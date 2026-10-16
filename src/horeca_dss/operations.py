"""Operations: staff scheduling and ingredient purchasing driven by the forecast."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data.loader import daily_totals
from .forecasting import DemandForecaster, item_forecast, item_mix


@dataclass
class StaffStandards:
    covers_per_waiter_hour: float = 12.0   # guests one waiter can serve per hour
    covers_per_cook_hour: float = 18.0     # guests one cook can serve per hour
    min_waiters: int = 1
    min_cooks: int = 1
    hourly_wage: float = 22000.0           # UZS per staff-hour (illustrative)


def staffing_plan(hourly: pd.DataFrame, std: StaffStandards) -> pd.DataFrame:
    """`hourly` has date, branch, hour, value (= forecast guests in that hour)."""
    p = hourly.copy()
    p["guests"] = p["value"].fillna(0)
    p["waiters"] = np.maximum(np.ceil(p["guests"] / std.covers_per_waiter_hour), std.min_waiters).astype(int)
    p["cooks"] = np.maximum(np.ceil(p["guests"] / std.covers_per_cook_hour), std.min_cooks).astype(int)
    return p.drop(columns="value")


def compare_to_fixed_schedule(plan: pd.DataFrame, std: StaffStandards, quantile: float = 0.85) -> pd.DataFrame:
    """Compare the demand-driven plan with a fixed schedule (same headcount every
    hour, sized for the `quantile` busiest hours) - what many restaurants do today."""
    rows = []
    for b, g in plan.groupby("branch"):
        for role in ("waiters", "cooks"):
            fixed = int(np.ceil(g[role].quantile(quantile)))
            need = g[role].to_numpy()
            rows.append({
                "branch": b, "role": role, "fixed_headcount": fixed,
                "planned_hours": int(need.sum()), "fixed_hours": int(fixed * len(need)),
                "hours_saved": int(fixed * len(need) - need.sum()),
                "understaffed_hours_fixed": int((need > fixed).sum()),
                "overstaffed_hours_fixed": int((need < fixed).sum()),
            })
    r = pd.DataFrame(rows)
    r["cost_saved"] = r["hours_saved"] * std.hourly_wage
    return r


def ingredient_needs(item_fc: pd.DataFrame, recipes: pd.DataFrame, ingredients: pd.DataFrame) -> pd.DataFrame:
    n = item_fc.astype({"item_id": str}).merge(recipes.astype({"item_id": str}), on="item_id")
    n["need"] = n["qty"] * n["qty_per_portion"]
    n = n.groupby(["date", "branch", "ingredient"], as_index=False)["need"].sum()
    n = n.merge(ingredients, on="ingredient", how="left")
    n["cost"] = n["need"] * n["unit_cost"]
    return n


def purchase_list(needs: pd.DataFrame, safety: float = 0.10) -> pd.DataFrame:
    g = needs.groupby(["branch", "ingredient", "unit", "unit_cost", "shelf_life_days"], as_index=False)["need"].sum()
    g["order_qty"] = g["need"] * (1 + safety)
    g["order_cost"] = g["order_qty"] * g["unit_cost"]
    g["ordering"] = np.where(g["shelf_life_days"] <= 3, "daily (perishable)",
                             np.where(g["shelf_life_days"] <= 7, "twice a week", "weekly"))
    return g.sort_values("order_cost", ascending=False)


def actual_ingredient_use(sales: pd.DataFrame, recipes: pd.DataFrame, ingredients: pd.DataFrame) -> pd.DataFrame:
    q = sales.groupby(["date", "branch", "item_id"], observed=True)["qty"].sum().reset_index()
    q = q.astype({"branch": str, "item_id": str})
    return ingredient_needs(q, recipes, ingredients)


def waste_backtest(sales: pd.DataFrame, calendar: pd.DataFrame, recipes: pd.DataFrame,
                   ingredients: pd.DataFrame, weeks: int = 4, safety: float = 0.10,
                   naive_buffer: float = 0.15, perishable_days: int = 3) -> dict:
    """Simulate daily ordering of perishable ingredients over the last `weeks` weeks.

    * Naive plan: what was used on the same weekday last week + `naive_buffer`.
    * AI plan: guest forecast x item mix x recipes + `safety`.
    Unused perishables are counted as waste; missing quantity as shortage.
    """
    daily = daily_totals(sales)
    end = daily["date"].max()
    perish = ingredients[ingredients["shelf_life_days"] <= perishable_days]["ingredient"].tolist()
    actual = actual_ingredient_use(sales, recipes, ingredients)
    actual = actual[actual["ingredient"].isin(perish)]
    act = actual.set_index(["date", "branch", "ingredient"])["need"]
    results = []
    for w in range(weeks, 0, -1):
        origin = end - pd.Timedelta(days=7 * w)
        fc = DemandForecaster("covers").fit(daily, calendar, train_end=origin).predict(7)
        mix = item_mix(sales[sales["date"] <= origin])
        ai = ingredient_needs(item_forecast(fc, mix), recipes, ingredients)
        ai = ai[ai["ingredient"].isin(perish)].set_index(["date", "branch", "ingredient"])["need"] * (1 + safety)
        week_idx = act[(act.index.get_level_values("date") > origin)
                       & (act.index.get_level_values("date") <= origin + pd.Timedelta(days=7))].index
        prev = act.copy()
        prev.index = prev.index.set_levels(prev.index.levels[0] + pd.Timedelta(days=7), level=0)
        naive = prev.reindex(week_idx).fillna(0) * (1 + naive_buffer)
        a = act.reindex(week_idx).fillna(0)
        plan_ai = ai.reindex(week_idx).fillna(0)
        cost = ingredients.set_index("ingredient")["unit_cost"].reindex(week_idx.get_level_values("ingredient")).to_numpy()
        for name, plan in (("Naive (last week + 15%)", naive), ("AI forecast + 10% safety", plan_ai)):
            waste = np.maximum(plan.to_numpy() - a.to_numpy(), 0)
            short = np.maximum(a.to_numpy() - plan.to_numpy(), 0)
            results.append({"week_start": origin + pd.Timedelta(days=1), "method": name,
                            "waste_cost": float((waste * cost).sum()),
                            "shortage_cost": float((short * cost).sum()),
                            "purchased_cost": float((plan.to_numpy() * cost).sum()),
                            "used_cost": float((a.to_numpy() * cost).sum())})
    r = pd.DataFrame(results)
    summary = r.groupby("method", as_index=False)[["waste_cost", "shortage_cost", "purchased_cost", "used_cost"]].sum()
    summary["waste_pct_of_purchases"] = summary["waste_cost"] / summary["purchased_cost"]
    summary["shortage_pct_of_use"] = summary["shortage_cost"] / summary["used_cost"]
    naive_w = summary.loc[summary["method"].str.startswith("Naive"), "waste_cost"].iloc[0]
    ai_w = summary.loc[summary["method"].str.startswith("AI"), "waste_cost"].iloc[0]
    return {"weekly": r, "summary": summary, "waste_reduction": 1 - ai_w / naive_w if naive_w else 0.0,
            "weeks": weeks, "perishables": perish}
