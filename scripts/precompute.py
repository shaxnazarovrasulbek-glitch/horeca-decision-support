"""Store the slow results (forecast back-tests, waste simulation) for the default demo dataset,
so the app opens quickly on a small cloud server. Re-run after changing the models or the data generator.

    python scripts/precompute.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from horeca_dss import forecasting, operations, precompute  # noqa: E402
from horeca_dss.data.loader import load_generated  # noqa: E402

EVAL_END = "2026-10-15"   # keep in sync with app/ui.py

if __name__ == "__main__":
    ds = load_generated(seed=42, end=EVAL_END, days=365)
    for target in ("revenue", "covers"):
        print(precompute.save(f"backtest_{target}", ds.dataset_id, forecasting.backtest(ds.sales, ds.calendar, target)))
    print(precompute.save("waste_backtest", ds.dataset_id,
                          operations.waste_backtest(ds.sales, ds.calendar, ds.recipes, ds.ingredients)))
    print("code version", precompute.code_version())
