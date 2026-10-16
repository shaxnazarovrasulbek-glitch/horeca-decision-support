"""Daily demand forecasting with gradient boosting + calendar/weather features.

Design
------
* One global model across branches (branch is a categorical feature).
* The target is modelled *relative to the recent level* (log ratio to the
  28-day mean lagged by 7 days) so that tree models can follow growth trends.
* Multi-step forecasts are produced recursively (lags of 7+ days only).
* Accuracy is measured with a rolling-origin backtest against two baselines
  that restaurant managers actually use: "same weekday last week" (seasonal
  naive) and "average of the last 4 same weekdays".
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .data.calendar import extend_calendar
from .data.loader import daily_totals

TARGETS = {"revenue": "Revenue (UZS)", "covers": "Guests (covers)", "orders": "Orders"}
FEATURES = ["branch_code", "dow", "month", "doy_sin", "doy_cos", "holiday_type",
            "promo", "ramadan", "temp_c", "lag7_r", "lag14_r", "lag21_r", "lag28_r", "ma4_r", "level_log"]
CATEGORICAL = ["branch_code", "dow", "holiday_type"]
MIN_HISTORY = 35


def _features(y: pd.Series, cal: pd.DataFrame, branch_code: int) -> pd.DataFrame:
    """Feature frame for one branch; `y` indexed by consecutive dates (may end with NaNs)."""
    df = pd.DataFrame({"y": y})
    level = y.shift(7).rolling(28, min_periods=14).mean()
    df["level"] = level
    df["level_log"] = np.log1p(level)
    for k in (7, 14, 21, 28):
        df[f"lag{k}_r"] = np.log1p(y.shift(k)) - np.log1p(level)
    ma4 = pd.concat([y.shift(k) for k in (7, 14, 21, 28)], axis=1).mean(axis=1)
    df["ma4_r"] = np.log1p(ma4) - np.log1p(level)
    c = cal.reindex(df.index)
    df["branch_code"] = branch_code
    df["dow"] = df.index.dayofweek
    df["month"] = df.index.month
    doy = df.index.dayofyear
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    # holiday type is domain knowledge: celebration (people dine out) vs stay-at-home day
    hf = c["holiday_factor"].fillna(1.0).to_numpy()
    df["holiday_type"] = np.where(hf > 1.0, 1, np.where(hf < 1.0, 2, 0))
    df["promo"] = c["promo"].fillna(False).astype(int).to_numpy()
    df["ramadan"] = c["ramadan"].fillna(False).astype(int).to_numpy()
    df["temp_c"] = c["temp_c"].to_numpy()
    df["target"] = np.log1p(y) - np.log1p(level)
    return df


@dataclass
class DemandForecaster:
    target: str = "revenue"
    random_state: int = 0

    def fit(self, daily: pd.DataFrame, calendar: pd.DataFrame, train_end=None) -> "DemandForecaster":
        self.calendar = calendar.set_index(pd.to_datetime(calendar["date"]))
        self.branches = sorted(daily["branch"].unique())
        self.history: dict[str, pd.Series] = {}
        frames = []
        for code, b in enumerate(self.branches):
            y = daily[daily["branch"] == b].set_index("date")[self.target].astype(float).sort_index()
            if train_end is not None:
                y = y[y.index <= pd.Timestamp(train_end)]
            self.history[b] = y
            frames.append(_features(y, self.calendar, code))
        train = pd.concat(frames).dropna(subset=["target", "lag28_r"])
        train = train[np.isfinite(train["target"])]
        self.model = HistGradientBoostingRegressor(
            max_iter=250, learning_rate=0.04, max_leaf_nodes=8, min_samples_leaf=15,
            l2_regularization=2.0, categorical_features=[FEATURES.index(c) for c in CATEGORICAL],
            random_state=self.random_state)
        self.model.fit(train[FEATURES].to_numpy(), train["target"].to_numpy())
        resid = train["target"] - self.model.predict(train[FEATURES].to_numpy())
        self.in_sample_std = float(resid.std())
        return self

    def predict(self, horizon: int = 14, promo: bool = False) -> pd.DataFrame:
        """Recursive forecast for `horizon` days after the end of the training data."""
        last = max(s.index.max() for s in self.history.values())
        cal = self.calendar
        if cal.index.max() < last + pd.Timedelta(days=horizon):
            ext = extend_calendar(cal.reset_index(drop=True), (last + pd.Timedelta(days=horizon) - cal.index.max()).days)
            cal = ext.set_index(pd.to_datetime(ext["date"]))
        if promo:
            cal = cal.copy()
            cal.loc[cal.index > last, "promo"] = True
        out = []
        for code, b in enumerate(self.branches):
            y = self.history[b].copy()
            for step in range(1, horizon + 1):
                d = last + pd.Timedelta(days=step)
                y.loc[d] = np.nan
                tail = y.iloc[-40:]
                row = _features(tail, cal, code).iloc[[-1]]
                pred_log_ratio = self.model.predict(row[FEATURES].to_numpy())[0]
                yhat = max(float(np.expm1(pred_log_ratio + row["level_log"].iloc[0])), 0.0)
                y.loc[d] = yhat
                out.append({"date": d, "branch": b, "forecast": yhat})
        return pd.DataFrame(out)


def _baselines(y: pd.Series, origin: pd.Timestamp, horizon: int) -> pd.DataFrame:
    hist = y[y.index <= origin]
    rows = []
    for step in range(1, horizon + 1):
        d = origin + pd.Timedelta(days=step)
        same = hist[hist.index.dayofweek == d.dayofweek]
        rows.append({"date": d, "snaive": float(same.iloc[-1]) if len(same) else np.nan,
                     "ma4": float(same.iloc[-4:].mean()) if len(same) else np.nan})
    return pd.DataFrame(rows)


def wape(actual, forecast) -> float:
    a, f = np.asarray(actual, float), np.asarray(forecast, float)
    return float(np.abs(a - f).sum() / max(np.abs(a).sum(), 1e-9))


def mape(actual, forecast) -> float:
    a, f = np.asarray(actual, float), np.asarray(forecast, float)
    m = a > 0
    return float(np.mean(np.abs(a[m] - f[m]) / a[m])) if m.any() else float("nan")


def bias(actual, forecast) -> float:
    a, f = np.asarray(actual, float), np.asarray(forecast, float)
    return float((f - a).sum() / max(a.sum(), 1e-9))


def backtest(sales: pd.DataFrame, calendar: pd.DataFrame, target: str = "revenue",
             n_origins: int = 8, horizon: int = 14, step: int = 7) -> dict:
    """Rolling-origin evaluation: refit at each origin, forecast `horizon` days."""
    daily = daily_totals(sales)
    end = daily["date"].max()
    origins = [end - pd.Timedelta(days=horizon + step * i) for i in range(n_origins)][::-1]
    preds = []
    for origin in origins:
        fc = DemandForecaster(target).fit(daily, calendar, train_end=origin).predict(horizon)
        for b in fc["branch"].unique():
            y = daily[daily["branch"] == b].set_index("date")[target].astype(float)
            base = _baselines(y, origin, horizon)
            f = fc[fc["branch"] == b].merge(base, on="date")
            f["actual"] = y.reindex(f["date"]).to_numpy()
            f["origin"] = origin
            f["h"] = (f["date"] - origin).dt.days
            preds.append(f)
    p = pd.concat(preds, ignore_index=True)
    metrics = []
    for name, col in [("AI model (gradient boosting)", "forecast"), ("Same weekday last week", "snaive"),
                      ("Average of last 4 same weekdays", "ma4")]:
        metrics.append({"method": name, "WAPE": wape(p["actual"], p[col]), "MAPE": mape(p["actual"], p[col]),
                        "bias": bias(p["actual"], p[col])})
    m = pd.DataFrame(metrics)
    # accuracy on "special" days (holidays, promo campaigns, Ramadan) vs normal days
    cal = calendar.assign(date=pd.to_datetime(calendar["date"])).set_index("date")
    special = cal.reindex(p["date"])
    p["special"] = ((special["holiday"].fillna("") != "") | special["promo"].fillna(False).astype(bool)
                    | special["ramadan"].fillna(False).astype(bool)).to_numpy()
    rows = []
    for flag, g in p.groupby("special"):
        rows.append({"days": "holiday / promo / Ramadan" if flag else "normal days", "n": len(g),
                     "AI model": wape(g["actual"], g["forecast"]), "Same weekday last week": wape(g["actual"], g["snaive"]),
                     "Average of last 4 same weekdays": wape(g["actual"], g["ma4"])})
    by_day_type = pd.DataFrame(rows)
    ratio = (p["actual"] / p["forecast"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).dropna()
    band = (float(ratio.quantile(0.10)), float(ratio.quantile(0.90))) if len(ratio) > 10 else (0.85, 1.15)
    best_base = m.iloc[1:]["WAPE"].min()
    improvement = 1 - m.iloc[0]["WAPE"] / best_base if best_base > 0 else 0.0
    return {"predictions": p, "metrics": m, "band": band, "improvement_vs_best_baseline": improvement,
            "by_day_type": by_day_type,
            "origins": origins, "horizon": horizon, "target": target}


# ---- disaggregation: day -> hour, covers -> menu items ---------------------------------

def hourly_profile(sales: pd.DataFrame, weeks: int = 8) -> pd.DataFrame:
    """Share of a day's guests that arrive in each hour, by branch and weekday."""
    s = sales[sales["date"] > sales["date"].max() - pd.Timedelta(weeks=weeks)]
    o = s.drop_duplicates("order_id")
    g = o.groupby(["branch", o["date"].dt.dayofweek.rename("dow"), "hour"], observed=True)["covers"].sum()
    share = g / g.groupby(level=["branch", "dow"], observed=True).transform("sum")
    return share.rename("share").reset_index().astype({"branch": str})


def split_hourly(daily_fc: pd.DataFrame, profile: pd.DataFrame, value: str = "forecast") -> pd.DataFrame:
    f = daily_fc.assign(dow=daily_fc["date"].dt.dayofweek)
    out = f.merge(profile, on=["branch", "dow"], how="left")
    out["value"] = out[value] * out["share"]
    return out[["date", "branch", "hour", "value"]]


def item_mix(sales: pd.DataFrame, weeks: int = 4) -> pd.DataFrame:
    """Portions of each menu item sold per guest, by branch and weekday."""
    s = sales[sales["date"] > sales["date"].max() - pd.Timedelta(weeks=weeks)]
    covers = (s.drop_duplicates("order_id")
              .groupby(["branch", s.drop_duplicates("order_id")["date"].dt.dayofweek.rename("dow")], observed=True)["covers"].sum())
    qty = s.groupby(["branch", s["date"].dt.dayofweek.rename("dow"), "item_id"], observed=True)["qty"].sum()
    mix = qty / covers.reindex(qty.index.droplevel("item_id")).to_numpy()
    return mix.rename("qty_per_cover").reset_index().astype({"branch": str, "item_id": str})


def item_forecast(cover_fc: pd.DataFrame, mix: pd.DataFrame) -> pd.DataFrame:
    f = cover_fc.assign(dow=cover_fc["date"].dt.dayofweek)
    out = f.merge(mix, on=["branch", "dow"], how="left")
    out["qty"] = out["forecast"] * out["qty_per_cover"]
    return out[["date", "branch", "item_id", "qty"]]
