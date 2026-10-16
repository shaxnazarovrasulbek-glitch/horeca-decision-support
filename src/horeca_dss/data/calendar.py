"""Calendar features for Uzbekistan: public holidays, Ramadan and climate.

Islamic holiday dates follow the lunar calendar; the values below are the
commonly published approximate dates and may differ by +/- 1 day from the
official announcement.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# name -> demand multiplier for a restaurant (dinner-heavy celebrations go up,
# family-at-home days go down)
FIXED_HOLIDAYS: dict[tuple[int, int], tuple[str, float]] = {
    (1, 1): ("New Year", 0.70),
    (1, 14): ("Defenders' Day", 1.10),
    (3, 8): ("International Women's Day", 1.45),
    (3, 21): ("Navruz", 1.35),
    (5, 9): ("Day of Remembrance", 1.10),
    (9, 1): ("Independence Day", 1.25),
    (10, 1): ("Teachers' Day", 1.15),
    (12, 8): ("Constitution Day", 1.10),
    (12, 31): ("New Year's Eve", 1.40),
}

LUNAR_HOLIDAYS: dict[str, tuple[str, float]] = {
    "2025-03-30": ("Ramazon Hayit", 1.30),
    "2025-06-06": ("Qurbon Hayit", 1.20),
    "2026-03-20": ("Ramazon Hayit", 1.30),
    "2026-05-27": ("Qurbon Hayit", 1.20),
    "2027-03-10": ("Ramazon Hayit", 1.30),
    "2027-05-16": ("Qurbon Hayit", 1.20),
}

RAMADAN: list[tuple[str, str]] = [
    ("2025-03-01", "2025-03-29"),
    ("2026-02-18", "2026-03-19"),
    ("2027-02-08", "2027-03-09"),
]


def holiday_info(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Return holiday name and demand factor for each date."""
    names, factors = [], []
    for d in dates:
        key = d.strftime("%Y-%m-%d")
        if key in LUNAR_HOLIDAYS:
            n, f = LUNAR_HOLIDAYS[key]
        elif (d.month, d.day) in FIXED_HOLIDAYS:
            n, f = FIXED_HOLIDAYS[(d.month, d.day)]
        else:
            n, f = "", 1.0
        names.append(n)
        factors.append(f)
    return pd.DataFrame({"holiday": names, "holiday_factor": factors}, index=dates)


def ramadan_flag(dates: pd.DatetimeIndex) -> np.ndarray:
    flag = np.zeros(len(dates), dtype=bool)
    for start, end in RAMADAN:
        flag |= (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
    return flag


def climate_temperature(dates: pd.DatetimeIndex) -> np.ndarray:
    """Average daily temperature in Tashkent (deg C) by day of year."""
    doy = dates.dayofyear.to_numpy()
    return 15.5 + 13.5 * np.sin(2 * np.pi * (doy - 110) / 365.25)


def build_calendar(start, end, seed: int = 7, temps: pd.Series | None = None,
                   promo_dates: set | None = None) -> pd.DataFrame:
    """Daily calendar with weather, holidays, Ramadan and promo flags."""
    dates = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="D")
    cal = holiday_info(dates)
    cal["ramadan"] = ramadan_flag(dates)
    if temps is not None:
        cal["temp_c"] = temps.reindex(dates).to_numpy()
        missing = cal["temp_c"].isna()
        cal.loc[missing, "temp_c"] = climate_temperature(dates[missing])
    else:
        rng = np.random.default_rng(seed)
        noise = np.zeros(len(dates))
        for i in range(1, len(dates)):  # AR(1) weather anomalies
            noise[i] = 0.75 * noise[i - 1] + rng.normal(0, 2.2)
        cal["temp_c"] = np.round(climate_temperature(dates) + noise, 1)
    promo_dates = promo_dates or set()
    cal["promo"] = [d.strftime("%Y-%m-%d") in promo_dates for d in dates]
    cal.index.name = "date"
    return cal.reset_index()


def extend_calendar(cal: pd.DataFrame, days: int, promo: bool = False) -> pd.DataFrame:
    """Append `days` future dates using climatology for temperature."""
    last = pd.Timestamp(cal["date"].max())
    future = pd.date_range(last + pd.Timedelta(days=1), periods=days, freq="D")
    f = holiday_info(future)
    f["ramadan"] = ramadan_flag(future)
    f["temp_c"] = np.round(climate_temperature(future), 1)
    f["promo"] = promo
    f.index.name = "date"
    return pd.concat([cal, f.reset_index()], ignore_index=True)
