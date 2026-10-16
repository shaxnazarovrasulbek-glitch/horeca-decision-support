"""Market-basket analysis: which items are bought together, and what an upsell
prompt ("Would you like an Achichuk salad with your plov?") is worth."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse


def pair_rules(sales: pd.DataFrame, min_support: float = 0.005, min_lift: float = 1.2,
               min_confidence: float = 0.08) -> pd.DataFrame:
    """Directional pair rules A -> B with support, confidence and lift."""
    s = sales[["order_id", "item_id", "item_name"]].drop_duplicates(["order_id", "item_id"])
    o_codes, o_uni = pd.factorize(s["order_id"].astype(str))
    i_codes, i_uni = pd.factorize(s["item_id"].astype(str))
    names = s.drop_duplicates("item_id").set_index(s.drop_duplicates("item_id")["item_id"].astype(str))["item_name"].astype(str)
    X = sparse.csr_matrix((np.ones(len(s), dtype=np.int32), (o_codes, i_codes)), shape=(len(o_uni), len(i_uni)))
    n = X.shape[0]
    co = (X.T @ X).toarray().astype(float)
    count = np.diag(co).copy()
    rows = []
    for a in range(len(i_uni)):
        for b in range(len(i_uni)):
            if a == b or co[a, b] == 0:
                continue
            support = co[a, b] / n
            conf = co[a, b] / count[a]
            lift = conf / (count[b] / n)
            if support >= min_support and lift >= min_lift and conf >= min_confidence:
                rows.append({"antecedent_id": i_uni[a], "antecedent": names[i_uni[a]],
                             "consequent_id": i_uni[b], "consequent": names[i_uni[b]],
                             "orders_with_both": int(co[a, b]), "orders_with_antecedent": int(count[a]),
                             "support": support, "confidence": conf, "lift": lift,
                             "consequent_base_rate": count[b] / n})
    cols = ["antecedent_id", "antecedent", "consequent_id", "consequent", "orders_with_both",
            "orders_with_antecedent", "support", "confidence", "lift", "consequent_base_rate"]
    return pd.DataFrame(rows, columns=cols).sort_values("lift", ascending=False).reset_index(drop=True)


TRIGGER_CATEGORIES = ("Main", "Soup", "Dessert")
ADD_ON_CATEGORIES = ("Salad", "Side", "Drink", "Dessert", "Soup")
CATEGORY_ORDER = {"Main": 0, "Soup": 1, "Salad": 2, "Side": 3, "Dessert": 4, "Drink": 5}


def upsell_opportunities(rules: pd.DataFrame, menu: pd.DataFrame, period_days: int,
                         acceptance: float = 0.10, min_confidence: float = 0.15,
                         min_lift: float = 1.5) -> pd.DataFrame:
    """Monthly value if staff/app suggest add-on B to orders that have trigger A
    but not B, and `acceptance` of those guests say yes."""
    if rules.empty:
        return rules.assign(missed_orders_month=[], extra_revenue_month=[], extra_cm_month=[], script=[])
    m = menu.astype({"item_id": str}).set_index("item_id")
    cat = m["category"].astype(str)
    r = rules[rules["antecedent_id"].map(cat).isin(TRIGGER_CATEGORIES)
              & rules["consequent_id"].map(cat).isin(ADD_ON_CATEGORIES)
              & (rules["confidence"] >= min_confidence) & (rules["lift"] >= min_lift)].copy()
    r["missed_orders_month"] = (r["orders_with_antecedent"] - r["orders_with_both"]) * 30 / max(period_days, 1)
    price_b = m["price"].reindex(r["consequent_id"]).to_numpy()
    cm_b = (m["price"] - m["unit_cost"]).reindex(r["consequent_id"]).to_numpy()
    r["extra_revenue_month"] = r["missed_orders_month"] * acceptance * price_b
    r["extra_cm_month"] = r["missed_orders_month"] * acceptance * cm_b
    r["script"] = "With " + r["antecedent"] + ", suggest " + r["consequent"]
    return r.sort_values("extra_cm_month", ascending=False).reset_index(drop=True)


def combo_suggestions(rules: pd.DataFrame, menu: pd.DataFrame, discount: float = 0.07, top: int = 6) -> pd.DataFrame:
    """Bundle the strongest pairs (one row per unordered pair) at a small discount."""
    if rules.empty:
        return pd.DataFrame()
    m = menu.astype({"item_id": str}).set_index("item_id")
    r = rules.copy()
    r["pair"] = [tuple(sorted(p)) for p in zip(r["antecedent_id"], r["consequent_id"])]
    r = r.sort_values("lift", ascending=False).drop_duplicates("pair").head(top)
    rank = m["category"].astype(str).map(CATEGORY_ORDER).fillna(9)
    out = []
    for _, x in r.iterrows():
        a, b = sorted([x["antecedent_id"], x["consequent_id"]], key=lambda i: rank.get(i, 9))
        x = x.copy()
        x["antecedent"], x["consequent"] = m.loc[a, "item_name"], m.loc[b, "item_name"]
        full = m.loc[a, "price"] + m.loc[b, "price"]
        price = round(full * (1 - discount) / 1000) * 1000
        cost = m.loc[a, "unit_cost"] + m.loc[b, "unit_cost"]
        out.append({"combo": f"{x['antecedent']} + {x['consequent']}", "separate_price": full,
                    "combo_price": price, "guest_saves": full - price, "combo_margin": price - cost,
                    "combo_margin_pct": (price - cost) / price, "lift": x["lift"],
                    "orders_together_pct": x["support"]})
    return pd.DataFrame(out)
