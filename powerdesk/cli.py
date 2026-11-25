"""Command line: `powerdesk <command>`. Analysis only; there is no order-entry command."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from powerdesk.canonical import coverage_by_day
from powerdesk.db.models import MarketIntervalValue
from powerdesk.db.session import make_engine, make_session_factory, upgrade_to_head
from powerdesk.ingestion import alpex_web
from powerdesk.ingestion.base import PoliteHttp
from powerdesk.settings import EXECUTION_MODE


def _date(s: str) -> date:
    return date.fromisoformat(s)


def cmd_db_upgrade(_: argparse.Namespace) -> int:
    upgrade_to_head()
    print("database schema at head")
    return 0


def cmd_ingest_alpex(args: argparse.Namespace) -> int:
    sf = make_session_factory(make_engine())
    end = args.to or (datetime.now(UTC).date() - timedelta(days=1))
    errors = 0

    def report(r: alpex_web.DayResult) -> None:
        nonlocal errors
        st = r.stats
        if r.error:
            errors += 1
        print(f"{r.day} rows={r.rows} "
              f"new={st.inserted_new if st else 0} rev={st.inserted_revision if st else 0} "
              f"unchanged={st.unchanged if st else 0} warn={st.warn if st else 0} "
              f"bad={st.bad if st else 0} issues={len(r.issues)} error={r.error or '-'}"
              + (f" | e.g. {'; '.join(r.issues[:2])}" if r.issues else ""), flush=True)

    http = PoliteHttp(min_interval_s=args.min_interval)
    try:
        res = alpex_web.ingest_range(sf, args.from_, end, product=args.product, http=http,
                                     refresh=args.refresh, on_day=report)
    finally:
        http.close()
    print(f"done: {len(res)} day(s) processed, {errors} error(s)")
    return 1 if errors else 0


def cmd_sources_status(args: argparse.Namespace) -> int:
    sf = make_session_factory(make_engine())
    m = MarketIntervalValue
    with sf() as s:
        bounds = s.execute(
            select(func.min(m.delivery_day_local), func.max(m.delivery_day_local),
                   func.max(m.ingested_at_utc))
            .where(m.source_name == alpex_web.SOURCE_NAME, m.product == args.product,
                   m.market_zone == args.zone, m.quantity == "price")
        ).one()
        if bounds[0] is None:
            print(f"{alpex_web.SOURCE_NAME} {args.zone} {args.product}: no data")
            return 1
        first, last, last_ingest = bounds
        cov = coverage_by_day(s, alpex_web.SOURCE_NAME, args.zone, args.product, "price", first, last)
        warn = s.scalar(select(func.count()).select_from(m).where(
            m.source_name == alpex_web.SOURCE_NAME, m.market_zone == args.zone,
            m.product == args.product, m.quality_status == "WARN"))
    incomplete = [c for c in cov if not c.complete]
    expected = sum(c.expected for c in cov)
    received = sum(c.received for c in cov)
    stale_days = (datetime.now(UTC).date() - last).days
    print(f"source={alpex_web.SOURCE_NAME} zone={args.zone} product={args.product} "
          f"licence={alpex_web.LICENSE_STATUS}")
    print(f"delivery days {first} .. {last} ({len(cov)} days); last ingest {last_ingest:%Y-%m-%d %H:%M} UTC")
    print(f"hourly prices expected={expected} received={received} "
          f"complete_days={len(cov) - len(incomplete)} incomplete_days={len(incomplete)} "
          f"warn_values={warn}")
    print(f"freshness: latest delivery day is {stale_days} day(s) before today (UTC)")
    for c in incomplete[:50]:
        print(f"  incomplete {c.day}: received {c.received}/{c.expected}, bad={c.bad}")
    return 0


def monthly_averages(zone: str, product: str = "DAM") -> dict[str, tuple[Decimal, int]]:
    """Simple arithmetic mean of current hourly prices per calendar month (local delivery day)."""
    from powerdesk.canonical import current_values_query

    sf = make_session_factory(make_engine())
    sums: dict[str, tuple[Decimal, int]] = {}
    with sf() as s:
        for row in s.scalars(current_values_query(alpex_web.SOURCE_NAME, zone, product, "price")):
            k = row.delivery_day_local.strftime("%Y-%m")
            tot, n = sums.get(k, (Decimal(0), 0))
            sums[k] = (tot + row.value, n + 1)
    return {k: (tot / n, n) for k, (tot, n) in sorted(sums.items())}


def cmd_check_monthly(args: argparse.Namespace) -> int:
    import yaml

    ref_path = Path(args.reference)
    refs = yaml.safe_load(ref_path.read_text(encoding="utf-8"))["months"] if ref_path.exists() else []
    ref_by = {(r["month"], r["zone"]): r for r in refs}
    ok = True
    for zone in ("AL", "KS"):
        for month, (avg, n) in monthly_averages(zone).items():
            ref = ref_by.get((month, zone))
            line = f"{zone} {month} computed_avg={avg:.2f} EUR/MWh hours={n}"
            if ref is not None:
                diff = abs(avg - Decimal(str(ref["avg_eur_mwh"])))
                verdict = "MATCH" if diff <= Decimal(args.tolerance) else "MISMATCH"
                ok &= verdict == "MATCH"
                line += f" reported={ref['avg_eur_mwh']} diff={diff:.3f} {verdict}"
            print(line)
    print("cross-check:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def cmd_report_earnings(args: argparse.Namespace) -> int:
    from powerdesk.analysis.report import write_earnings_report

    path = write_earnings_report(Path(args.plant), Path(args.out_dir))
    print(f"report written: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="powerdesk", description=f"POWERDESK ({EXECUTION_MODE})")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    db = sub.add_parser("db").add_subparsers(dest="db_cmd", required=True)
    db.add_parser("upgrade", help="apply migrations").set_defaults(func=cmd_db_upgrade)

    ing = sub.add_parser("ingest").add_subparsers(dest="ing_cmd", required=True)
    a = ing.add_parser("alpex", help="collect ALPEX public results one delivery day at a time")
    a.add_argument("--from", dest="from_", type=_date, required=True)
    a.add_argument("--to", type=_date, help="default: yesterday (UTC)")
    a.add_argument("--product", default="DAM", choices=sorted(alpex_web.TABLE_ID_BY_PRODUCT))
    a.add_argument("--refresh", action="store_true", help="re-fetch complete days (revisions kept)")
    a.add_argument("--min-interval", type=float, default=3.0, help="seconds between requests")
    a.set_defaults(func=cmd_ingest_alpex)

    src = sub.add_parser("sources").add_subparsers(dest="src_cmd", required=True)
    st = src.add_parser("status")
    st.add_argument("--zone", default="AL")
    st.add_argument("--product", default="DAM")
    st.set_defaults(func=cmd_sources_status)

    chk = sub.add_parser("check").add_subparsers(dest="chk_cmd", required=True)
    mo = chk.add_parser("monthly", help="compare monthly averages with ALPEX monthly reports")
    mo.add_argument("--reference", default="data/reference/alpex_monthly_reported.yaml")
    mo.add_argument("--tolerance", default="0.01", help="EUR/MWh")
    mo.set_defaults(func=cmd_check_monthly)

    rep = sub.add_parser("report").add_subparsers(dest="rep_cmd", required=True)
    er = rep.add_parser("earnings", help="'what would the plant have earned' report")
    er.add_argument("--plant", default="config/plant.yaml")
    er.add_argument("--out-dir", default="reports")
    er.set_defaults(func=cmd_report_earnings)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    rc: int = args.func(args)
    return rc


if __name__ == "__main__":
    sys.exit(main())
