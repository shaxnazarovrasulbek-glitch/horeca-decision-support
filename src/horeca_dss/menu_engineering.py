"""Menu engineering (Kasavana & Smith, 1982): popularity x contribution margin.

Each item is placed in one of four segments, computed within its menu section
(category) so that a tea is not compared with a steak:

* Star       - popular and profitable           -> keep, protect quality, feature it
* Plowhorse  - popular, below-average margin     -> re-engineer cost / small price rise
* Puzzle     - profitable but not popular        -> promote: placement, staff suggestion
* Dog        - neither popular nor profitable    -> replace or remove

Popularity threshold: 70% of an equal share of the section's mix (the classic rule).
Margin threshold: the section's quantity-weighted average contribution margin.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEGMENTS = ["Star", "Plowhorse", "Puzzle", "Dog"]
ACTIONS = {
    "Star": "Keep recipe and price; give it the best menu position and photo. Test a small (+3-5%) price rise.",
    "Plowhorse": "Popular but low margin: reduce portion/ingredient cost or raise price slightly; pair it with a high-margin side.",
    "Puzzle": "High margin but under-ordered: move it up the menu, add a photo, have waiters recommend it, run a combo.",
    "Dog": "Low popularity and margin: replace with a new dish or remove to simplify the kitchen.",
}


def menu_engineering(sales: pd.DataFrame, by_category: bool = True, min_qty: int = 1) -> pd.DataFrame:
    """Classify each menu item. `sales` should already be filtered to the period/branch."""
    g = sales.groupby(["item_id", "item_name", "category"], observed=True).agg(
        qty=("qty", "sum"), revenue=("revenue", "sum"), food_cost=("food_cost", "sum")).reset_index()
    g = g[g["qty"] >= min_qty].astype({"item_id": str, "item_name": str, "category": str})
    g["price"] = g["revenue"] / g["qty"]
    g["unit_cost"] = g["food_cost"] / g["qty"]
    g["cm"] = g["price"] - g["unit_cost"]               # contribution margin per portion
    g["total_cm"] = g["cm"] * g["qty"]
    g["food_cost_pct"] = g["unit_cost"] / g["price"]
    group = g["category"] if by_category else pd.Series("All", index=g.index)
    g["section"] = group
    g["mix_pct"] = g["qty"] / g.groupby("section")["qty"].transform("sum")
    n_items = g.groupby("section")["item_id"].transform("count")
    g["pop_threshold"] = 0.7 / n_items
    g["cm_threshold"] = g.groupby("section")["total_cm"].transform("sum") / g.groupby("section")["qty"].transform("sum")
    high_pop = g["mix_pct"] >= g["pop_threshold"]
    high_cm = g["cm"] >= g["cm_threshold"]
    g["segment"] = np.select([high_pop & high_cm, high_pop & ~high_cm, ~high_pop & high_cm],
                             ["Star", "Plowhorse", "Puzzle"], default="Dog")
    g["action"] = g["segment"].map(ACTIONS)
    # relative position for plotting: >1 means above the section threshold
    g["popularity_index"] = g["mix_pct"] / g["pop_threshold"]
    g["margin_index"] = g["cm"] / g["cm_threshold"]
    return g.sort_values(["section", "total_cm"], ascending=[True, False]).reset_index(drop=True)


def segment_summary(me: pd.DataFrame) -> pd.DataFrame:
    s = me.groupby("segment").agg(items=("item_id", "count"), revenue=("revenue", "sum"),
                                  total_cm=("total_cm", "sum")).reindex(SEGMENTS).fillna(0)
    s["cm_share"] = s["total_cm"] / s["total_cm"].sum()
    return s.reset_index()
