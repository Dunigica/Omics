"""
Backfill abstract / claims_text / description_text for patents that have a
summary (with missing scores) but no text stored in the DB.

These patents were originally summarized by fetching text from Lens/EPO APIs
on the fly, but the text was never persisted. Without text, resynthesize
--missing-scores cannot reach them.

After this script runs, execute:
    python -m scripts.resynthesize_patents --missing-scores \\
        --group industrial_enzymes therapeutic_enzymes --provider groq

Sources tried per patent:
  Lens ID (not EPO_/USPTO_ prefix) → Lens.org API (abstract + claims + description)
  EPO_ prefix or EP*/WO* number    → EPO OPS API (abstract + claims)
  USPTO_ prefix or US* number      → USPTO PatentsView API (abstract + claims)

Run from backend/:
    python -m scripts.backfill_patent_text --dry-run
    python -m scripts.backfill_patent_text --group industrial_enzymes therapeutic_enzymes
    python -m scripts.backfill_patent_text --limit 500

    # Backfill text for unprocessed patents (no summary yet) before first synthesize run:
    python -m scripts.backfill_patent_text --no-summary --group therapeutic_enzymes crispr_proteins
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from Database.connection import engine, check_connection
from Database.models import Patent, PatentAISummary
from DataPipeline.patent_pipeline import EPOClient, EPO_CLAIMS_URL, LENS_API_URL

_ENZYME_GROUPS = {"industrial_enzymes", "therapeutic_enzymes", "crispr_proteins"}

EPO_ABSTRACT_URL     = "https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{number}/abstract"
EPO_DESCRIPTION_URL  = "https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{number}/description"
USPTO_SEARCH_URL     = "https://search.patentsview.org/api/v1/patent/"


# ---------------------------------------------------------------------------
# DB query
# ---------------------------------------------------------------------------

def fetch_text_missing(groups: list[str], limit: int | None) -> list[tuple]:
    """
    Return (patent_id, patent_number, lens_id, protein_type) for patents that:
      - have a summary with missing scores
      - have < 200 chars of stored text
    """
    group_list = ", ".join(f"'{g}'" for g in groups)
    limit_clause = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT p.patent_id, p.patent_number, p.lens_id, p.protein_type
        FROM patent_ai_summaries s
        JOIN patents p ON p.patent_id = s.patent_id
        WHERE p.protein_type IN ({group_list})
          AND (s.fto_score IS NULL OR s.commercial_opportunity IS NULL
               OR s.engineering_tractability IS NULL)
          AND (
            LENGTH(COALESCE(p.abstract, ''))
          + LENGTH(COALESCE(p.claims_text, ''))
          + LENGTH(COALESCE(p.description_text, ''))
          ) < 200
        ORDER BY p.protein_type, p.patent_id
        {limit_clause}
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def fetch_text_missing_no_summary(groups: list[str], limit: int | None) -> list[tuple]:
    """
    Return (patent_id, patent_number, lens_id, protein_type) for patents that:
      - have no summary yet (ai_processed=False, never reached LLM)
      - have < 200 chars of stored text
    These are typically EPO-indexed patents whose full text was never fetched.
    """
    group_list = ", ".join(f"'{g}'" for g in groups)
    limit_clause = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT p.patent_id, p.patent_number, p.lens_id, p.protein_type
        FROM patents p
        LEFT JOIN patent_ai_summaries s ON s.patent_id = p.patent_id
        WHERE p.protein_type IN ({group_list})
          AND p.ai_processed = FALSE
          AND s.patent_id IS NULL
          AND (
            LENGTH(COALESCE(p.abstract, ''))
          + LENGTH(COALESCE(p.claims_text, ''))
          + LENGTH(COALESCE(p.description_text, ''))
          ) < 200
        ORDER BY p.protein_type, p.patent_id
        {limit_clause}
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------

def _detect_source(lens_id: str, patent_number: str) -> str:
    # Patent number jurisdiction is the reliable signal for which API can serve text.
    # lens_id prefixes (EPO_/USPTO_) reflect how the patent was *ingested*, not what
    # API can return its full text — EPO OPS only serves EP/WO documents.
    pn = (patent_number or "").upper()
    if pn.startswith(("EP", "WO")):
        return "epo"
    if pn.startswith("US"):
        return "lens"   # Lens is preferred for US patents; USPTO PatentsView is the fallback
    if lens_id and not lens_id.startswith(("EPO_", "USPTO_")):
        return "lens"
    return "lens"  # safe default — Lens indexes all jurisdictions


# ---------------------------------------------------------------------------
# EPO OPS fetchers
# ---------------------------------------------------------------------------

def _epo_epodoc(patent_number: str) -> str:
    return re.sub(r'[A-Z]\d?$', '', patent_number.strip())


def _epo_get_json(url: str, client: EPOClient) -> dict:
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=client.get_headers(), timeout=20)
        except requests.RequestException:
            return {}
        if resp.status_code == 503:
            time.sleep(15 * (attempt + 1))
            continue
        if resp.status_code not in (200, 203):
            log.warning("EPO OPS %d for %s", resp.status_code, url)
            return {}
        try:
            return resp.json()
        except Exception as exc:
            log.warning("EPO OPS JSON parse failed: %s", exc)
            return {}
    return {}


def _epo_extract_text_node(node) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        parts = []
        for v in node.values():
            parts.append(_epo_extract_text_node(v))
        return " ".join(p for p in parts if p)
    if isinstance(node, list):
        return " ".join(_epo_extract_text_node(i) for i in node)
    return str(node) if node else ""


def fetch_epo_text(patent_number: str, client: EPOClient) -> dict:
    epodoc = _epo_epodoc(patent_number)
    result = {"abstract": "", "claims_text": "", "description_text": ""}

    # Abstract
    data = _epo_get_json(EPO_ABSTRACT_URL.format(number=epodoc), client)
    world = data.get("ops:world-patent-data", {})
    doc   = (world.get("ftxt:fulltext-documents") or world.get("exch:exchange-documents") or {})
    if isinstance(doc, dict):
        ab = doc.get("ftxt:fulltext-document") or doc.get("exch:exchange-document") or {}
        if isinstance(ab, list):
            ab = ab[0] if ab else {}
        ab_node = ab.get("abstract") or ab.get("ftxt:abstract") or {}
        if isinstance(ab_node, list):
            ab_node = ab_node[0] if ab_node else {}
        result["abstract"] = _epo_extract_text_node(ab_node).strip()[:5000]

    # Claims (reuse existing logic pattern)
    data = _epo_get_json(EPO_CLAIMS_URL.format(number=epodoc), client)
    world = data.get("ops:world-patent-data", {})
    ftxt  = world.get("ftxt:fulltext-documents", {})
    doc   = ftxt.get("ftxt:fulltext-document", {})
    if isinstance(doc, list):
        doc = doc[0] if doc else {}
    claims_node = doc.get("claims", {})
    if isinstance(claims_node, list):
        en = next((c for c in claims_node
                   if isinstance(c, dict) and c.get("@lang") == "en"), None)
        claims_node = en or (claims_node[0] if claims_node else {})
    claim_list = claims_node.get("claim", [])
    if isinstance(claim_list, dict):
        claim_list = [claim_list]
    parts = []
    for claim in (claim_list or []):
        num  = claim.get("@num", "")
        text = _epo_extract_text_node(claim.get("claim-text", ""))
        if text:
            parts.append(f"Claim {num}: {text}")
    result["claims_text"] = "\n\n".join(parts)

    # Description (first 20K chars)
    data = _epo_get_json(EPO_DESCRIPTION_URL.format(number=epodoc), client)
    world = data.get("ops:world-patent-data", {})
    ftxt  = world.get("ftxt:fulltext-documents", {})
    doc   = ftxt.get("ftxt:fulltext-document", {})
    if isinstance(doc, list):
        doc = doc[0] if doc else {}
    desc_node = doc.get("description", {})
    if isinstance(desc_node, list):
        en = next((d for d in desc_node
                   if isinstance(d, dict) and d.get("@lang") == "en"), None)
        desc_node = en or (desc_node[0] if desc_node else {})
    result["description_text"] = _epo_extract_text_node(desc_node).strip()[:20_000]

    time.sleep(0.5)  # EPO OPS rate limit: 30 req/s burst, 4 req/s sustained
    return result


# ---------------------------------------------------------------------------
# Lens fetcher
# ---------------------------------------------------------------------------

def fetch_lens_text(lens_id: str, patent_number: str, api_key: str) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if lens_id and not lens_id.startswith(("EPO_", "USPTO_")):
        query: dict = {"term": {"lens_id": lens_id}}
    else:
        pn = patent_number.strip().upper()
        m = re.match(r'^([A-Z]{2,3})(\d+)', pn)
        if m:
            query = {"bool": {"must": [
                {"term": {"jurisdiction": m.group(1)}},
                {"term": {"doc_number": m.group(2)}},
            ]}}
        else:
            query = {"term": {"doc_number": pn}}

    body = {
        "query": query,
        "include": ["lens_id", "doc_number", "jurisdiction", "abstract", "claims", "description"],
        "size": 1,
    }

    for attempt in range(4):
        try:
            resp = requests.post(LENS_API_URL, json=body, headers=headers, timeout=30)
        except requests.RequestException as exc:
            log.warning("Lens request error: %s", exc)
            return {}
        if resp.status_code == 429:
            wait = 15 * (2 ** attempt)  # 15, 30, 60, 120 s
            log.warning("Lens rate limit (429) — waiting %ds (attempt %d/4)", wait, attempt + 1)
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            log.debug("Lens error %d", resp.status_code)
            return {}
        break
    else:
        log.warning("Lens rate limit persists after 4 attempts — skipping this patent")
        return {}

    hits = resp.json().get("data", [])
    if not hits:
        return {}
    raw = hits[0]

    a = raw.get("abstract", "")
    abstract = (
        " ".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in a)
        if isinstance(a, list) else str(a or "")
    )
    c = raw.get("claims", [])
    claims_text = (
        "\n".join(
            x.get("text", x.get("claim_text", "")) if isinstance(x, dict) else str(x)
            for x in c
        ) if isinstance(c, list) else str(c or "")
    )
    d = raw.get("description", "")
    if isinstance(d, list):
        desc = " ".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in d)
    else:
        desc = str(d) if d else ""

    return {
        "abstract":         abstract,
        "claims_text":      claims_text,
        "description_text": desc[:20_000],
        "_jurisdiction":    (raw.get("jurisdiction") or "").upper(),
        "_doc_number":      raw.get("doc_number") or "",
    }


# ---------------------------------------------------------------------------
# USPTO PatentsView fetcher (single patent)
# ---------------------------------------------------------------------------

def fetch_uspto_text(patent_number: str) -> dict:
    pn = re.sub(r'^US', '', patent_number.strip(), flags=re.IGNORECASE)
    pn = re.sub(r'[A-Z]\d*$', '', pn)  # strip kind code
    body = {
        "q": {"_eq": {"patent_id": pn}},
        "f": ["patent_abstract", "patent_title", "claims.claim_text", "claims.claim_sequence"],
        "o": {"per_page": 1},
    }
    try:
        resp = requests.post(
            USPTO_SEARCH_URL, json=body,
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        if resp.status_code != 200:
            return {}
        patents = resp.json().get("patents") or []
        if not patents:
            return {}
        p = patents[0]
        claims_raw = p.get("claims") or []
        if isinstance(claims_raw, list):
            sorted_claims = sorted(
                claims_raw,
                key=lambda c: int(c.get("claim_sequence", 0)) if str(c.get("claim_sequence", "0")).isdigit() else 0,
            )
            claims_text = "\n\n".join(
                c.get("claim_text", "") for c in sorted_claims if c.get("claim_text")
            )
        else:
            claims_text = ""
        return {
            "abstract":         p.get("patent_abstract", "") or "",
            "claims_text":      claims_text,
            "description_text": "",
        }
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(
    groups: list[str],
    limit: int | None = None,
    dry_run: bool = False,
    no_summary: bool = False,
    skip_lens: bool = False,
) -> None:
    lens_api_key = "" if skip_lens else os.environ.get("LENS_API_KEY", "")
    epo_client_id     = os.environ.get("EPO_OPS_CLIENT_ID", "")
    epo_client_secret = os.environ.get("EPO_OPS_CLIENT_SECRET", "")

    epo_client = None
    if epo_client_id and epo_client_secret:
        try:
            epo_client = EPOClient(epo_client_id, epo_client_secret)
            log.info("EPO OPS client initialised")
        except Exception as exc:
            log.warning("EPO OPS init failed: %s — EPO patents will be skipped", exc)

    if skip_lens:
        log.info("Lens disabled (--skip-lens) — using EPO OPS and USPTO only")
    elif not lens_api_key:
        log.warning("LENS_API_KEY not set — Lens-sourced patents will be skipped")
    if not epo_client:
        log.warning("EPO_OPS_CLIENT_ID/SECRET not set — EPO patents will be skipped")

    if no_summary:
        rows = fetch_text_missing_no_summary(groups, limit)
        log.info("Found %d unprocessed patents (no summary yet) with insufficient text", len(rows))
    else:
        rows = fetch_text_missing(groups, limit)
        log.info("Found %d patents with missing text + missing scores", len(rows))

    if not rows:
        log.info("Nothing to backfill.")
        return

    if dry_run:
        by_source: dict[str, int] = {}
        for _, pn, lid, _ in rows[:20]:
            src = _detect_source(lid or "", pn or "")
            by_source[src] = by_source.get(src, 0) + 1
            log.info("  [DRY RUN] %s  source=%s", pn, src)
        if len(rows) > 20:
            log.info("  ... and %d more", len(rows) - 20)
        for src, cnt in sorted(by_source.items()):
            log.info("  Source breakdown (sample): %s = %d", src, cnt)
        return

    def _total(d: dict) -> int:
        return (len(d.get("abstract", ""))
                + len(d.get("claims_text", ""))
                + len(d.get("description_text", "")))

    n_ok = n_skip = n_err = 0
    total = len(rows)

    with Session(engine) as session:
        for i, (patent_id, patent_number, lens_id, protein_type) in enumerate(rows, 1):
            log.info("[%d/%d] %s  lens_id=%s  [%s]", i, total, patent_number, lens_id, protein_type)

            source = _detect_source(lens_id or "", patent_number or "")

            try:
                text_data: dict = {}
                tried: list[str] = []

                # Try Lens first (skipped when --skip-lens)
                if lens_api_key:
                    text_data = fetch_lens_text(lens_id or "", patent_number or "", lens_api_key)
                    tried.append("lens")

                # Extract jurisdiction Lens returned (empty when Lens rate-limited or no hit)
                lens_jurisdiction = text_data.pop("_jurisdiction", "")
                lens_doc_number   = text_data.pop("_doc_number", "")

                pn_upper   = (patent_number or "").upper()
                is_us      = pn_upper.startswith("US") or lens_jurisdiction == "US"
                is_ep_wo   = pn_upper.startswith(("EP", "WO")) or lens_jurisdiction in ("EP", "WO")
                is_numeric = pn_upper.isdigit()
                # When jurisdiction is unknown (Lens rate-limited), bare numerics try both APIs

                # EPO OPS: explicit EP/WO, or bare numeric that isn't confirmed US
                if _total(text_data) < 100 and epo_client and (is_ep_wo or (is_numeric and not is_us)):
                    pn_for_epo = lens_doc_number or patent_number or ""
                    if pn_for_epo.isdigit():
                        pn_for_epo = "EP" + pn_for_epo.zfill(7)
                    log.info("  Lens insufficient — trying EPO OPS (%s)", pn_for_epo)
                    text_data = fetch_epo_text(pn_for_epo, epo_client)
                    tried.append("epo")

                # USPTO: explicit US, or bare numeric that isn't confirmed EP/WO
                if _total(text_data) < 100 and (is_us or (is_numeric and not is_ep_wo)):
                    pn_for_uspto = lens_doc_number or patent_number or ""
                    log.info("  Lens insufficient — trying USPTO PatentsView (%s)", pn_for_uspto)
                    text_data = fetch_uspto_text(pn_for_uspto)
                    tried.append("uspto")

                # If nothing was tried and nothing fetched (no keys set, non-US patent)
                if _total(text_data) == 0 and not lens_api_key and not epo_client:
                    log.warning("  No API available — skip (set LENS_API_KEY in .env)")
                    n_skip += 1
                    continue

                total_chars = _total(text_data)

                if total_chars < 100:
                    log.warning("  Fetched < 100 chars from all sources [%s] — skip",
                                "+".join(tried) if tried else "none")
                    n_skip += 1
                    continue

                patent_row = session.query(Patent).filter_by(patent_id=patent_id).first()
                if not patent_row:
                    n_skip += 1
                    continue

                if text_data.get("abstract"):
                    patent_row.abstract = text_data["abstract"]
                if text_data.get("claims_text"):
                    patent_row.claims_text = text_data["claims_text"]
                if text_data.get("description_text"):
                    patent_row.description_text = text_data["description_text"]

                session.commit()
                log.info("  OK [%s]  abstract=%d  claims=%d  desc=%d chars",
                         source,
                         len(text_data.get("abstract", "")),
                         len(text_data.get("claims_text", "")),
                         len(text_data.get("description_text", "")))
                n_ok += 1

            except Exception as exc:
                log.error("  Failed: %s", exc)
                session.rollback()
                n_err += 1

    log.info("Done — backfilled: %d  skipped: %d  errors: %d", n_ok, n_skip, n_err)
    if n_ok:
        log.info("Next step:")
        if no_summary:
            log.info("  python -m scripts.search_patents --groups %s "
                     "--synthesize-only --provider groq", " ".join(groups))
        else:
            log.info("  python -m scripts.resynthesize_patents --missing-scores "
                     "--group %s --provider groq", " ".join(groups))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill patent text from Lens/EPO/USPTO for patents missing text+scores",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--group", nargs="+", metavar="GROUP",
        default=["industrial_enzymes", "therapeutic_enzymes"],
        help="Protein type(s) to process (default: industrial_enzymes therapeutic_enzymes)",
    )
    parser.add_argument(
        "--limit", type=int, metavar="N",
        help="Process at most N patents",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be fetched without making API calls",
    )
    parser.add_argument(
        "--no-summary", action="store_true",
        help="Target patents with no summary yet (ai_processed=False) instead of "
             "patents with summaries missing scores. Use this before the first "
             "synthesize run to backfill text for EPO-indexed patents that have "
             "no claims/description stored.",
    )
    parser.add_argument(
        "--skip-lens", action="store_true",
        help="Skip Lens API entirely and go straight to EPO OPS / USPTO. "
             "Use when the Lens API key is rate-limited.",
    )
    args = parser.parse_args()

    if not check_connection():
        print("ERROR: Cannot reach the database. Check DATABASE_URL in .env")
        sys.exit(1)

    run(
        groups=args.group,
        limit=args.limit,
        dry_run=args.dry_run,
        no_summary=args.no_summary,
        skip_lens=args.skip_lens,
    )


if __name__ == "__main__":
    main()
