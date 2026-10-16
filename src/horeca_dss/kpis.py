"""Business KPIs, period comparison and anomaly detection."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data.loader import daily_totals

ALL = "All branches"
DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def filter_sales(sales: pd.DataFrame, start=None, end=None, branch: str | None = None) -> pd.DataFrame:
    s = sales
    if branch not in (None, ALL):
        s = s[s["branch"] == branch]
    if start is not None:
        s = s[s["date"] >= pd.Timestamp(start)]
    if end is not None:
        s = s[s["date"] <= pd.Timestamp(end)]
    return s


def summary(s: pd.DataFrame) -> dict[str, float]:
    orders = s.drop_duplicates("order_id")
    revenue = float(s["revenue"].sum())
    food = float(s["food_cost"].sum())
    n_orders = int(len(orders))
    covers = int(orders["covers"].sum())
    days = max(int(s["date"].nunique()), 1)
    return {
        "revenue": revenue,
        "orders": n_orders,
        "covers": covers,
        "avg_check": revenue / n_orders if n_orders else 0.0,
        "revenue_per_cover": revenue / covers if covers else 0.0,
        "food_cost_pct": food / revenue if revenue else 0.0,
        "gross_margin": revenue - food,
        "revenue_per_day": revenue / days,
        "items_per_order": float(s["qty"].sum()) / n_orders if n_orders else 0.0,
    }


def compare_periods(sales: pd.DataFrame, end, days: int = 28, branch: str | None = None) -> dict:
    end = pd.Timestamp(end)
    cur = filter_sales(sales, end - pd.Timedelta(days=days - 1), end, branch)
    prev = filter_sales(sales, end - pd.Timedelta(days=2 * days - 1), end - pd.Timedelta(days=days), branch)
    c, p = summary(cur), summary(prev)
    delta = {k: (c[k] / p[k] - 1) if p.get(k) else None for k in c}
    return {"current": c, "previous": p, "delta": delta,
            "period": (end - pd.Timedelta(days=days - 1), end)}


def weekly_revenue(sales: pd.DataFrame, branch: str | None = None) -> pd.DataFrame:
    d = daily_totals(sales, branch)
    d["week"] = d["date"] - pd.to_timedelta(d["date"].dt.dayofweek, unit="D")
    w = d.groupby(["week", "branch"], as_index=False)[["revenue", "orders", "covers"]].sum()
    # drop incomplete first/last weeks
    counts = d.groupby("week")["date"].nunique()
    full = counts[counts == 7].index
    return w[w["week"].isin(full)]


def hour_dow_heatmap(s: pd.DataFrame) -> pd.DataFrame:
    """Average revenue per (weekday, hour) over the selected period."""
    days_per_dow = s.groupby(s["date"].dt.dayofweek)["date"].nunique()
    g = s.groupby([s["date"].dt.dayofweek, "hour"])["revenue"].sum().unstack(fill_value=0)
    g = g.div(days_per_dow, axis=0)
    g.index = [DOW_NAMES[i] for i in g.index]
    return g


def category_mix(s: pd.DataFrame) -> pd.DataFrame:
    g = s.groupby("category", observed=True).agg(revenue=("revenue", "sum"), qty=("qty", "sum"),
                                                 food_cost=("food_cost", "sum")).reset_index()
    g["share"] = g["revenue"] / g["revenue"].sum()
    g["margin_pct"] = 1 - g["food_cost"] / g["revenue"]
    return g.sort_values("revenue", ascending=False)


def _longest_run(hours: list[int]) -> list[int]:
    """Longest run of consecutive hours, e.g. [10, 15, 16, 17] -> [15, 16, 17]."""
    best, cur = [], []
    for h in hours:
        cur = cur + [h] if cur and h == cur[-1] + 1 else [h]
        if len(cur) > len(best):
            best = cur
    return best


def detect_anomalies(sales: pd.DataFrame, calendar: pd.DataFrame, threshold: float = 0.30,
                     lookback_days: int = 120) -> pd.DataFrame:
    """Flag branch-days whose revenue deviates from the same-weekday median of the
    previous 4 weeks, and attach likely explanations (holiday, promo, weather,
    hours with no sales)."""
    d = daily_totals(sales)
    d = d.sort_values(["branch", "date"])
    exp = []
    for _, g in d.groupby("branch"):
        r = g.set_index("date")["revenue"]
        lags = pd.concat([r.shift(7 * k) for k in range(1, 5)], axis=1)
        exp.append(pd.Series(lags.median(axis=1).to_numpy(), index=g.index))
    d["expected"] = pd.concat(exp)
    d = d[d["date"] >= d["date"].max() - pd.Timedelta(days=lookback_days)]
    d = d.dropna(subset=["expected"])
    d["deviation"] = d["revenue"] / d["expected"].replace(0, np.nan) - 1
    flagged = d[d["deviation"].abs() >= threshold].copy()
    if flagged.empty:
        return pd.DataFrame(columns=["date", "weekday", "branch", "type", "revenue", "expected", "deviation",
                                     "explanation", "explained_by_calendar"])
    cal = calendar.set_index(pd.to_datetime(calendar["date"]))
    hourly = sales.groupby(["branch", "date", "hour"], observed=True)["revenue"].sum()
    sw = sales.assign(dow=sales["date"].dt.dayofweek)
    num = sw.groupby(["branch", "dow", "hour"], observed=True)["revenue"].sum()
    den = sw.groupby(["branch", "dow"], observed=True)["date"].nunique()
    typical = num / den.reindex(num.index.droplevel("hour")).to_numpy()
    notes = []
    for _, row in flagged.iterrows():
        why = []
        c = cal.loc[row["date"]] if row["date"] in cal.index else None
        if c is not None:
            if c["holiday"]:
                why.append(f"public holiday: {c['holiday']}")
            if c["promo"]:
                why.append("marketing campaign running")
            if c["ramadan"]:
                why.append("Ramadan period")
            if c["temp_c"] >= 35:
                why.append(f"heat ({c['temp_c']:.0f} C)")
            if c["temp_c"] <= -3:
                why.append(f"cold ({c['temp_c']:.0f} C)")
        if row["deviation"] < 0:
            try:
                h = hourly.loc[(row["branch"], row["date"])]
            except KeyError:
                h = pd.Series(dtype=float)
            t = typical.loc[(row["branch"], row["date"].dayofweek)]
            day_total = float(t.sum())
            gaps = sorted(hr for hr in t.index if t[hr] >= 0.03 * day_total and h.get(hr, 0) < 0.15 * t[hr])
            run = _longest_run(gaps)
            if len(run) >= 2:
                why.append(f"almost no sales from {run[0]}:00 to {run[-1] + 1}:00 (possible closure/outage)")
            elif not why:
                why.append("demand drop across all hours (check staffing, kitchen, competitors)")
        elif not why:
            why.append("demand spike (event nearby? check reviews/social media)")
        notes.append("; ".join(why))
    flagged["explanation"] = notes
    flagged["type"] = np.where(flagged["deviation"] < 0, "drop", "spike")
    flagged["explained_by_calendar"] = [any(k in n for k in ("holiday", "campaign", "Ramadan", "heat", "cold"))
                                        for n in notes]
    flagged["weekday"] = flagged["date"].dt.day_name()
    return flagged.sort_values("date", ascending=False)[
        ["date", "weekday", "branch", "type", "revenue", "expected", "deviation", "explanation",
         "explained_by_calendar"]]
