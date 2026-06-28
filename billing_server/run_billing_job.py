"""Run quarterly or annual platform billing job."""

import argparse
from datetime import date

from billing_schedule import BILLING_ANNUAL, BILLING_QUARTERLY, quarter_bounds, year_bounds
from config import PLATFORM_INVOICE_DIR
from platform_billing import generate_platform_invoices


def main():
    parser = argparse.ArgumentParser(description="Generate KorraOne platform invoices")
    parser.add_argument("--output", default=None, help=f"Output dir (default: {PLATFORM_INVOICE_DIR})")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--quarter", type=int, choices=[1, 2, 3, 4], help="Calendar quarter (quarterly mode)")
    parser.add_argument(
        "--mode",
        choices=[BILLING_QUARTERLY, BILLING_ANNUAL],
        default=BILLING_QUARTERLY,
        help="Bill quarterly (default) or annual accounts",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Replace existing invoices for the same account and month range",
    )
    args = parser.parse_args()

    if args.mode == BILLING_ANNUAL:
        start, end = year_bounds(args.year)
        label = f"year {args.year}"
    else:
        if args.quarter is None:
            parser.error("--quarter is required for quarterly mode")
        start, end = quarter_bounds(args.year, args.quarter)
        label = f"Q{args.quarter} {args.year}"

    output = args.output or PLATFORM_INVOICE_DIR
    created = generate_platform_invoices(
        output_dir=output,
        cycle_start=start,
        cycle_end=end,
        billing_mode=args.mode,
        regenerate=args.regenerate,
    )
    print(f"Generated {len(created)} platform invoice(s) for {label} ({args.mode})")
    for item in created:
        months = item.get("months", "")
        suffix = f" [{months}]" if months else ""
        print(f"  {item['email']}: ${item['total']} ({item['invoice_number']}){suffix} -> {item['pdf']}")


if __name__ == "__main__":
    main()
