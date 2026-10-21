"""Loading, validating and caching datasets (generated or uploaded POS exports)."""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .calendar import build_calendar
from .generator import generate_dataset, reference_tables

REQUIRED_COLUMNS = ["order_id", "datetime", "branch", "item_name", "qty", "unit_price"]
OPTIONAL_COLUMNS = {
    "item_id": None,          # derived from item_name
    "category": "Other",
    "covers": 1,
    "channel": "Dine-in",
    "unit_cost": None,        # derived as 32% of price when missing
}
DEFAULT_FOOD_COST_PCT = 0.32
DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@dataclass
class Dataset:
    """Everything the analytics modules need, plus where it came from."""

    sales: pd.DataFrame
    calendar: pd.DataFrame
    menu: pd.DataFrame
    recipes: pd.DataFrame | None = None
    ingredients: pd.DataFrame | None = None
    incidents: pd.DataFrame | None = None
    truth: pd.DataFrame | None = None
    source: str = "generated"
    dataset_id: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def start(self) -> pd.Timestamp:
        return self.sales["date"].min()

    @property
    def end(self) -> pd.Timestamp:
        return self.sales["date"].max()

    @property
    def branches(self) -> list[str]:
        return sorted(self.sales["branch"].unique().tolist())


def prepare_sales(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Validate a raw order-lines table and add derived columns."""
    notes: list[str] = []
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    bad = df["datetime"].isna().sum()
    if bad:
        notes.append(f"Dropped {bad} rows with unreadable datetime.")
        df = df.dropna(subset=["datetime"])
    for col in ["qty", "unit_price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["qty", "unit_price"])
    df = df[(df["qty"] > 0) & (df["unit_price"] >= 0)]
    for col, default in OPTIONAL_COLUMNS.items():
        if col not in df.columns:
            if col == "item_id":
                codes = {n: f"I{i:03d}" for i, n in enumerate(sorted(df["item_name"].unique()), 1)}
                df[col] = df["item_name"].map(codes)
            elif col == "unit_cost":
                df[col] = (df["unit_price"] * DEFAULT_FOOD_COST_PCT).round()
                notes.append(f"No unit_cost column: assumed food cost = {DEFAULT_FOOD_COST_PCT:.0%} of price.")
            else:
                df[col] = default
    df["unit_cost"] = pd.to_numeric(df["unit_cost"], errors="coerce").fillna(df["unit_price"] * DEFAULT_FOOD_COST_PCT)
    df["covers"] = pd.to_numeric(df["covers"], errors="coerce").fillna(1).clip(lower=1).astype(int)
    df["order_id"] = df["order_id"].astype(str)
    df["date"] = df["datetime"].dt.normalize()
    df["hour"] = df["datetime"].dt.hour.astype(int)
    df["revenue"] = df["qty"] * df["unit_price"]
    df["food_cost"] = df["qty"] * df["unit_cost"]
    for col in ["branch", "item_id", "item_name", "category", "channel"]:
        df[col] = df[col].astype(str).astype("category")
    df = df.sort_values("datetime").reset_index(drop=True)
    return df, notes


def menu_from_sales(sales: pd.DataFrame) -> pd.DataFrame:
    """Current menu = latest observed price and cost per item."""
    last = sales.sort_values("datetime").groupby("item_id", observed=True).tail(1)
    menu = last[["item_id", "item_name", "category", "unit_price", "unit_cost"]].rename(columns={"unit_price": "price"})
    return menu.astype({"item_id": str, "item_name": str, "category": str}).reset_index(drop=True)


def load_generated(seed: int = 42, end: str | None = None, days: int = 365, n_branches: int = 2) -> Dataset:
    from .catalog import make_branches
    raw = generate_dataset(end=end, days=days, seed=seed,
                           branches=None if n_branches == 2 else make_branches(n_branches, seed))
    sales, notes = prepare_sales(raw["sales"])
    end_s = sales["date"].max().strftime("%Y-%m-%d")
    return Dataset(
        sales=sales, calendar=raw["calendar"], menu=raw["menu"], recipes=raw["recipes"],
        ingredients=raw["ingredients"], incidents=raw["incidents"], truth=raw["truth"],
        source="generated", dataset_id=f"gen-{seed}-{days}-{end_s}" + (f"-b{n_branches}" if n_branches != 2 else ""),
        notes=notes,
    )


def load_csv(file_or_bytes, name: str = "upload.csv") -> Dataset:
    """Load a POS export (CSV) uploaded by the user."""
    data = file_or_bytes if isinstance(file_or_bytes, (bytes, bytearray)) else file_or_bytes.read()
    digest = hashlib.md5(data).hexdigest()[:10]
    raw = pd.read_csv(io.BytesIO(data))
    sales, notes = prepare_sales(raw)
    cal = build_calendar(sales["date"].min(), sales["date"].max())
    notes.append("Weather for uploaded data is approximated from Tashkent climate averages.")
    notes.append("Ingredient-level purchase planning needs recipes; using sample recipes where item_id matches.")
    recipes, ingredients = reference_tables()
    return Dataset(
        sales=sales, calendar=cal, menu=menu_from_sales(sales), recipes=recipes,
        ingredients=ingredients, source=f"upload: {name}", dataset_id=f"csv-{digest}", notes=notes,
    )


def export_sample_csv(path: Path | None = None, seed: int = 42, days: int = 90) -> Path:
    """Write a small sample POS export that matches the upload schema."""
    path = path or DATA_DIR / "sample_pos_export.csv"
    raw = generate_dataset(days=days, seed=seed)["sales"]
    path.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(path, index=False)
    return path


def daily_totals(sales: pd.DataFrame, branch: str | None = None) -> pd.DataFrame:
    """Daily revenue, orders, covers, food cost per branch (complete date grid)."""
    s = sales if branch in (None, "All branches") else sales[sales["branch"] == branch]
    orders = s.drop_duplicates("order_id")[["order_id", "date", "branch", "covers"]]
    agg = s.groupby(["date", "branch"], observed=True).agg(revenue=("revenue", "sum"), food_cost=("food_cost", "sum"))
    o = orders.groupby(["date", "branch"], observed=True).agg(orders=("order_id", "size"), covers=("covers", "sum"))
    out = agg.join(o).reset_index()
    branches = out["branch"].unique()
    grid = pd.MultiIndex.from_product([pd.date_range(s["date"].min(), s["date"].max()), branches],
                                      names=["date", "branch"])
    out = out.set_index(["date", "branch"]).reindex(grid, fill_value=0).reset_index()
    out["branch"] = out["branch"].astype(str)
    return out


def safe_div(a, b):
    return np.where(np.asarray(b) == 0, 0.0, np.asarray(a) / np.where(np.asarray(b) == 0, 1, np.asarray(b)))
