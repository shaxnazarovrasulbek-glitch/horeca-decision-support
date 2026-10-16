"""Price elasticity estimation and margin-maximising price recommendations.

Elasticity is estimated per item with a log-log regression of daily portions
per guest on the item's price *relative to its menu section* (so a menu-wide
inflation update does not bias the estimate), controlling for weekday,
temperature, branch and trend:

    log(q / guests) = a + e * log(p / p_section) + weekday + temp + branch + trend

Items without enough own price variation fall back to a category prior and are
labelled as such. Recommendations evaluate +/-5% and +/-10% price moves with a
constant-elasticity demand curve and keep the one with the highest contribution
margin, as long as volume does not fall by more than `max_volume_drop`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CATEGORY_PRIOR = {"Main": -0.9, "Salad": -0.9, "Soup": -0.8, "Dessert": -1.0, "Drink": -0.7, "Side": -0.5}
CANDIDATES = (-0.10, -0.05, 0.0, 0.05, 0.10)


def _daily_item_table(sales: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Daily (branch, item) table with portions, guests and the menu price relative
    to the average menu price of the item's section. Prices are only observed when
    an item sells, so they are carried forward/backward on a full date grid."""
    orders = sales.drop_duplicates("order_id")
    guests = orders.groupby(["date", "branch"], observed=True)["covers"].sum().rename("guests")
    q = sales.groupby(["date", "branch", "item_id"], observed=True).agg(
        qty=("qty", "sum"), revenue=("revenue", "sum"))
    price = (q["revenue"] / q["qty"]).rename("price")
    dates = pd.date_range(sales["date"].min(), sales["date"].max())
    branches = sales["branch"].astype(str).unique()
    items = sales["item_id"].astype(str).unique()
    grid = pd.MultiIndex.from_product([dates, branches, items], names=["date", "branch", "item_id"])
    t = pd.DataFrame(index=grid)
    q.index = q.index.set_levels([q.index.levels[0], q.index.levels[1].astype(str), q.index.levels[2].astype(str)])
    price.index = q.index
    t = t.join(q[["qty"]]).join(price)
    t["qty"] = t["qty"].fillna(0)
    t["price"] = t.groupby(level=["branch", "item_id"])["price"].transform(lambda x: x.ffill().bfill())
    cats = sales.drop_duplicates("item_id").astype({"item_id": str, "category": str}).set_index("item_id")["category"]
    t = t.reset_index()
    t["category"] = t["item_id"].map(cats)
    t["rel_price"] = t["price"] / t.groupby(["date", "branch", "category"])["price"].transform("mean")
    g = guests.reset_index().astype({"branch": str})
    t = t.merge(g, on=["date", "branch"], how="left")
    cal = calendar.assign(date=pd.to_datetime(calendar["date"])).set_index("date")
    t["temp_z"] = (cal["temp_c"].reindex(t["date"]).to_numpy() - 16) / 10
    t["dow"] = t["date"].dt.dayofweek
    t["t"] = (t["date"] - t["date"].min()).dt.days / 365
    return t


def estimate_elasticities(sales: pd.DataFrame, calendar: pd.DataFrame, min_obs: int = 60,
                          min_changed_days: int = 14) -> pd.DataFrame:
    q = _daily_item_table(sales, calendar)
    rows = []
    for (item_id, category), g in q.groupby(["item_id", "category"]):
        g = g[(g["guests"] > 0) & g["rel_price"].notna()]
        x = np.log(g["rel_price"].to_numpy())
        changed = int((np.abs(x - np.median(x)) > 0.03).sum()) if len(x) else 0
        prior = CATEGORY_PRIOR.get(str(category), -0.8)
        if len(g) < min_obs or changed < min_changed_days:
            rows.append({"item_id": item_id, "elasticity": prior, "se": np.nan, "n_obs": len(g),
                         "days_with_price_change": changed, "method": "category prior", "confidence": "Low"})
            continue
        y = np.log((g["qty"].to_numpy() + 0.5) / g["guests"].to_numpy())
        dow = pd.get_dummies(g["dow"], prefix="d", drop_first=True).to_numpy(float)
        br = pd.get_dummies(g["branch"].astype(str), drop_first=True).to_numpy(float)
        X = np.column_stack([np.ones(len(g)), x, g["temp_z"].to_numpy(), g["t"].to_numpy(), dow, br])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        dof = max(len(y) - X.shape[1], 1)
        sigma2 = resid @ resid / dof
        try:
            se = float(np.sqrt((sigma2 * np.linalg.inv(X.T @ X))[1, 1]))
        except np.linalg.LinAlgError:
            se = np.nan
        e = float(np.clip(beta[1], -3.0, -0.05))
        conf = "High" if se < 0.15 else "Medium" if se < 0.30 else "Low"
        rows.append({"item_id": item_id, "elasticity": e, "se": se, "n_obs": len(g),
                     "days_with_price_change": changed, "method": "estimated from price changes",
                     "confidence": conf})
    return pd.DataFrame(rows)


def price_recommendations(sales_period: pd.DataFrame, menu: pd.DataFrame, elasticities: pd.DataFrame,
                          period_days: int, max_volume_drop: float = 0.08) -> pd.DataFrame:
    qty = sales_period.groupby("item_id", observed=True)["qty"].sum().rename("qty_period")
    df = (menu.astype({"item_id": str}).merge(elasticities.astype({"item_id": str}), on="item_id", how="left")
          .merge(qty.rename_axis("item_id").reset_index().astype({"item_id": str}), on="item_id", how="left"))
    df["qty_period"] = df["qty_period"].fillna(0)
    month = 30 / max(period_days, 1)
    out = []
    for _, r in df.iterrows():
        e = r["elasticity"] if pd.notna(r["elasticity"]) else -0.8
        # only act on elasticities we trust; low-confidence items get a price test instead
        cands = list(CANDIDATES) if r["confidence"] != "Low" else [0.0]
        q0 = r["qty_period"] * month
        best = None
        for c in cands:
            p = round(r["price"] * (1 + c) / 1000) * 1000
            if p <= r["unit_cost"]:
                continue
            q = q0 * (p / r["price"]) ** e
            if q < q0 * (1 - max_volume_drop) - 1e-9:
                continue
            cm = (p - r["unit_cost"]) * q
            if best is None or cm > best["cm"] + 1e-6:
                best = {"price": p, "qty": q, "cm": cm, "rev": p * q}
        cm0 = (r["price"] - r["unit_cost"]) * q0
        out.append({
            "item_id": r["item_id"], "item_name": r["item_name"], "category": r["category"],
            "current_price": r["price"], "unit_cost": r["unit_cost"], "elasticity": e,
            "confidence": r["confidence"], "method": r["method"],
            "recommended_price": best["price"], "change_pct": best["price"] / r["price"] - 1,
            "qty_month": q0, "exp_qty_change_pct": best["qty"] / q0 - 1 if q0 else 0.0,
            "cm_month_now": cm0, "cm_month_new": best["cm"], "cm_uplift_month": best["cm"] - cm0,
            "revenue_uplift_month": best["rev"] - r["price"] * q0,
            "test_price": round(r["price"] * 1.05 / 1000) * 1000,
            "next_step": ("Apply in one branch, compare with the other for 2 weeks" if best["price"] != r["price"]
                          else "Keep price" if r["confidence"] != "Low"
                          else "Run a 2-week price test to measure demand"),
        })
    res = pd.DataFrame(out)
    return res.sort_values("cm_uplift_month", ascending=False).reset_index(drop=True)
