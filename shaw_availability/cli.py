from __future__ import annotations

import argparse
import logging
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from . import api_client, collector, config, persistence, report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan Shaw IMAX showtime seat availability.")
    parser.add_argument(
        "--days",
        type=int,
        default=config.SCAN_DAYS_DEFAULT,
        help=f"Number of days to scan forward (default: {config.SCAN_DAYS_DEFAULT}).",
    )
    parser.add_argument(
        "--start-date",
        type=_parse_date,
        default=None,
        help="Start date as YYYY-MM-DD (default: today).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=config.OUTPUT_DIR,
        help=f"Directory to write results to (default: {config.OUTPUT_DIR}).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args(argv)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    start_date = args.start_date or date.today()

    session = api_client.build_session()
    result = collector.run_scan(session, start_date=start_date, max_days=args.days)

    run_dir = persistence.make_run_dir(args.output_dir, datetime.now(timezone.utc))
    persistence.save_scan_result_json(result, run_dir)
    persistence.save_shows_csv(result, run_dir)
    persistence.save_days_csv(result, run_dir)
    persistence.append_history_csv(result, args.output_dir)

    report_data = report.build_report(result)
    report.print_report(report_data)

    if result.failed_calls:
        counts = Counter(f.kind for f in result.failed_calls)
        logging.warning("scan completed with failed calls: %s", dict(counts))

    return 0
