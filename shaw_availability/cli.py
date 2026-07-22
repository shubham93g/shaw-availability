from __future__ import annotations

import argparse
import logging
from collections import Counter
from datetime import date, datetime

from . import api_client, collector, config, persistence, report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan Shaw IMAX showtime seat availability.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan showtimes and save scan_result.json.")
    scan_parser.add_argument(
        "--days",
        type=int,
        default=config.SCAN_DAYS_DEFAULT,
        help=f"Number of days to scan forward (default: {config.SCAN_DAYS_DEFAULT}).",
    )
    scan_parser.add_argument(
        "--start-date",
        type=_parse_date,
        default=None,
        help="Start date as YYYY-MM-DD (default: today).",
    )
    scan_parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")

    report_parser = subparsers.add_parser(
        "report", help="Generate report.txt/index.html from an existing scan_result.json."
    )
    report_parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")

    return parser.parse_args(argv)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _run_scan(args: argparse.Namespace) -> None:
    start_date = args.start_date or date.today()

    session = api_client.build_session()
    result = collector.run_scan(session, start_date=start_date, max_days=args.days)

    persistence.save_scan_result_json(result)

    if result.failed_calls:
        counts = Counter(f.kind for f in result.failed_calls)
        logging.warning("scan completed with failed calls: %s", dict(counts))


def _run_report(args: argparse.Namespace) -> None:
    result = persistence.load_scan_result_json()

    report_data = report.build_report(result)
    report_text = report.render_report_text(report_data)
    print(report_text)

    persistence.save_report_txt(report_text)
    persistence.save_report_html(report.render_report_html(report_data.generated_at, report_text))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "scan":
        _run_scan(args)
    else:
        _run_report(args)

    return 0
