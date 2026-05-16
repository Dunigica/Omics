"""
Patent pipeline end-to-end audit.

Checks every layer of the patent stack:
  1.  DB connectivity
  2.  Schema  — all Tier 8 tables + expected columns present
  3.  Counts  — row counts per table
  4.  Quality — null rates on critical fields
  5.  Integrity — FK consistency, orphaned rows, value ranges
  6.  Flow    — data moving through each pipeline stage
  7.  API     — every endpoint: HTTP 200, correct shape, sane values
                (skipped gracefully if server is not running)

Run:
    cd backend/
    python -m scripts.audit_patents
    python -m scripts.audit_patents --api-url http://localhost:8000/api/v1   # specify custom API URL
    python -m scripts.audit_patents --skip-api        # DB-only audit
    python -m scripts.audit_patents --json            # machine-readable output

Exit code: 0 = all pass/warn, 1 = any FAIL
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Force UTF-8 output on Windows so box-drawing characters render correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from sqlalchemy import inspect, text
from Database.connection import engine, check_connection

# ─── Result tracking ─────────────────────────────────────────────────────────

@dataclass
class Check:
    section: str
    name: str
    status: str          # PASS | WARN | FAIL | SKIP
    detail: str = ""
    hint: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, section: str, name: str, status: str, detail: str = "", hint: str = ""):
        self.checks.append(Check(section, name, status, detail, hint))
        return self.checks[-1]

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == "FAIL"]

    @property
    def warned(self) -> list[Check]:
        return [c for c in self.checks if c.status == "WARN"]


COLORS = {
    "PASS": "\033[32m",
    "WARN": "\033[33m",
    "FAIL": "\033[31m",
    "SKIP": "\033[90m",
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "SECTION": "\033[36m",
}


def _c(status: str, text_: str) -> str:
    return f"{COLORS.get(status,'')}{text_}{COLORS['RESET']}"


def print_report(report: Report, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps([vars(c) for c in report.checks], indent=2))
        return

    current_section = None
    for c in report.checks:
        if c.section != current_section:
            current_section = c.section
            print(f"\n{COLORS['SECTION']}{COLORS['BOLD']}── {c.section} {'─'*(60-len(c.section))}{COLORS['RESET']}")
        icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗", "SKIP": "·"}[c.status]
        line = f"  {_c(c.status, icon)} {c.name}"
        if c.detail:
            line += f"  {_c('RESET', c.detail)}"
        print(line)
        if c.hint and c.status in ("WARN", "FAIL"):
            print(f"      {COLORS['SKIP']}→ {c.hint}{COLORS['RESET']}")

    n_pass = sum(1 for c in report.checks if c.status == "PASS")
    n_warn = sum(1 for c in report.checks if c.status == "WARN")
    n_fail = sum(1 for c in report.checks if c.status == "FAIL")
    n_skip = sum(1 for c in report.checks if c.status == "SKIP")
    print(f"\n{'─'*65}")
    parts = [
        _c("PASS", f"{n_pass} passed"),
        _c("WARN", f"{n_warn} warnings"),
        _c("FAIL", f"{n_fail} failed"),
        _c("SKIP", f"{n_skip} skipped"),
    ]
    print("  " + "   ".join(parts))
    if report.failed:
        print(f"\n{_c('FAIL', 'FAILURES:')}")
        for c in report.failed:
            print(f"  {c.section} / {c.name}: {c.detail}")
            if c.hint:
                print(f"    → {c.hint}")


# ─── DB helpers ──────────────────────────────────────────────────────────────

def _scalar(sql: str, params: dict | None = None) -> Any:
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        row = result.fetchone()
        return row[0] if row else None


def _rows(sql: str, params: dict | None = None) -> list:
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchall()


def _table_exists(name: str) -> bool:
    insp = inspect(engine)
    return name in insp.get_table_names()


def _columns(table: str) -> set[str]:
    insp = inspect(engine)
    if not _table_exists(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _count(table: str, where: str = "1=1") -> int:
    if not _table_exists(table):
        return -1
    return int(_scalar(f"SELECT COUNT(*) FROM {table} WHERE {where}") or 0)


def _null_rate(table: str, col: str) -> float:
    """Return fraction of rows where col IS NULL."""
    total = _count(table)
    if total == 0:
        return 0.0
    nulls = _scalar(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL") or 0
    return int(nulls) / total


# ─── HTTP helper ─────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 30) -> tuple[int, dict | None]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — DB CONNECTIVITY
# ═══════════════════════════════════════════════════════════════════════════════

def check_connectivity(report: Report) -> bool:
    S = "1. Connectivity"
    ok = check_connection()
    if ok:
        version = _scalar("SELECT version()")
        report.add(S, "PostgreSQL reachable", "PASS", (version or "")[:60])
        return True
    else:
        report.add(S, "PostgreSQL reachable", "FAIL",
                   hint="Check DATABASE_URL in .env and that PostgreSQL is running")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════

TIER8_SCHEMA = {
    "patents": {
        "required": ["patent_id", "patent_number", "title", "protein_type",
                     "assignees", "publication_date", "source_url", "ai_processed"],
    },
    "patent_ai_summaries": {
        "required": ["summary_id", "patent_id", "fto_risk", "biological_context",
                     "engineering_strategy", "tissues_claimed", "serotypes_covered",
                     "epistatic_interactions", "enzyme_context", "peptide_context",
                     "reference_sequence_id", "opportunity_notes",
                     "fto_score", "fto_score_rationale",
                     "commercial_opportunity", "commercial_opportunity_rationale",
                     "engineering_tractability", "engineering_tractability_rationale"],
    },
    "patent_protein_coverage": {
        "required": ["coverage_id", "patent_id", "protein_type", "position_constraints",
                     "breadth_estimate"],
    },
    "patent_opportunity_zones": {
        "required": ["zone_id", "name", "protein_type", "opportunity_score",
                     "strategy_notes", "tissues_of_interest", "vr_positions"],
    },
    "patent_experimental_records": {
        "required": ["record_id", "patent_id", "protein_type", "mutations",
                     "metric_type", "fold_change", "direction",
                     "substrate_or_target"],
    },
    "patent_epistasis_edges": {
        "required": ["edge_id", "protein_type", "ref_id", "position_a", "position_b",
                     "interaction_type", "interaction_mechanism",
                     "n_patents_supporting", "source_patent_ids"],
    },
    "enzyme_reference_sequences": {
        # protein_type is not on this table — it comes from patents JOIN; actual col is protein_group
        "required": ["ref_id", "enzyme_family", "common_name", "uniprot_id", "sequence"],
    },
    "patent_sequences": {
        "required": ["pseq_id", "patent_id", "sequence"],
    },
    "patent_description_sections": {
        "required": ["section_id", "patent_id", "section_type", "section_text"],
    },
}


def check_schema(report: Report) -> None:
    S = "2. Schema"
    for table, spec in TIER8_SCHEMA.items():
        if not _table_exists(table):
            report.add(S, f"Table: {table}", "FAIL",
                       hint=f"python -m scripts.setup_db  (or alembic upgrade head)")
            continue

        existing_cols = _columns(table)
        missing = [c for c in spec["required"] if c not in existing_cols]
        if missing:
            report.add(S, f"Table: {table}", "FAIL",
                       f"missing columns: {', '.join(missing)}",
                       hint="Run schema migration to add missing columns")
        else:
            report.add(S, f"Table: {table}", "PASS",
                       f"{len(existing_cols)} columns present")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — ROW COUNTS
# ═══════════════════════════════════════════════════════════════════════════════

def check_counts(report: Report) -> dict[str, int]:
    S = "3. Row counts"
    counts = {}

    tables = [
        ("patents",                    50,  None,  "Run patent_pipeline to fetch patents"),
        ("patent_ai_summaries",        10,  None,  "Run patent_pipeline with LLM synthesis"),
        ("patent_experimental_records", 0,  None,  "LLM synthesis extracts these — rerun synthesis"),
        ("patent_epistasis_edges",      0,  None,  "Run: python -m scripts.build_epistasis_graph"),
        ("patent_protein_coverage",     0,  None,  "Run patent_pipeline --update-coverage"),
        ("patent_opportunity_zones",    0,  None,  "Run patent_pipeline --build-opportunities"),
        ("enzyme_reference_sequences",  0,  None,  "Run: python -m scripts.build_reference_sequences --phase 1"),
        ("patent_sequences",            0,  None,  "Populated during patent fetch with sequence data"),
        ("patent_description_sections", 0,  None,  "Run: python -m scripts.build_description_sections"),
    ]

    for table, warn_below, fail_below, hint in tables:
        n = _count(table)
        if n == -1:
            report.add(S, f"{table}", "FAIL", "table does not exist")
            counts[table] = 0
            continue

        counts[table] = n
        if fail_below is not None and n < fail_below:
            report.add(S, f"{table}", "FAIL", f"{n} rows", hint)
        elif n < warn_below:
            report.add(S, f"{table}", "WARN", f"{n} rows", hint)
        else:
            report.add(S, f"{table}", "PASS", f"{n:,} rows")

    return counts


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — DATA QUALITY
# ═══════════════════════════════════════════════════════════════════════════════

def check_quality(report: Report, counts: dict[str, int]) -> None:
    S = "4. Data quality"

    # ── patents ──
    if counts.get("patents", 0) > 0:
        null_title = _null_rate("patents", "title")
        if null_title > 0.1:
            report.add(S, "patents.title null rate", "WARN",
                       f"{null_title:.1%}", "Fetch may have returned incomplete records")
        else:
            report.add(S, "patents.title null rate", "PASS", f"{null_title:.1%}")

        processed = _scalar("SELECT COUNT(*) FROM patents WHERE ai_processed = TRUE") or 0
        total_p = counts["patents"]
        pct = processed / total_p if total_p else 0
        status = "PASS" if pct >= 0.5 else "WARN" if pct > 0 else "FAIL"
        report.add(S, "patents: AI processed fraction", status,
                   f"{processed}/{total_p} ({pct:.0%})",
                   hint="Run patent_pipeline --synthesize to process unprocessed patents" if pct < 0.5 else "")

        # FTO risk distribution
        rows = _rows("""
            SELECT fto_risk, COUNT(*) as n
            FROM patent_ai_summaries
            GROUP BY fto_risk ORDER BY n DESC
        """)
        dist = {r[0]: int(r[1]) for r in rows}
        total_s = sum(dist.values())
        if total_s > 0:
            null_fto = dist.get(None, 0) + dist.get("unknown", 0)
            fto_pct = null_fto / total_s
            status = "WARN" if fto_pct > 0.3 else "PASS"
            dist_str = "  ".join(f"{k or 'null'}:{v}" for k, v in sorted(dist.items(), key=lambda x: -(x[1])))
            report.add(S, "ai_summaries: FTO risk distribution", status,
                       dist_str,
                       hint="High unknown/null rate means LLM synthesis did not extract FTO risk" if fto_pct > 0.3 else "")

    # ── ai summaries quality ──
    if counts.get("patent_ai_summaries", 0) > 0:
        for col, threshold, label in [
            ("biological_context", 0.5, "biological_context populated"),
            ("engineering_strategy", 0.5, "engineering_strategy populated"),
            ("opportunity_notes", 0.3, "opportunity_notes populated"),
        ]:
            if "patent_ai_summaries" in _columns("patent_ai_summaries") or True:
                cols = _columns("patent_ai_summaries")
                if col not in cols:
                    report.add(S, f"ai_summaries: {label}", "SKIP", "column missing")
                    continue
                null_rate = _null_rate("patent_ai_summaries", col)
                populated = 1 - null_rate
                status = "PASS" if populated >= threshold else "WARN"
                report.add(S, f"ai_summaries: {label}", status,
                           f"{populated:.0%} populated",
                           hint="Rerun synthesis for better field extraction" if populated < threshold else "")

    # ── experimental records quality ──
    if counts.get("patent_experimental_records", 0) > 0:
        # Direction distribution
        rows = _rows("""
            SELECT direction, COUNT(*) as n
            FROM patent_experimental_records
            WHERE direction IS NOT NULL
            GROUP BY direction ORDER BY n DESC
        """)
        dist_str = "  ".join(f"{r[0]}:{r[1]}" for r in rows)
        report.add(S, "experimental_records: direction distribution", "PASS", dist_str)

        # Hallucinated positions (> 5000)
        bad_pos = _scalar("""
            SELECT COUNT(*) FROM patent_experimental_records er,
            LATERAL jsonb_array_elements(
                CASE WHEN jsonb_typeof(er.mutations) = 'array' THEN er.mutations ELSE '[]'::jsonb END
            ) AS mut
            WHERE (mut->>'position')::text ~ '^[0-9]+$'
              AND (mut->>'position')::integer > 5000
        """) or 0
        if int(bad_pos) > 0:
            report.add(S, "experimental_records: hallucinated positions (>5000)", "WARN",
                       f"{bad_pos} records",
                       hint="API already filters these; consider rerunning synthesis for affected patents")
        else:
            report.add(S, "experimental_records: hallucinated positions (>5000)", "PASS", "none found")

        # Records with NULL substrate_or_target
        if "substrate_or_target" in _columns("patent_experimental_records"):
            null_sub = _null_rate("patent_experimental_records", "substrate_or_target")
            status = "WARN" if null_sub > 0.7 else "PASS"
            report.add(S, "experimental_records: substrate_or_target populated", status,
                       f"{1-null_sub:.0%} populated")

    # ── epistasis edges quality ──
    # Only enzyme/CRISPR protein types use enzyme_reference_sequences — aav_capsid
    # and monoclonal_antibodies have no enzyme family mapping so null ref_id is expected.
    ENZYME_TYPES = ("crispr_proteins", "industrial_enzymes", "therapeutic_enzymes",
                    "peptide_therapeutics")
    if counts.get("patent_epistasis_edges", 0) > 0:
        # Overall linkage (informational)
        null_ref = _scalar(
            "SELECT COUNT(*) FROM patent_epistasis_edges WHERE ref_id IS NULL"
        ) or 0
        total_e = counts["patent_epistasis_edges"]

        # Linkage rate among enzyme/CRISPR types only (these should be linked)
        enzyme_total = _scalar(f"""
            SELECT COUNT(*) FROM patent_epistasis_edges
            WHERE protein_type = ANY(ARRAY{list(ENZYME_TYPES)!r})
        """.replace("'", "'")) or 0
        enzyme_unlinked = _scalar(f"""
            SELECT COUNT(*) FROM patent_epistasis_edges
            WHERE protein_type = ANY(ARRAY{list(ENZYME_TYPES)!r})
              AND ref_id IS NULL
        """.replace("'", "'")) or 0
        enzyme_linked = int(enzyme_total) - int(enzyme_unlinked)
        enzyme_null_pct = int(enzyme_unlinked) / int(enzyme_total) if int(enzyme_total) else 0

        status = "FAIL" if enzyme_null_pct > 0.7 else "WARN" if enzyme_null_pct > 0.3 else "PASS"
        report.add(S, "epistasis_edges: ref_id linkage (enzyme/CRISPR)", status,
                   f"{enzyme_linked}/{int(enzyme_total)} enzyme+CRISPR edges linked  "
                   f"({total_e - int(null_ref)}/{total_e} overall)",
                   hint="Run: python -m scripts.build_reference_sequences --phase 1  "
                        "then: python -m scripts.build_epistasis_graph" if enzyme_null_pct > 0.3 else "")

        # Position range sanity
        bad = _scalar("""
            SELECT COUNT(*) FROM patent_epistasis_edges
            WHERE position_a > 5000 OR position_b > 5000
              OR position_a < 1 OR position_b < 1
        """) or 0
        if int(bad) > 0:
            report.add(S, "epistasis_edges: position sanity (1–5000)", "WARN",
                       f"{bad} edges with out-of-range positions",
                       hint="These edges may contain LLM-hallucinated positions; consider rebuilding graph")
        else:
            report.add(S, "epistasis_edges: position sanity (1–5000)", "PASS")

    # ── opportunity zones ──
    if counts.get("patent_opportunity_zones", 0) > 0:
        rows = _rows("""
            SELECT protein_type, COUNT(*) as n, AVG(opportunity_score) as avg_score
            FROM patent_opportunity_zones
            GROUP BY protein_type ORDER BY n DESC
        """)
        for r in rows:
            report.add(S, f"opportunity_zones: {r[0] or 'unknown'}", "PASS",
                       f"{r[1]} zones  avg_score={float(r[2] or 0):.2f}")

    # ── reference sequences ──
    if counts.get("enzyme_reference_sequences", 0) > 0:
        null_seq = _null_rate("enzyme_reference_sequences", "sequence")
        status = "WARN" if null_seq > 0.2 else "PASS"
        report.add(S, "enzyme_reference_sequences: sequence populated", status,
                   f"{1-null_seq:.0%} have sequence",
                   hint="Run build_reference_sequences --phase 2 to fetch sequences from UniProt")

        families = _scalar("SELECT COUNT(DISTINCT enzyme_family) FROM enzyme_reference_sequences") or 0
        report.add(S, "enzyme_reference_sequences: distinct families", "PASS", f"{families}")

    # ── enzyme / CRISPR multi-dimensional scores ──
    ENZYME_SCORE_GROUPS = ["industrial_enzymes", "therapeutic_enzymes", "crispr_proteins"]
    score_cols = _columns("patent_ai_summaries")
    scores_migrated = all(c in score_cols for c in (
        "fto_score", "commercial_opportunity", "engineering_tractability"))

    if not scores_migrated:
        report.add(S, "enzyme scores: migration applied", "FAIL",
                   "score columns missing from patent_ai_summaries",
                   hint="Run: python -m scripts.migrate_enzyme_scores")
    else:
        report.add(S, "enzyme scores: migration applied", "PASS",
                   "fto_score / commercial_opportunity / engineering_tractability present")

        for grp in ENZYME_SCORE_GROUPS:
            n_sum_grp = int(_scalar("""
                SELECT COUNT(*) FROM patents p
                JOIN patent_ai_summaries s ON s.patent_id = p.patent_id
                WHERE p.protein_type = :g
            """, {"g": grp}) or 0)
            if n_sum_grp == 0:
                report.add(S, f"enzyme scores: {grp}", "SKIP", "no summaries yet")
                continue

            n_all3 = int(_scalar("""
                SELECT COUNT(*) FROM patents p
                JOIN patent_ai_summaries s ON s.patent_id = p.patent_id
                WHERE p.protein_type = :g
                  AND s.fto_score IS NOT NULL
                  AND s.commercial_opportunity IS NOT NULL
                  AND s.engineering_tractability IS NOT NULL
            """, {"g": grp}) or 0)
            pct = n_all3 / n_sum_grp
            status = "PASS" if pct >= 0.8 else "WARN" if pct > 0 else "FAIL"
            report.add(S, f"enzyme scores: {grp} all-3-scores rate", status,
                       f"{n_all3}/{n_sum_grp} ({pct:.0%}) fully scored",
                       hint=f"python -m scripts.search_patents --groups {grp} --synthesize-only --no-resume"
                            if pct < 0.8 else "")

        bad_range = int(_scalar("""
            SELECT COUNT(*) FROM patent_ai_summaries
            WHERE (fto_score IS NOT NULL AND (fto_score < 1 OR fto_score > 5))
               OR (commercial_opportunity IS NOT NULL AND (commercial_opportunity < 1 OR commercial_opportunity > 5))
               OR (engineering_tractability IS NOT NULL AND (engineering_tractability < 1 OR engineering_tractability > 5))
        """) or 0)
        status = "FAIL" if bad_range > 0 else "PASS"
        report.add(S, "enzyme scores: all values in range 1–5", status,
                   f"{bad_range} out-of-range values" if bad_range > 0 else "",
                   hint="Check DB constraints or rerun synthesis for affected patents" if bad_range > 0 else "")

        inconsistent = int(_scalar("""
            SELECT COUNT(*) FROM patent_ai_summaries
            WHERE fto_score IS NOT NULL AND fto_risk IS NOT NULL
              AND NOT (
                (fto_score BETWEEN 1 AND 2 AND fto_risk = 'high')   OR
                (fto_score = 3              AND fto_risk = 'medium') OR
                (fto_score BETWEEN 4 AND 5 AND fto_risk = 'low')
              )
        """) or 0)
        status = "WARN" if inconsistent > 0 else "PASS"
        report.add(S, "enzyme scores: fto_risk consistent with fto_score", status,
                   f"{inconsistent} mismatched rows" if inconsistent > 0 else "",
                   hint="fto_risk should be derived from fto_score — rerun synthesis for affected patents"
                        if inconsistent > 0 else "")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — DATA INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════════

def check_integrity(report: Report, counts: dict[str, int]) -> None:
    S = "5. Data integrity"

    # ── Orphaned ai_summaries (no parent patent) ──
    if counts.get("patent_ai_summaries", 0) > 0:
        orphans = _scalar("""
            SELECT COUNT(*) FROM patent_ai_summaries s
            LEFT JOIN patents p ON p.patent_id = s.patent_id
            WHERE p.patent_id IS NULL
        """) or 0
        status = "FAIL" if int(orphans) > 0 else "PASS"
        report.add(S, "ai_summaries: no orphaned rows", status,
                   f"{orphans} orphans" if int(orphans) > 0 else "",
                   hint="DELETE FROM patent_ai_summaries WHERE patent_id NOT IN (SELECT patent_id FROM patents)" if int(orphans) > 0 else "")

    # ── Orphaned experimental records ──
    if counts.get("patent_experimental_records", 0) > 0:
        orphans = _scalar("""
            SELECT COUNT(*) FROM patent_experimental_records er
            LEFT JOIN patents p ON p.patent_id = er.patent_id
            WHERE p.patent_id IS NULL
        """) or 0
        status = "FAIL" if int(orphans) > 0 else "PASS"
        report.add(S, "experimental_records: no orphaned rows", status,
                   f"{orphans} orphans" if int(orphans) > 0 else "")

    # ── Duplicate patent numbers ──
    if counts.get("patents", 0) > 0:
        dupes = _scalar("""
            SELECT COUNT(*) FROM (
                SELECT patent_number, COUNT(*) as n
                FROM patents
                WHERE patent_number IS NOT NULL
                GROUP BY patent_number HAVING COUNT(*) > 1
            ) dups
        """) or 0
        status = "WARN" if int(dupes) > 0 else "PASS"
        report.add(S, "patents: no duplicate patent numbers", status,
                   f"{dupes} duplicated numbers" if int(dupes) > 0 else "",
                   hint="Deduplication step may need to be rerun" if int(dupes) > 0 else "")

    # ── ai_summaries: one per patent ──
    if counts.get("patent_ai_summaries", 0) > 0:
        dupes = _scalar("""
            SELECT COUNT(*) FROM (
                SELECT patent_id, COUNT(*) as n FROM patent_ai_summaries
                GROUP BY patent_id HAVING COUNT(*) > 1
            ) d
        """) or 0
        status = "FAIL" if int(dupes) > 0 else "PASS"
        report.add(S, "ai_summaries: one-per-patent constraint", status,
                   f"{dupes} patents with multiple summaries" if int(dupes) > 0 else "",
                   hint="UNIQUE constraint on patent_id should prevent this — check migration" if int(dupes) > 0 else "")

    # ── Epistasis edges: canonical ordering (pos_a <= pos_b) ──
    if counts.get("patent_epistasis_edges", 0) > 0:
        bad_order = _scalar("""
            SELECT COUNT(*) FROM patent_epistasis_edges WHERE position_a > position_b
        """) or 0
        status = "FAIL" if int(bad_order) > 0 else "PASS"
        report.add(S, "epistasis_edges: canonical pos_a <= pos_b", status,
                   f"{bad_order} edges with reversed positions" if int(bad_order) > 0 else "",
                   hint="Rebuild graph: python -m scripts.build_epistasis_graph" if int(bad_order) > 0 else "")

    # ── Coverage: position constraints are valid JSON arrays ──
    if counts.get("patent_protein_coverage", 0) > 0:
        bad_json = _scalar("""
            SELECT COUNT(*) FROM patent_protein_coverage
            WHERE position_constraints IS NOT NULL
              AND jsonb_typeof(position_constraints) != 'array'
        """) or 0
        status = "FAIL" if int(bad_json) > 0 else "PASS"
        report.add(S, "patent_protein_coverage: position_constraints are arrays", status,
                   f"{bad_json} rows with non-array" if int(bad_json) > 0 else "",
                   hint="Run: python -m scripts.migrate_coverage_to_v2" if int(bad_json) > 0 else "")

    # ── Proteins types consistency ──
    pt_in_patents = set(r[0] for r in _rows(
        "SELECT DISTINCT protein_type FROM patents WHERE protein_type IS NOT NULL"))
    pt_in_coverage = set(r[0] for r in _rows(
        "SELECT DISTINCT protein_type FROM patent_protein_coverage WHERE protein_type IS NOT NULL"
    )) if _table_exists("patent_protein_coverage") else set()
    pt_in_zones = set(r[0] for r in _rows(
        "SELECT DISTINCT protein_type FROM patent_opportunity_zones WHERE protein_type IS NOT NULL"
    )) if _table_exists("patent_opportunity_zones") else set()

    all_types = sorted(pt_in_patents)
    report.add(S, "protein_type values in patents", "PASS",
               ", ".join(all_types) or "(none)")

    # coverage types that don't exist in patents
    orphan_cov = pt_in_coverage - pt_in_patents
    if orphan_cov:
        report.add(S, "coverage: protein_types match patents", "WARN",
                   f"unknown types in coverage: {', '.join(orphan_cov)}")
    elif pt_in_coverage:
        report.add(S, "coverage: protein_types match patents", "PASS")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — PIPELINE FLOW
# ═══════════════════════════════════════════════════════════════════════════════

def check_pipeline_flow(report: Report, counts: dict[str, int]) -> None:
    S = "6. Pipeline flow"

    n_pat = counts.get("patents", 0)
    n_sum = counts.get("patent_ai_summaries", 0)
    n_exp = counts.get("patent_experimental_records", 0)
    n_epi = counts.get("patent_epistasis_edges", 0)
    n_cov = counts.get("patent_protein_coverage", 0)
    n_opp = counts.get("patent_opportunity_zones", 0)
    n_ref = counts.get("enzyme_reference_sequences", 0)

    # Stage 1: patents fetched
    status = "PASS" if n_pat >= 50 else "WARN" if n_pat > 0 else "FAIL"
    report.add(S, "Stage 1 — Patents fetched", status, f"{n_pat:,} patents",
               hint="Run: python -m DataPipeline.patent_pipeline --fetch" if n_pat == 0 else "")

    # Stage 2: LLM synthesis
    ratio = n_sum / n_pat if n_pat else 0
    status = "PASS" if ratio >= 0.8 else "WARN" if ratio >= 0.3 else "FAIL"
    report.add(S, "Stage 2 — LLM synthesis", status,
               f"{n_sum}/{n_pat} patents synthesized ({ratio:.0%})",
               hint="Run: python -m DataPipeline.patent_pipeline --synthesize" if ratio < 0.8 else "")

    # Stage 3: Experimental records extracted
    per_pat = n_exp / n_sum if n_sum else 0
    status = "PASS" if per_pat >= 1.0 else "WARN" if per_pat > 0 else "SKIP"
    report.add(S, "Stage 3 — Experimental records extracted", status,
               f"{n_exp:,} records ({per_pat:.1f}/summary)" if n_sum else "no summaries yet")

    # Stage 4: Reference sequences linked
    if n_sum > 0:
        linked = _scalar("""
            SELECT COUNT(DISTINCT s.patent_id)
            FROM patent_ai_summaries s
            WHERE s.reference_sequence_id IS NOT NULL
        """) or 0
        link_ratio = int(linked) / n_sum
        # Note: only enzyme/CRISPR/peptide patents need reference sequences
        status = "PASS" if int(linked) > 0 else "WARN"
        report.add(S, "Stage 4 — Reference sequences linked", status,
                   f"{linked}/{n_sum} summaries linked",
                   hint="Run: python -m scripts.build_reference_sequences --phase 1" if int(linked) == 0 else "")

    # Stage 5: Epistasis graph built
    if n_sum > 0:
        summaries_with_epistasis = _scalar("""
            SELECT COUNT(*) FROM patent_ai_summaries
            WHERE epistatic_interactions IS NOT NULL
              AND jsonb_array_length(epistatic_interactions) > 0
        """) or 0
        status = "PASS" if n_epi > 0 else ("WARN" if int(summaries_with_epistasis) > 0 else "SKIP")
        report.add(S, "Stage 5 — Epistasis graph built", status,
                   f"{n_epi} edges  ({summaries_with_epistasis} summaries with data)",
                   hint="Run: python -m scripts.build_epistasis_graph" if n_epi == 0 and int(summaries_with_epistasis) > 0 else "")

    # Stage 6: Coverage populated
    status = "PASS" if n_cov > 0 else "WARN"
    report.add(S, "Stage 6 — Protein coverage populated", status,
               f"{n_cov:,} coverage rows",
               hint="Run: python -m DataPipeline.patent_pipeline --update-coverage" if n_cov == 0 else "")

    # Stage 7: Opportunity zones built
    status = "PASS" if n_opp > 0 else "WARN"
    report.add(S, "Stage 7 — Opportunity zones built", status,
               f"{n_opp} zones",
               hint="Run: python -m DataPipeline.patent_pipeline --build-opportunities" if n_opp == 0 else "")

    # Stage 2b: Enzyme / CRISPR multi-dimensional scores
    for grp in ["industrial_enzymes", "therapeutic_enzymes", "crispr_proteins"]:
        n_sum_grp = int(_scalar("""
            SELECT COUNT(*) FROM patents p
            JOIN patent_ai_summaries s ON s.patent_id = p.patent_id
            WHERE p.protein_type = :g
        """, {"g": grp}) or 0)
        if n_sum_grp == 0:
            report.add(S, f"Stage 2b — Enzyme scores: {grp}", "SKIP", "no summaries yet")
            continue
        n_scored = int(_scalar("""
            SELECT COUNT(*) FROM patents p
            JOIN patent_ai_summaries s ON s.patent_id = p.patent_id
            WHERE p.protein_type = :g AND s.fto_score IS NOT NULL
        """, {"g": grp}) or 0)
        pct = n_scored / n_sum_grp
        status = "PASS" if pct >= 0.8 else "WARN" if pct > 0 else "FAIL"
        report.add(S, f"Stage 2b — Enzyme scores: {grp}", status,
                   f"{n_scored}/{n_sum_grp} ({pct:.0%}) have fto_score",
                   hint=f"python -m scripts.search_patents --groups {grp} --synthesize-only --no-resume"
                        if pct < 0.8 else "")

    # Per-protein-type coverage
    if n_pat > 0:
        pt_rows = _rows("""
            SELECT p.protein_type, COUNT(DISTINCT p.patent_id) as n_patents,
                   COUNT(DISTINCT s.summary_id) as n_summarized,
                   COUNT(DISTINCT er.record_id) as n_records
            FROM patents p
            LEFT JOIN patent_ai_summaries s ON s.patent_id = p.patent_id
            LEFT JOIN patent_experimental_records er ON er.patent_id = p.patent_id
            WHERE p.protein_type IS NOT NULL
            GROUP BY p.protein_type ORDER BY n_patents DESC
        """)
        for row in pt_rows:
            ptype = row[0]
            np_, ns, nr = int(row[1]), int(row[2]), int(row[3])
            synth_pct = ns / np_ if np_ else 0
            detail = f"{np_} patents  {ns} summarized ({synth_pct:.0%})  {nr} exp records"
            status = "PASS" if synth_pct >= 0.7 else "WARN" if synth_pct > 0 else "FAIL"
            report.add(S, f"Coverage: {ptype}", status, detail,
                       hint=f"python -m DataPipeline.patent_pipeline --synthesize --protein-type {ptype}" if synth_pct < 0.7 else "")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

def _check_fields(data: Any, required: list[str]) -> list[str]:
    """Return list of missing required fields from a dict."""
    if not isinstance(data, dict):
        return required
    return [f for f in required if f not in data]


def check_api(report: Report, base_url: str) -> None:
    S = "7. API endpoints"

    # Server reachable?
    code, _ = _get(f"{base_url}/patents/summary")
    if code == 0:
        report.add(S, "Server reachable", "SKIP",
                   f"Cannot connect to {base_url}",
                   hint="Start the API server: uvicorn main:app --reload")
        return
    report.add(S, "Server reachable", "PASS", f"{base_url}")

    endpoints: list[tuple[str, str, list[str], list[str]]] = [
        # (url, name, required top-level fields, required per-item fields)
        ("/patents/summary",
         "GET /summary",
         ["status", "data"],
         ["patents", "ai_summaries", "protein_coverage", "opportunity_zones", "variants", "enrichment_scores"]),

        ("/patents/list?limit=5",
         "GET /list",
         ["status", "total", "data"],
         ["patent_number", "title", "protein_type", "fto_risk", "ai_processed", "biological_context"]),

        ("/patents/fto?organ=liver",
         "GET /fto",
         ["status", "organ", "data"],
         []),  # data may be empty if no variants

        ("/patents/opportunities?min_score=0",
         "GET /opportunities",
         ["status", "data"],
         []),

        ("/patents/heatmap",
         "GET /heatmap",
         ["status", "has_position_data", "data"],
         []),

        ("/patents/tissue-coverage?by=tissue",
         "GET /tissue-coverage (tissue)",
         ["status", "data"],
         []),

        ("/patents/tissue-coverage?by=serotype",
         "GET /tissue-coverage (serotype)",
         ["status", "data"],
         []),

        ("/patents/tissue-coverage?by=strategy",
         "GET /tissue-coverage (strategy)",
         ["status", "data"],
         []),

        ("/patents/tissue-coverage?by=target",
         "GET /tissue-coverage (target)",
         ["status", "data"],
         []),

        ("/patents/enzyme-landscape",
         "GET /enzyme-landscape",
         ["status", "data"],
         []),

        ("/patents/epistasis?min_patents=1",
         "GET /epistasis",
         ["status", "data"],
         []),

        ("/patents/enzyme-family",
         "GET /enzyme-family",
         ["status", "data"],
         []),

        ("/patents/substrate-map",
         "GET /substrate-map",
         ["status", "data"],
         []),
    ]

    for path, name, top_fields, item_fields in endpoints:
        url = base_url + path
        code, body = _get(url)

        if code == 0:
            report.add(S, name, "FAIL", "connection error",
                       hint=f"GET {url}")
            continue

        if code != 200:
            report.add(S, name, "FAIL", f"HTTP {code}",
                       hint=f"Check server logs for: GET {url}")
            continue

        if body is None:
            report.add(S, name, "FAIL", "empty/invalid JSON response")
            continue

        # Top-level fields
        missing_top = _check_fields(body, top_fields)
        if missing_top:
            report.add(S, name, "FAIL",
                       f"missing fields: {', '.join(missing_top)}")
            continue

        if body.get("status") != "ok":
            report.add(S, name, "WARN",
                       f"status={body.get('status')!r} (expected 'ok')")
            continue

        # Per-item fields
        items = body.get("data", [])
        if isinstance(items, list) and items and item_fields:
            first = items[0]
            missing_item = _check_fields(first, item_fields)
            if missing_item:
                report.add(S, name, "FAIL",
                           f"item missing fields: {', '.join(missing_item)}")
                continue

        n = len(items) if isinstance(items, list) else "n/a"
        report.add(S, name, "PASS", f"{n} items" if isinstance(n, int) else "")

    # ── Extra: specific value checks on populated endpoints ──
    _, summary = _get(f"{base_url}/patents/summary")
    if summary and isinstance(summary.get("data"), dict):
        d = summary["data"]
        if d.get("patents", 0) == 0:
            report.add(S, "summary: patents > 0", "FAIL", "no patents in DB",
                       hint="Run patent_pipeline to fetch patents")
        else:
            report.add(S, "summary: patents > 0", "PASS", f"{d['patents']:,} patents")

    _, landscape = _get(f"{base_url}/patents/enzyme-landscape")
    if landscape and landscape.get("data"):
        items = landscape["data"]
        bad_pos = [i for i in items if isinstance(i.get("position"), int) and i["position"] > 5000]
        if bad_pos:
            report.add(S, "enzyme-landscape: no hallucinated positions", "FAIL",
                       f"{len(bad_pos)} positions > 5000 in response",
                       hint="BETWEEN 1 AND 5000 filter missing in routes/patents.py")
        else:
            report.add(S, "enzyme-landscape: no hallucinated positions", "PASS",
                       f"{len(items)} positions, all ≤ 5000")

    _, epistasis = _get(f"{base_url}/patents/epistasis")
    if epistasis and epistasis.get("data"):
        items = epistasis["data"]
        no_ref = [i for i in items if not i.get("reference_name") and not i.get("uniprot_id")]
        pct = len(no_ref) / len(items) if items else 0
        status = "WARN" if pct > 0.3 else "PASS"
        report.add(S, "epistasis: reference linkage rate", status,
                   f"{len(items)-len(no_ref)}/{len(items)} edges have reference name/uniprot",
                   hint="Run: python -m scripts.build_epistasis_graph  (backfills ref_id)" if pct > 0.3 else "")

    _, patents = _get(f"{base_url}/patents/list?limit=20&target=kinase")
    if patents and isinstance(patents.get("data"), list):
        report.add(S, "list: target filter works", "PASS",
                   f"{patents['total']} patents matching 'kinase'")
    elif patents is not None:
        report.add(S, "list: target filter works", "WARN",
                   "target param returned unexpected shape")

    # ── Enzyme score fields present in FTO response ──
    SCORE_FIELDS = ["fto_score", "fto_score_rationale",
                    "commercial_opportunity", "commercial_opportunity_rationale",
                    "engineering_tractability", "engineering_tractability_rationale"]
    _, fto_resp = _get(f"{base_url}/patents/fto?organ=liver")
    if fto_resp and isinstance(fto_resp.get("data"), list) and fto_resp["data"]:
        first = fto_resp["data"][0]
        missing_score = [f for f in SCORE_FIELDS if f not in first]
        if missing_score:
            report.add(S, "fto: enzyme score fields in response", "FAIL",
                       f"missing: {', '.join(missing_score)}",
                       hint="FTOPoint model in routes/patents.py is missing the new score fields")
        else:
            scored = [i for i in fto_resp["data"] if i.get("fto_score") is not None]
            report.add(S, "fto: enzyme score fields in response", "PASS",
                       f"{len(scored)}/{len(fto_resp['data'])} items have fto_score populated")
    elif fto_resp and fto_resp.get("status") == "ok":
        report.add(S, "fto: enzyme score fields in response", "SKIP",
                   "no FTO items returned (no variants in DB)")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="Patent pipeline end-to-end audit")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000",
                        help="Base URL of the running FastAPI server (default: http://127.0.0.1:8000)")
    parser.add_argument("--skip-api", action="store_true",
                        help="Skip API endpoint tests (DB-only audit)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON instead of coloured text")
    args = parser.parse_args()

    report = Report()

    # 1. Connectivity (gate all DB checks)
    db_ok = check_connectivity(report)
    if not db_ok:
        print_report(report, args.json)
        return 1

    # 2–6. DB checks
    check_schema(report)
    counts = check_counts(report)
    check_quality(report, counts)
    check_integrity(report, counts)
    check_pipeline_flow(report, counts)

    # 7. API checks
    if not args.skip_api:
        check_api(report, args.api_url.rstrip("/"))

    print_report(report, args.json)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
