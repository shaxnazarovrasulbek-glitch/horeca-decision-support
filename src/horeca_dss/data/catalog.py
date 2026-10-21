"""Static reference data for the synthetic restaurant chain.

All prices are in Uzbek som (UZS). The menu, recipes and ingredient costs are
illustrative values for a mid-range Tashkent restaurant chain, chosen to give
realistic margins and demand patterns. They are NOT real business data.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MenuItem:
    item_id: str
    name: str
    category: str
    price: int            # base menu price, UZS
    food_cost_pct: float  # ingredient cost as share of base price
    weight: float         # base popularity inside its category
    elasticity: float     # true own-price elasticity used by the generator
    temp_sens: float      # >0 sells more on hot days, <0 more on cold days


MENU: list[MenuItem] = [
    MenuItem("M01", "Tashkent Plov", "Main", 45000, 0.34, 1.60, -0.6, 0.0),
    MenuItem("M02", "Lagman", "Main", 38000, 0.30, 1.10, -0.9, -0.3),
    MenuItem("M03", "Beef Shashlik", "Main", 54000, 0.42, 1.00, -1.1, 0.2),
    MenuItem("M04", "Chicken Shashlik", "Main", 42000, 0.36, 0.90, -1.2, 0.2),
    MenuItem("M05", "Manti", "Main", 36000, 0.28, 0.90, -0.8, -0.2),
    MenuItem("M06", "Classic Burger", "Main", 39000, 0.33, 0.80, -1.5, 0.0),
    MenuItem("M07", "Chicken Wrap", "Main", 34000, 0.31, 0.50, -1.6, 0.2),
    MenuItem("M08", "Dimlama", "Main", 44000, 0.27, 0.35, -1.0, -0.4),
    MenuItem("M09", "Grilled Salmon", "Main", 89000, 0.48, 0.15, -1.4, 0.1),
    MenuItem("M10", "Kazan Kebab", "Main", 52000, 0.37, 0.45, -1.0, 0.0),
    MenuItem("S01", "Achichuk Salad", "Salad", 16000, 0.22, 1.00, -0.7, 0.4),
    MenuItem("S02", "Caesar Salad", "Salad", 36000, 0.35, 0.60, -1.3, 0.1),
    MenuItem("S03", "Greek Salad", "Salad", 32000, 0.33, 0.40, -1.2, 0.3),
    MenuItem("S04", "Olivier Salad", "Salad", 28000, 0.30, 0.35, -1.0, -0.2),
    MenuItem("P01", "Shurpa", "Soup", 30000, 0.26, 0.90, -0.8, -1.0),
    MenuItem("P02", "Mastava", "Soup", 26000, 0.24, 0.70, -0.8, -0.9),
    MenuItem("P03", "Chuchvara Soup", "Soup", 28000, 0.27, 0.50, -0.9, -0.8),
    MenuItem("D01", "Medovik Cake", "Dessert", 24000, 0.30, 0.80, -1.1, 0.0),
    MenuItem("D02", "Napoleon Cake", "Dessert", 24000, 0.31, 0.60, -1.1, 0.0),
    MenuItem("D03", "Ice Cream", "Dessert", 18000, 0.25, 0.50, -1.3, 1.2),
    MenuItem("D04", "Chak-chak", "Dessert", 15000, 0.20, 0.25, -0.9, -0.2),
    MenuItem("B01", "Green Tea (pot)", "Drink", 12000, 0.08, 1.60, -0.4, -0.5),
    MenuItem("B02", "Black Tea (pot)", "Drink", 12000, 0.08, 1.00, -0.4, -0.5),
    MenuItem("B03", "Americano", "Drink", 20000, 0.15, 0.60, -1.0, -0.1),
    MenuItem("B04", "Cappuccino", "Drink", 26000, 0.18, 0.60, -1.1, -0.2),
    MenuItem("B05", "Homemade Lemonade", "Drink", 22000, 0.14, 0.60, -1.4, 1.3),
    MenuItem("B06", "Coca-Cola 0.5L", "Drink", 12000, 0.45, 0.70, -1.2, 0.8),
    MenuItem("B07", "Mineral Water 0.5L", "Drink", 8000, 0.40, 0.50, -0.6, 0.6),
    MenuItem("B08", "Fresh Juice", "Drink", 28000, 0.30, 0.30, -1.5, 0.6),
    MenuItem("X01", "Tandoor Non", "Side", 6000, 0.20, 1.00, -0.3, 0.0),
    MenuItem("X02", "French Fries", "Side", 18000, 0.22, 0.60, -1.2, 0.0),
    MenuItem("X03", "Rice Garnish", "Side", 12000, 0.18, 0.30, -0.8, 0.0),
]

# Items that are frequently ordered together: main -> [(companion, probability per guest)]
COMPANIONS: dict[str, list[tuple[str, float]]] = {
    "M01": [("S01", 0.55)],
    "M03": [("S01", 0.30)],
    "M04": [("S01", 0.25)],
    "M06": [("X02", 0.60), ("B06", 0.45)],
    "M07": [("X02", 0.30), ("B05", 0.25)],
    "M09": [("S03", 0.35), ("B08", 0.20)],
    "M10": [("X03", 0.40)],
}
# A guest who orders a cake often adds a cappuccino.
DESSERT_COMPANIONS: dict[str, list[tuple[str, float]]] = {
    "D01": [("B04", 0.30)],
    "D02": [("B04", 0.25)],
}


@dataclass(frozen=True)
class Branch:
    name: str
    base_orders_per_hour: float
    hour_profile: tuple[float, ...]  # opening hours 10:00 ... 23:00 (14 slots)
    dow_profile: tuple[float, ...]   # Monday ... Sunday
    summer_terrace: float            # extra demand May-Sep


OPEN_HOUR = 10
CLOSE_HOUR = 24  # last orders 23:xx
HOURS = list(range(OPEN_HOUR, CLOSE_HOUR))

BRANCHES: list[Branch] = [
    Branch(
        "Chilanzar",
        9.0,
        (0.30, 0.50, 0.90, 1.20, 1.00, 0.60, 0.50, 0.70, 1.10, 1.40, 1.50, 1.20, 0.80, 0.40),
        (0.85, 0.85, 0.90, 0.95, 1.10, 1.35, 1.30),
        0.10,
    ),
    Branch(
        "Yunusabad",
        8.5,
        (0.40, 0.70, 1.40, 1.80, 1.30, 0.60, 0.50, 0.60, 0.90, 1.10, 1.00, 0.80, 0.50, 0.25),
        (1.05, 1.05, 1.05, 1.05, 1.10, 0.85, 0.70),
        0.04,
    ),
]

def make_branches(n: int = 2, seed: int = 0) -> list[Branch]:
    """Return `n` branches for scale tests: the two real profiles first, then synthetic
    copies ("Branch 03", ...) that alternate between a family-district and a
    business-district profile with a different size (70-130% of the base demand)."""
    if n <= len(BRANCHES):
        return BRANCHES[:max(n, 1)]
    import numpy as np
    rng = np.random.default_rng(seed)
    out = list(BRANCHES)
    for k in range(len(BRANCHES), n):
        base = BRANCHES[k % len(BRANCHES)]
        out.append(Branch(f"Branch {k + 1:02d}", round(base.base_orders_per_hour * float(rng.uniform(0.7, 1.3)), 2),
                          base.hour_profile, base.dow_profile, base.summer_terrace))
    return out


# ingredient -> (unit, unit cost UZS, shelf life days)
INGREDIENTS: dict[str, tuple[str, int, int]] = {
    "Rice": ("kg", 18000, 180),
    "Beef": ("kg", 110000, 3),
    "Lamb": ("kg", 120000, 3),
    "Chicken": ("kg", 42000, 2),
    "Salmon": ("kg", 260000, 2),
    "Carrot": ("kg", 6000, 14),
    "Onion": ("kg", 5000, 21),
    "Tomato": ("kg", 14000, 5),
    "Cucumber": ("kg", 12000, 5),
    "Potato": ("kg", 6000, 30),
    "Flour": ("kg", 9000, 120),
    "Lettuce": ("kg", 30000, 3),
    "Cheese": ("kg", 95000, 14),
    "Milk & Cream": ("l", 16000, 5),
    "Eggs": ("pcs", 1500, 21),
    "Cooking Oil": ("l", 22000, 180),
    "Tea Leaves": ("kg", 120000, 365),
    "Coffee Beans": ("kg", 260000, 90),
    "Lemons & Fruit": ("kg", 25000, 7),
    "Sugar & Honey": ("kg", 14000, 365),
    "Bottled Drinks": ("pcs", 5000, 180),
}

# item_id -> {ingredient: quantity per portion}
RECIPES: dict[str, dict[str, float]] = {
    "M01": {"Rice": 0.15, "Lamb": 0.10, "Carrot": 0.12, "Onion": 0.04, "Cooking Oil": 0.03},
    "M02": {"Flour": 0.12, "Beef": 0.09, "Tomato": 0.06, "Onion": 0.03, "Cooking Oil": 0.02},
    "M03": {"Beef": 0.21, "Onion": 0.05},
    "M04": {"Chicken": 0.25, "Onion": 0.04},
    "M05": {"Flour": 0.10, "Lamb": 0.09, "Onion": 0.05},
    "M06": {"Beef": 0.15, "Flour": 0.08, "Lettuce": 0.02, "Tomato": 0.03, "Cheese": 0.02},
    "M07": {"Chicken": 0.12, "Flour": 0.07, "Lettuce": 0.03, "Tomato": 0.03},
    "M08": {"Beef": 0.12, "Potato": 0.15, "Carrot": 0.08, "Onion": 0.05, "Tomato": 0.05},
    "M09": {"Salmon": 0.16, "Lettuce": 0.03, "Lemons & Fruit": 0.02},
    "M10": {"Lamb": 0.16, "Potato": 0.15, "Onion": 0.04, "Cooking Oil": 0.03},
    "S01": {"Tomato": 0.15, "Onion": 0.04},
    "S02": {"Lettuce": 0.08, "Chicken": 0.06, "Cheese": 0.02, "Eggs": 1.0},
    "S03": {"Tomato": 0.08, "Cucumber": 0.08, "Cheese": 0.04},
    "S04": {"Potato": 0.08, "Carrot": 0.03, "Eggs": 1.0, "Cucumber": 0.03},
    "P01": {"Lamb": 0.08, "Potato": 0.10, "Carrot": 0.05, "Onion": 0.03},
    "P02": {"Rice": 0.05, "Beef": 0.06, "Carrot": 0.04, "Tomato": 0.04},
    "P03": {"Flour": 0.06, "Beef": 0.05, "Onion": 0.02},
    "D01": {"Flour": 0.05, "Milk & Cream": 0.06, "Sugar & Honey": 0.04, "Eggs": 1.0},
    "D02": {"Flour": 0.06, "Milk & Cream": 0.08, "Sugar & Honey": 0.03, "Eggs": 1.0},
    "D03": {"Milk & Cream": 0.12, "Sugar & Honey": 0.03},
    "D04": {"Flour": 0.05, "Sugar & Honey": 0.05, "Cooking Oil": 0.02},
    "B01": {"Tea Leaves": 0.005},
    "B02": {"Tea Leaves": 0.005},
    "B03": {"Coffee Beans": 0.018},
    "B04": {"Coffee Beans": 0.018, "Milk & Cream": 0.15},
    "B05": {"Lemons & Fruit": 0.08, "Sugar & Honey": 0.03},
    "B06": {"Bottled Drinks": 1.0},
    "B07": {"Bottled Drinks": 1.0},
    "B08": {"Lemons & Fruit": 0.35},
    "X01": {"Flour": 0.12},
    "X02": {"Potato": 0.18, "Cooking Oil": 0.03},
    "X03": {"Rice": 0.10},
}
