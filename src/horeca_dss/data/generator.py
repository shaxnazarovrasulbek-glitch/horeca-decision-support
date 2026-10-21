"""Synthetic point-of-sale (POS) data for a two-branch restaurant chain in Tashkent.

The generator is fully vectorised and deterministic for a given seed. It plants
realistic structure that the analytics modules are expected to recover:

* weekly / hourly seasonality that differs per branch (family vs business district)
* growth trend, summer terrace effect, weather (hot days -> cold drinks, ice cream)
* Uzbek public holidays, Ramadan (lunch down, iftar evenings up), marketing promos
* price changes with item-specific price elasticity (within-category substitution)
* items that are frequently bought together (plov + achichuk, burger + fries + cola)
* two operational incidents (a power outage and an equipment failure)

The output is a flat table of order lines - the same schema a real POS export
would be mapped to (see ``loader.REQUIRED_COLUMNS``).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calendar import build_calendar
from .catalog import (
    BRANCHES, COMPANIONS, DESSERT_COMPANIONS, HOURS, INGREDIENTS, MENU, RECIPES,
)

ITEM_IDS = [m.item_id for m in MENU]
ITEM_INDEX = {iid: i for i, iid in enumerate(ITEM_IDS)}


def _choose(rng: np.random.Generator, day_idx: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Vectorised categorical draw where each row uses the weights of its day."""
    cum = np.cumsum(weights, axis=1)
    cum = cum / cum[:, -1:]
    u = rng.random(len(day_idx))
    return (u[:, None] > cum[day_idx]).sum(axis=1)


def _incidents(dates: pd.DatetimeIndex) -> list[dict]:
    """Two planted operational incidents relative to the end of the period."""
    end = dates[-1]
    # most recent Tuesday at least 3 days before the end -> power outage from 15:00
    outage_day = end - pd.Timedelta(days=3)
    while outage_day.dayofweek != 1:
        outage_day -= pd.Timedelta(days=1)
    failure_start = end - pd.Timedelta(days=75)
    return [
        {"branch": "Yunusabad", "start": outage_day, "end": outage_day, "from_hour": 15,
         "factor": 0.0, "description": "Power outage from 15:00 (branch closed early)"},
        {"branch": "Chilanzar", "start": failure_start, "end": failure_start + pd.Timedelta(days=2),
         "from_hour": 10, "factor": 0.45, "description": "Tandoor / grill equipment failure (limited menu)"},
    ]


def reference_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recipes (bill of materials) and ingredient master data."""
    recipes = pd.DataFrame([{"item_id": iid, "ingredient": ing, "qty_per_portion": q}
                            for iid, rec in RECIPES.items() for ing, q in rec.items()])
    ingredients = pd.DataFrame([{"ingredient": n, "unit": u, "unit_cost": c, "shelf_life_days": sl}
                                for n, (u, c, sl) in INGREDIENTS.items()])
    return recipes, ingredients


def generate_dataset(end: str | pd.Timestamp | None = None, days: int = 365,
                     seed: int = 42, branches: list | None = None) -> dict[str, pd.DataFrame]:
    """Generate a full dataset ending on `end` (default: yesterday).

    Returns a dict with ``sales`` (order lines), ``calendar``, ``menu``,
    ``recipes``, ``ingredients``, ``price_history`` and ``incidents``.
    `branches` defaults to the two demo branches; pass ``make_branches(n)`` for scale tests.
    """
    branches = BRANCHES if branches is None else branches
    rng = np.random.default_rng(seed)
    end = (pd.Timestamp.today().normalize() - pd.Timedelta(days=1)) if end is None else pd.Timestamp(end).normalize()
    start = end - pd.Timedelta(days=days - 1)
    dates = pd.date_range(start, end, freq="D")
    n_days, k = len(dates), len(MENU)

    # ---- marketing campaigns: 5 chain-wide promo weeks -------------------------------
    promo_dates: set[str] = set()
    slots = np.linspace(20, n_days - 15, 5).astype(int)
    for s in slots:
        s = int(s + rng.integers(-8, 8))
        for d in dates[max(s, 0):max(s, 0) + 7]:
            promo_dates.add(d.strftime("%Y-%m-%d"))
    cal = build_calendar(start, end, seed=seed + 1, promo_dates=promo_dates)
    temp = cal["temp_c"].to_numpy()
    z_temp = (temp - 16.0) / 10.0

    # ---- prices & costs ----------------------------------------------------------------
    base_price = np.array([m.price for m in MENU], dtype=float)
    price = np.tile(base_price, (n_days, 1))
    infl_day = int(min(max(n_days * 0.42, 30), n_days - 1))
    infl_date = (dates[infl_day] + pd.offsets.MonthBegin(0)).normalize()
    infl_mask = dates >= infl_date
    price[infl_mask] *= 1.08                       # menu-wide price update
    experiments = []
    # item-level price tests: 14 dishes, each tested twice (8 weeks up, 8 weeks down)
    exp_items = rng.choice([i for i, m in enumerate(MENU) if m.category != "Side"], size=14, replace=False)
    for j in exp_items:
        first = int(rng.integers(20, max(21, n_days // 2 - 60)))
        second = int(rng.integers(n_days // 2, max(n_days // 2 + 1, n_days - 60)))
        size = float(rng.choice([0.12, 0.15, 0.18]))
        for s, change in ((first, size), (second, -size)):
            price[s:s + 56, j] *= 1 + change
            experiments.append({"item_id": MENU[j].item_id, "start": dates[s],
                                "end": dates[min(s + 55, n_days - 1)], "change": change})
    price = np.round(price / 500) * 500
    cost = np.tile(base_price * np.array([m.food_cost_pct for m in MENU]), (n_days, 1))
    cost[infl_mask] *= 1.05
    cost = np.round(cost / 100) * 100

    # ---- category choice weights per day (price + weather effects) ---------------------
    eps = np.array([m.elasticity for m in MENU])
    tsens = np.array([m.temp_sens for m in MENU])
    w0 = np.array([m.weight for m in MENU])
    attract = w0 * (price / base_price) ** eps * np.exp(0.30 * tsens * z_temp[:, None])
    cats = {c: np.array([i for i, m in enumerate(MENU) if m.category == c])
            for c in ["Main", "Salad", "Soup", "Dessert", "Drink"]}

    # ---- hourly order intensity per branch -------------------------------------------
    t = np.arange(n_days) / 365.0
    month = dates.month.to_numpy()
    dow = dates.dayofweek.to_numpy()
    hours = np.array(HOURS)
    hol = cal["holiday_factor"].to_numpy()
    ram = cal["ramadan"].to_numpy()
    promo = cal["promo"].to_numpy()
    incidents = _incidents(dates)

    cells = []
    for b_idx, br in enumerate(branches):
        season = np.where(np.isin(month, [1, 2]), 0.94, 1.0) * np.where(month == 12, 1.05, 1.0)
        daily = (br.base_orders_per_hour * (1 + 0.18 * t) * season * np.array(br.dow_profile)[dow]
                 * hol * np.where(promo, 1.15, 1.0) * rng.lognormal(0, 0.045, n_days))
        # weather: cold days keep guests at home, mild days fill the terrace
        daily *= np.where(temp < 2, 0.88, 1.0) * np.where((temp >= 18) & (temp <= 27), 1 + br.summer_terrace, 1.0)
        lam = daily[:, None] * np.array(br.hour_profile)[None, :]
        lunch = (hours >= 11) & (hours <= 16)
        iftar = (hours >= 18) & (hours <= 21)
        lam[np.ix_(ram, lunch)] *= 0.75
        lam[np.ix_(ram, iftar)] *= 1.25
        hot = temp > 34
        lam[np.ix_(hot, (hours >= 12) & (hours <= 16))] *= 0.85
        lam[np.ix_(hot, hours >= 19)] *= 1.08
        for inc in incidents:
            if inc["branch"] != br.name:
                continue
            dmask = (dates >= inc["start"]) & (dates <= inc["end"])
            lam[np.ix_(dmask, hours >= inc["from_hour"])] *= inc["factor"]
        n = rng.poisson(lam)
        d_i, h_i = np.nonzero(n)
        cells.append(pd.DataFrame({"day": np.repeat(d_i, n[d_i, h_i]),
                                   "hour": np.repeat(hours[h_i], n[d_i, h_i]),
                                   "branch": b_idx}))
    orders = pd.concat(cells, ignore_index=True)
    orders = orders.sort_values(["day", "hour", "branch"], kind="stable").reset_index(drop=True)
    n_orders = len(orders)
    o_day = orders["day"].to_numpy()
    o_hour = orders["hour"].to_numpy()

    # channel & party size
    evening = o_hour >= 18
    p_delivery = 0.12 + 0.08 * evening + 0.05 * (np.abs(z_temp[o_day]) > 1.4)
    u = rng.random(n_orders)
    channel = np.where(u < p_delivery, "Delivery", np.where(u < p_delivery + 0.15, "Takeaway", "Dine-in"))
    dine = channel == "Dine-in"
    covers = np.where(dine,
                      rng.choice([1, 2, 3, 4, 5, 6], size=n_orders, p=[0.22, 0.36, 0.16, 0.16, 0.06, 0.04]),
                      rng.choice([1, 2, 3], size=n_orders, p=[0.55, 0.30, 0.15]))

    # ---- guests and item choices ---------------------------------------------------------
    g_order = np.repeat(np.arange(n_orders), covers)
    g_day = o_day[g_order]
    n_g = len(g_order)
    lines_o, lines_i = [], []

    def add(mask: np.ndarray, items: np.ndarray | int):
        lines_o.append(g_order[mask])
        lines_i.append(np.broadcast_to(items, mask.sum()) if np.isscalar(items) else items)

    def pick(cat: str, mask: np.ndarray) -> np.ndarray:
        idx = cats[cat]
        choice = _choose(rng, g_day[mask], attract[:, idx])
        return idx[choice]

    has_main = rng.random(n_g) < 0.86
    mains = pick("Main", has_main)
    add(has_main, mains)
    main_full = np.full(n_g, -1)
    main_full[has_main] = mains
    for m_id, comps in COMPANIONS.items():
        for c_id, p in comps:
            mask = (main_full == ITEM_INDEX[m_id]) & (rng.random(n_g) < p)
            add(mask, ITEM_INDEX[c_id])
    soup = rng.random(n_g) < 0.28 * np.exp(-0.35 * z_temp[g_day])
    add(soup, pick("Soup", soup))
    salad = rng.random(n_g) < 0.20
    add(salad, pick("Salad", salad))
    drink = rng.random(n_g) < 0.90
    add(drink, pick("Drink", drink))
    g_hour = o_hour[g_order]
    p_dessert = 0.14 + 0.07 * (g_hour >= 18) + 0.05 * (dow[g_day] >= 5)
    dessert = rng.random(n_g) < p_dessert
    desserts = pick("Dessert", dessert)
    add(dessert, desserts)
    dessert_full = np.full(n_g, -1)
    dessert_full[dessert] = desserts
    for d_id, comps in DESSERT_COMPANIONS.items():
        for c_id, p in comps:
            mask = (dessert_full == ITEM_INDEX[d_id]) & (rng.random(n_g) < p)
            add(mask, ITEM_INDEX[c_id])
    fries = rng.random(n_g) < 0.06
    add(fries, ITEM_INDEX["X02"])

    li = pd.DataFrame({"o": np.concatenate(lines_o), "i": np.concatenate(lines_i).astype(int)})
    li = li.groupby(["o", "i"], sort=False).size().rename("qty").reset_index()
    # bread: one non per two guests for most dine-in orders
    bread_orders = np.nonzero(dine & (rng.random(n_orders) < 0.75))[0]
    li = pd.concat([li, pd.DataFrame({"o": bread_orders, "i": ITEM_INDEX["X01"],
                                      "qty": np.ceil(covers[bread_orders] / 2).astype(int)})],
                   ignore_index=True)
    li = li.sort_values(["o", "i"]).reset_index(drop=True)

    o = li["o"].to_numpy()
    i = li["i"].to_numpy()
    day = o_day[o]
    minute = rng.integers(0, 60, n_orders)
    ts = dates[o_day] + pd.to_timedelta(o_hour, unit="h") + pd.to_timedelta(minute, unit="m")
    branch_names = np.array([b.name for b in branches])
    code = np.array([b.name[:2].upper() for b in branches])
    order_ids = np.char.add(code[orders["branch"].to_numpy()],
                            np.char.zfill(np.arange(1, n_orders + 1).astype(str), 7))
    sales = pd.DataFrame({
        "order_id": order_ids[o],
        "datetime": ts[o],
        "branch": branch_names[orders["branch"].to_numpy()[o]],
        "channel": channel[o],
        "covers": covers[o],
        "item_id": np.array(ITEM_IDS)[i],
        "item_name": np.array([m.name for m in MENU])[i],
        "category": np.array([m.category for m in MENU])[i],
        "qty": li["qty"].to_numpy(),
        "unit_price": price[day, i].astype(int),
        "unit_cost": cost[day, i].astype(int),
    })

    menu = pd.DataFrame({
        "item_id": ITEM_IDS,
        "item_name": [m.name for m in MENU],
        "category": [m.category for m in MENU],
        "price": price[-1].astype(int),
        "unit_cost": cost[-1].astype(int),
    })
    recipes, ingredients = reference_tables()
    price_history = pd.DataFrame(experiments)
    truth = pd.DataFrame({"item_id": ITEM_IDS, "true_elasticity": eps, "temp_sensitivity": tsens})
    return {
        "sales": sales,
        "calendar": cal,
        "menu": menu,
        "recipes": recipes,
        "ingredients": ingredients,
        "price_history": price_history,
        "incidents": pd.DataFrame(incidents),
        "truth": truth,
    }
