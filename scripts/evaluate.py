"""Reproduce the evaluation numbers used in the internship report.

    python scripts/evaluate.py            # default demo data (seed 42, data up to yesterday)
    python scripts/evaluate.py --seed 7 --end 2026-10-15
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from horeca_dss import forecasting, operations  # noqa: E402
from horeca_dss.analysis import Settings, commercial_bundle, forecast_bundle, operations_bundle  # noqa: E402
from horeca_dss.data.loader import load_generated  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--end", default=None, help="last day of data, YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--out", default=str(ROOT / "docs" / "results.md"))
    a = ap.parse_args()

    ds = load_generated(seed=a.seed, end=a.end, days=a.days)
    st = Settings()
    lines = [f"# Evaluation results", "", f"Data: generated, seed {a.seed}, {ds.start:%Y-%m-%d} to {ds.end:%Y-%m-%d}", ""]

    lines.append("## Forecast accuracy (rolling-origin back-test, 8 origins x 14 days)")
    for target in ("revenue", "covers"):
        bt = forecasting.backtest(ds.sales, ds.calendar, target)
        lines.append(f"\n**{target}** - improvement vs best rule of thumb: {bt['improvement_vs_best_baseline']:+.1%}\n")
        lines.append(bt["metrics"].round(4).to_string(index=False))
        lines.append("")
        lines.append(bt["by_day_type"].round(4).to_string(index=False))

    c = commercial_bundle(ds, st)
    p = c["prices"]
    act = p[p["recommended_price"] != p["current_price"]]
    lines += ["", "## Pricing", f"Confident price changes: {len(act)}, expected margin gain "
              f"{act['cm_uplift_month'].sum():,.0f} UZS / month; price tests proposed: {(p['confidence'] == 'Low').sum()}"]
    lines += ["", "## Upsell (top 5, 10% acceptance)",
              c["upsell"].head(5)[["script", "confidence", "lift", "extra_cm_month"]].round(3).to_string(index=False)]

    fc = forecast_bundle(ds, 14)
    ops = operations_bundle(ds, fc["covers"], st)
    comp = ops["staff_comparison"]
    lines += ["", "## Staffing (next 7 days vs fixed schedule)", comp.to_string(index=False)]
    wb = operations.waste_backtest(ds.sales, ds.calendar, ds.recipes, ds.ingredients)
    lines += ["", f"## Perishable waste simulation ({wb['weeks']} weeks)",
              wb["summary"].round(3).to_string(index=False), f"\nWaste reduction: {wb['waste_reduction']:.1%}"]

    text = "\n".join(lines)
    Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    print(f"\nSaved to {a.out}")


if __name__ == "__main__":
    pd.set_option("display.width", 160)
    main()
