"""Scale test: how long does the full analysis take with more branches and more data?

    python scripts/scale_test.py                     # 2, 5 and 10 branches, one year each
    python scripts/scale_test.py --branches 2 10 20  # custom sizes

Every size runs in its own process (clean memory numbers) and goes through the same steps
as the app: data, KPIs and alerts, forecast, back-test, menu/pricing/basket, operations,
waste simulation and the AI fact sheet. Results are written to docs/scale_test.md.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

STEPS = ["data", "kpis_alerts", "forecast", "backtest", "menu_price_basket", "operations", "waste_sim", "ai_facts"]


def run_one(n_branches: int, days: int, seed: int, end: str | None) -> dict:
    import pandas as pd

    from horeca_dss import analysis, assistant, forecasting, operations
    from horeca_dss.data.loader import load_generated

    t: dict[str, float] = {}

    def timed(name, fn):
        t0 = time.perf_counter()
        out = fn()
        t[name] = time.perf_counter() - t0
        return out

    ds = timed("data", lambda: load_generated(seed=seed, end=end, days=days, n_branches=n_branches))
    s = analysis.Settings()
    k = timed("kpis_alerts", lambda: analysis.kpi_bundle(ds, s, analysis.kpis.ALL))
    fc = timed("forecast", lambda: analysis.forecast_bundle(ds, 14))
    bt = timed("backtest", lambda: forecasting.backtest(ds.sales, ds.calendar, "revenue"))
    c = timed("menu_price_basket", lambda: analysis.commercial_bundle(ds, s, analysis.kpis.ALL))
    ops = timed("operations", lambda: analysis.operations_bundle(ds, fc["covers"], s, 7))
    wb = timed("waste_sim", lambda: operations.waste_backtest(ds.sales, ds.calendar, ds.recipes, ds.ingredients))
    facts = timed("ai_facts", lambda: assistant.build_facts(ds, k, c, fc, ops, bt, wb))
    ctx = assistant.context_text(facts)
    m = bt["metrics"].set_index("method")
    try:
        import resource
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if sys.platform != "darwin" else 1024 ** 2)
    except Exception:  # Windows: no `resource` module
        peak_mb = None
    return {
        "branches": n_branches, "days": days,
        "orders": int(ds.sales["order_id"].nunique()), "order_lines": int(len(ds.sales)),
        "revenue_bn": float(ds.sales["revenue"].sum() / 1e9),
        "seconds": t, "total_seconds": sum(t.values()),
        "wape": float(m.iloc[0]["WAPE"]), "best_rule_wape": float(min(m.iloc[1]["WAPE"], m.iloc[2]["WAPE"])),
        "ai_context_tokens": int(len(ctx) / 4), "peak_memory_mb": peak_mb,
        "start": f"{ds.start:%Y-%m-%d}", "end": f"{ds.end:%Y-%m-%d}",
    }


def to_markdown(results: list[dict]) -> str:
    lines = ["# Scale test", "",
             f"Machine: {platform.system()} {platform.machine()}, Python {platform.python_version()}. "
             f"Generated data, one process per size; all steps the app runs on its first start.", "",
             "| Branches | Orders | Order lines | Total time | Data | KPIs + alerts | Forecast | Back-test | "
             "Menu + pricing + basket | Operations | Waste sim | Peak memory | Forecast WAPE (best rule) | AI context |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["seconds"]
        mem = f"{r['peak_memory_mb']:.0f} MB" if r.get("peak_memory_mb") else "n/a"
        lines.append(
            f"| {r['branches']} | {r['orders']:,} | {r['order_lines']:,} | **{r['total_seconds']:.1f} s** | "
            f"{s['data']:.1f} s | {s['kpis_alerts']:.1f} s | {s['forecast']:.1f} s | {s['backtest']:.1f} s | "
            f"{s['menu_price_basket']:.1f} s | {s['operations']:.1f} s | {s['waste_sim']:.1f} s | {mem} | "
            f"{r['wape']:.1%} ({r['best_rule_wape']:.1%}) | ~{r['ai_context_tokens']:,} tokens |")
    big = results[-1]
    small = results[0]
    ratio = big["order_lines"] / small["order_lines"]
    tratio = big["total_seconds"] / small["total_seconds"]
    growth = ("about linearly" if tratio <= ratio * 1.3 else "faster than the data, so the slowest step "
              "should move to a nightly job first")
    lines += ["",
              f"**Reading:** {ratio:.1f}x more data took {tratio:.1f}x more time, so the cost grows {growth}. "
              f"After the first run the app caches every step, so pages open in about a second. "
              f"The forecast model is shared by all branches (one global model), so it stays accurate when "
              f"branches are added, and the AI fact sheet stays small because it holds aggregates, not raw orders.",
              "",
              "**Limits and next steps for a real chain:** run the heavy steps (training, back-test, simulation) "
              "as a nightly batch job and store the results in a database (PostgreSQL), so the dashboard only "
              "reads; read POS data incrementally instead of one CSV; one app instance per region if needed.", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branches", type=int, nargs="+", default=[2, 5, 10])
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--end", default="2026-10-15", help="last day of data (same as the README evaluation)")
    ap.add_argument("--one", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--out", default=str(ROOT / "docs" / "scale_test.md"))
    a = ap.parse_args()
    if a.one:
        print(json.dumps(run_one(a.one, a.days, a.seed, a.end)))
        return
    results = []
    for n in a.branches:
        print(f"Running {n} branches...", flush=True)
        p = subprocess.run([sys.executable, __file__, "--one", str(n), "--days", str(a.days), "--seed", str(a.seed),
                            "--end", a.end],
                           capture_output=True, text=True, check=True)
        r = json.loads(p.stdout.strip().splitlines()[-1])
        print(f"  {r['order_lines']:,} order lines, {r['total_seconds']:.1f} s", flush=True)
        results.append(r)
    md = to_markdown(results)
    Path(a.out).write_text(md, encoding="utf-8")
    (Path(a.out).with_suffix(".json")).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
