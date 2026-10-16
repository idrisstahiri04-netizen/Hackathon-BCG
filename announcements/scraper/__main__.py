import argparse
import logging
import sys

from .pipeline import run


def main():
    ap = argparse.ArgumentParser(description="Scrape Kenyan government announcements for food-shortage signals.")
    ap.add_argument("--sources", help="comma-separated source_ids from sources.yaml (default: all, by priority)")
    ap.add_argument("--test", type=int, metavar="N",
                    help="test run: at most N candidate items per source, spread across keywords")
    ap.add_argument("--from", dest="date_from", help="start date YYYY-MM-DD (default: sources.yaml)")
    ap.add_argument("--to", dest="date_to", help="end date YYYY-MM-DD (default: today)")
    ap.add_argument("--full", action="store_true",
                    help="ignore the incremental state: re-scrape the whole window for the selected sources")
    ap.add_argument("--fetch-only", action="store_true",
                    help="only download and store the articles (.cache/docs/); no analysis, no output")
    ap.add_argument("--rebuild", action="store_true",
                    help="no downloading: analyse the stored articles and rewrite output/")
    ap.add_argument("--refresh", action="store_true", help="ignore the download cache and re-download")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if a.fetch_only and a.rebuild:
            sys.exit("--fetch-only and --rebuild are opposites; use one.")
        out = run(a.sources.split(",") if a.sources else None, a.test, a.refresh, a.date_from, a.date_to, a.full,
                  a.fetch_only, a.rebuild)
    except PermissionError as e:
        sys.exit(f"Cannot write {e.filename}: close it in Excel (or any other program) and run again.")
    print(out["report"])


if __name__ == "__main__":
    main()
