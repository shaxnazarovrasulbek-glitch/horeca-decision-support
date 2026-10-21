"""Structured manager feedback on recommendations.

Every recommendation in the app has a "Was this useful?" thumbs up / down and an optional
comment. Each click is one row in a CSV log, so a pilot can measure how useful the
recommendations are for real branch and operations managers (by module, over time).

The log lives in ``data/feedback_log.csv`` (set ``HORECA_FEEDBACK_FILE`` to change it) and is
not committed to git.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = ["timestamp", "module", "item", "recommendation", "rating", "comment", "role", "branch", "dataset"]
TARGET_USEFUL = 0.70   # pilot success target: at least 70% of rated recommendations are "useful"


def log_path() -> Path:
    return Path(os.environ.get("HORECA_FEEDBACK_FILE", ROOT / "data" / "feedback_log.csv"))


def record(module: str, item: str, recommendation: str, rating: int | None = None, comment: str = "",
           role: str = "", branch: str = "", dataset: str = "", path: Path | None = None) -> dict:
    """Append one feedback event. rating: 1 = useful, 0 = not useful, None = comment only."""
    path = path or log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"timestamp": datetime.now().isoformat(timespec="seconds"), "module": module, "item": item,
           "recommendation": " ".join(str(recommendation).split())[:300],
           "rating": "" if rating is None else int(rating), "comment": " ".join(str(comment).split())[:500],
           "role": role, "branch": branch, "dataset": dataset}
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)
    return row


def load(path: Path | None = None) -> pd.DataFrame:
    path = path or log_path()
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, dtype={"comment": str, "role": str, "branch": str, "item": str})
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    return df


def latest_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """One rating per (module, item): the manager's last click counts (changing a vote is allowed)."""
    r = df.dropna(subset=["rating"])
    if r.empty:
        return r
    return r.sort_values("timestamp").groupby(["module", "item"], as_index=False).tail(1)


def summary(df: pd.DataFrame) -> pd.DataFrame:
    """Usefulness by module: ratings, share useful, number of comments."""
    r = latest_ratings(df)
    if r.empty:
        return pd.DataFrame(columns=["module", "ratings", "useful", "useful_share", "comments"])
    s = r.groupby("module").agg(ratings=("rating", "size"), useful=("rating", "sum")).reset_index()
    s["useful"] = s["useful"].astype(int)
    s["useful_share"] = s["useful"] / s["ratings"]
    comments = df[df["comment"].fillna("").str.strip() != ""].groupby("module").size()
    s["comments"] = s["module"].map(comments).fillna(0).astype(int)
    return s.sort_values("ratings", ascending=False).reset_index(drop=True)


def overall(df: pd.DataFrame) -> dict:
    r = latest_ratings(df)
    n = len(r)
    useful = int(r["rating"].sum()) if n else 0
    return {"ratings": n, "useful": useful, "useful_share": useful / n if n else None,
            "comments": int((df["comment"].fillna("").str.strip() != "").sum()) if len(df) else 0,
            "target": TARGET_USEFUL}
