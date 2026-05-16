"""
Patent Intelligence CLI — search, summarize, and store protein engineering patents.

Data sources:
  uspto  — USPTO PatentsView REST API (FREE, no key needed, works immediately)
  wipo   — WIPO PATENTSCOPE REST API  (free account, PCT/WO patents)
  lens   — Lens.org aggregator        (USPTO+WIPO+EPO+CN, requires approved key)

Usage (from backend/):

    # List all available protein groups
    python -m scripts.search_patents --list-groups

    # Default run: USPTO + WIPO, AAV capsid, 20 patents (smoke test)
    python -m scripts.search_patents --groups aav_capsid --limit 20

    # USPTO only (fastest, no setup required)
    python -m scripts.search_patents --groups aav_capsid --sources uspto

    # All three sources (when Lens.org key is approved)
    python -m scripts.search_patents --groups aav_capsid --sources uspto wipo lens

    # Multiple protein groups
    python -m scripts.search_patents --groups aav_capsid crispr_proteins monoclonal_antibodies

    # All groups
    python -m scripts.search_patents --all-groups --limit 200

    # Use Anthropic Claude Haiku instead of Groq
    python -m scripts.search_patents --groups aav_capsid --provider anthropic

    # Resume interrupted run (already-processed patents are skipped)
    python -m scripts.search_patents --groups aav_capsid --resume

    # Skip LLM synthesis (load patents into DB only, no summarization)
    python -m scripts.search_patents --groups aav_capsid --no-synthesis

Environment variables (.env):
    GROQ_API_KEY      — Groq free tier LLM (default)   https://console.groq.com
    ANTHROPIC_API_KEY — Claude Haiku (--provider anthropic)
    OPENAI_API_KEY    — GPT-4o-mini   (--provider openai)

    LENS_API_KEY      — Only needed when --sources includes lens
    WIPO_API_TOKEN    — Optional; WIPO works without it at lower rate limits
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
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

PROVIDER_ENV_MAP = {
    "groq":      "GROQ_API_KEY",
    "groq2":     "GROQ2_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai":    "OPENAI_API_KEY",
}


def _check_env(provider: str, sources: list) -> None:
    key_var = PROVIDER_ENV_MAP[provider]
    if not os.environ.get(key_var, "").strip():
        log.error(
            "%s is not set.\n"
            "  Groq (free): https://console.groq.com\n"
            "  Add to .env: %s=<your-key>",
            key_var, key_var,
        )
        sys.exit(1)

    if "epo" in sources and (
        not os.environ.get("EPO_OPS_CLIENT_ID",     "").strip() or
        not os.environ.get("EPO_OPS_CLIENT_SECRET", "").strip()
    ):
        log.error(
            "EPO_OPS_CLIENT_ID / EPO_OPS_CLIENT_SECRET not set.\n"
            "  1. Register free at https://developers.epo.org\n"
            "  2. My Apps → Add new app\n"
            "  3. Add to .env:\n"
            "     EPO_OPS_CLIENT_ID=<Consumer Key>\n"
            "     EPO_OPS_CLIENT_SECRET=<Consumer Secret>"
        )
        sys.exit(1)

    if "lens" in sources and not os.environ.get("LENS_API_KEY", "").strip():
        log.error(
            "LENS_API_KEY is not set but --sources includes 'lens'.\n"
            "  Either remove 'lens' from --sources, or add LENS_API_KEY to .env.\n"
            "  USPTO + WIPO work without any key — use: --sources uspto wipo"
        )
        sys.exit(1)


def _print_results(results: list) -> None:
    print("\n" + "=" * 65)
    print("Patent Intelligence Run — Summary")
    print("=" * 65)

    total_fetched = total_summ = total_zones = total_errors = 0
    for r in results:
        sources_str = "+".join(s.upper() for s in r.get("sources", []))
        print(f"\n  [{sources_str}] {r['group']} — {r['label']}")
        print(f"    Patents fetched:    {r['fetched']}")
        print(f"    Claims retrieved:  {r.get('claims_fetched', 0)}")
        print(f"    Summarized:        {r['summarized']}")
        print(f"    Skipped (cached):  {r['skipped']}")
        print(f"    Errors:            {r['errors']}")
        print(f"    Opportunity zones: {r['opportunity_zones']}")
        total_fetched += r["fetched"]
        total_summ    += r["summarized"]
        total_zones   += r["opportunity_zones"]
        total_errors  += r["errors"]

    print(f"\n  TOTAL  fetched={total_fetched}  summarized={total_summ}"
          f"  zones={total_zones}  errors={total_errors}")
    print()
    print("Query the results:")
    print("  -- Patent landscape overview")
    print("  SELECT p.title, s.fto_risk, s.opportunity_notes")
    print("    FROM patents p JOIN patent_ai_summaries s USING (patent_id)")
    print("    ORDER BY s.fto_risk, p.publication_date DESC;")
    print()
    print("  -- Top engineering opportunities")
    print("  SELECT name, description, opportunity_score, strategy_notes")
    print("    FROM patent_opportunity_zones")
    print("    ORDER BY opportunity_score DESC;")


def main() -> None:
    from DataPipeline.patent_pipeline import PROTEIN_GROUPS, list_protein_groups

    parser = argparse.ArgumentParser(
        description="Search and summarize protein engineering patents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Group selection
    grp = parser.add_mutually_exclusive_group(required=False)
    grp.add_argument("--groups", "-g", nargs="+", metavar="GROUP",
                     help="One or more protein group keys")
    grp.add_argument("--all-groups", action="store_true",
                     help="Run all available protein groups")
    parser.add_argument("--list-groups", action="store_true",
                        help="Print available groups and exit")

    # Source selection
    parser.add_argument(
        "--sources", nargs="+",
        default=None,
        choices=["epo", "lens", "uspto"],
        metavar="SOURCE",
        help="Data sources for fetching: epo lens (default: epo). "
             "In --synthesize-only mode, filters which DB patents to process "
             "(epo=EPO_ prefix, uspto=USPTO_ prefix, lens=all others). "
             "Omit to process all sources in --synthesize-only mode.",
    )

    # LLM config
    parser.add_argument("--provider", default="groq",
                        choices=["groq", "groq2", "anthropic", "openai"],
                        help="LLM provider (default: groq)")
    parser.add_argument("--model", default=None,
                        help="Override default model for chosen provider")

    # Pipeline config
    parser.add_argument("--limit", type=int, default=10_000,
                        help="Max patents per group per source (default: 10000 = effectively unlimited)")
    parser.add_argument("--resume", action="store_true", default=True,
                        help="Skip patents already in DB (default: on)")
    parser.add_argument("--no-resume", action="store_true",
                        help="Re-summarize patents already in DB")
    parser.add_argument("--no-synthesis", "--harvest-only", action="store_true",
                        help="Store patent metadata only — skip all LLM calls (fast, free)")
    parser.add_argument("--synthesize-only", action="store_true",
                        help="Re-run LLM on patents already in DB — no new fetching. "
                             "Use with --no-resume to reprocess already-summarized patents. "
                             "Useful for backfilling claims text or re-extracting positions.")
    parser.add_argument("--since-year", type=int, default=None, metavar="YEAR",
                        help="Only summarize patents published in YEAR or later (harvest still gets all)")

    args = parser.parse_args()

    if args.list_groups:
        list_protein_groups()
        return

    if args.all_groups:
        selected_groups = list(PROTEIN_GROUPS.keys())
    elif args.groups:
        unknown = [g for g in args.groups if g not in PROTEIN_GROUPS]
        if unknown:
            log.error("Unknown groups: %s", unknown)
            list_protein_groups()
            sys.exit(1)
        selected_groups = args.groups
    else:
        log.error("Specify --groups <GROUP ...>, --all-groups, or --list-groups")
        parser.print_help()
        sys.exit(1)

    synthesize_only = getattr(args, "synthesize_only", False)
    # In fetch mode default sources to ["epo"] when not specified
    effective_sources = args.sources if args.sources is not None else ([] if synthesize_only else ["epo"])

    if not args.no_synthesis:
        _check_env(args.provider, effective_sources)

    log.info("Groups: %s | Sources: %s | Provider: %s | Limit: %d/source",
             selected_groups, effective_sources or "all (synthesize-only)",
             "none (harvest-only)" if args.no_synthesis else args.provider,
             args.limit)

    from DataPipeline.llm_client import LLMClient
    from DataPipeline.patent_pipeline import PatentPipeline

    harvest_only    = args.no_synthesis
    # In synthesize-only mode: None means no filter (process all sources in DB)
    fetch_sources      = [] if synthesize_only else effective_sources
    synthesize_sources = args.sources if synthesize_only else None

    llm = None if harvest_only else LLMClient(provider=args.provider, model=args.model)

    if harvest_only:
        log.info("Harvest-only mode: fetching and storing patent metadata, no LLM calls.")
    if synthesize_only:
        src_label = "+".join(s.upper() for s in (synthesize_sources or []))
        log.info("Synthesize-only mode: re-running LLM on existing DB patents%s, no new fetching.",
                 f" (source filter: {src_label})" if synthesize_sources else "")
    if args.since_year:
        log.info("Synthesis filter: only patents published >= %d", args.since_year)

    pipeline = PatentPipeline(
        protein_groups     = selected_groups,
        sources            = fetch_sources,
        synthesize_sources = synthesize_sources,
        llm                = llm,
        max_per_source     = args.limit,
        skip_existing      = not args.no_resume,
        run_synthesis      = not harvest_only,
        since_year         = args.since_year,
    )

    results = pipeline.run()
    _print_results(results)


if __name__ == "__main__":
    main()
