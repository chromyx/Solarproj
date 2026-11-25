"""Independent cross-checks of collected data against figures ALPEX publishes itself."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session, sessionmaker

from powerdesk.canonical import current_values_query
from powerdesk.ingestion import alpex_web

CENT = Decimal("0.01")


def monthly_averages(session_factory: sessionmaker[Session], zone: str,
                     product: str = "DAM") -> dict[str, tuple[Decimal, int]]:
    """Simple mean of the current hourly prices per local calendar month.

    Uses every published value, including intervals we mark BAD because their *hour mapping* is
    ambiguous: ALPEX's own monthly averages are computed over the values it published.
    """
    sums: dict[str, tuple[Decimal, int]] = {}
    with session_factory() as s:
        for row in s.scalars(current_values_query(alpex_web.SOURCE_NAME, zone, product, "price")):
            k = row.delivery_day_local.strftime("%Y-%m")
            tot, n = sums.get(k, (Decimal(0), 0))
            sums[k] = (tot + row.value, n + 1)
    return {k: (tot / n, n) for k, (tot, n) in sorted(sums.items())}


def monthly_cross_check(session_factory: sessionmaker[Session], reference: Path,
                        tolerance: Decimal = CENT) -> list[dict[str, Any]]:
    refs = yaml.safe_load(reference.read_text(encoding="utf-8"))["months"]
    computed = {z: monthly_averages(session_factory, z) for z in {r["zone"] for r in refs}}
    out = []
    for ref in refs:
        got = computed[ref["zone"]].get(ref["month"])
        if got is None:
            continue
        avg, n = got
        reported = Decimal(str(ref["avg_eur_mwh"]))
        diff = abs(avg - reported)
        match = diff <= tolerance
        out.append({"month": ref["month"], "zone": ref["zone"], "computed": str(avg.quantize(CENT)),
                    "reported": str(reported), "hours": n, "diff": str(diff.quantize(Decimal("0.001"))),
                    "match": match, "explained": None if match else ref.get("explained"),
                    "source": ref["source"]})
    return out


def cross_check_passes(rows: list[dict[str, Any]]) -> bool:
    return all(r["match"] or r["explained"] for r in rows)
