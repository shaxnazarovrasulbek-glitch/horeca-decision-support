"""One entry point that runs every module and returns the results the UI and the
AI assistant use. Keeping this in one place guarantees the dashboard and the
assistant always talk about the same numbers."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import basket, forecasting, kpis, menu_engineering, operations, pricing
from .data.loader import Dataset, daily_totals


@dataclass
class Settings:
    period_days: int = 28           # KPI / menu / pricing window
    basket_days: int = 90           # market-basket window
    horizon: int = 14               # forecast horizon (days)
    upsell_acceptance: float = 0.10
    combo_discount: float = 0.07
    safety_stock: float = 0.10
    staff: operations.StaffStandards = field(default_factory=operations.StaffStandards)


def forecast_bundle(ds: Dataset, horizon: int = 14, promo: bool = False) -> dict:
    daily = daily_totals(ds.sales)
    out = {}
    for target in ("revenue", "covers"):
        out[target] = forecasting.DemandForecaster(target).fit(daily, ds.calendar).predict(horizon, promo=promo)
    out["daily"] = daily
    return out


def operations_bundle(ds: Dataset, cover_fc: pd.DataFrame, settings: Settings, days: int = 7) -> dict:
    fc = cover_fc[cover_fc["date"] <= cover_fc["date"].min() + pd.Timedelta(days=days - 1)]
    hourly = forecasting.split_hourly(fc, forecasting.hourly_profile(ds.sales))
    plan = operations.staffing_plan(hourly, settings.staff)
    comparison = operations.compare_to_fixed_schedule(plan, settings.staff)
    out = {"hourly": hourly, "staffing": plan, "staff_comparison": comparison}
    if ds.recipes is not None and ds.ingredients is not None:
        items = forecasting.item_forecast(fc, forecasting.item_mix(ds.sales))
        needs = operations.ingredient_needs(items, ds.recipes, ds.ingredients)
        out.update(item_forecast=items, needs=needs, purchase=operations.purchase_list(needs, settings.safety_stock))
    return out


def commercial_bundle(ds: Dataset, settings: Settings, branch: str | None = None) -> dict:
    end = ds.end
    period = kpis.filter_sales(ds.sales, end - pd.Timedelta(days=settings.period_days - 1), end, branch)
    bwin = kpis.filter_sales(ds.sales, end - pd.Timedelta(days=settings.basket_days - 1), end, branch)
    me = menu_engineering.menu_engineering(period)
    el = pricing.estimate_elasticities(ds.sales if branch in (None, kpis.ALL) else
                                       kpis.filter_sales(ds.sales, branch=branch), ds.calendar)
    prices = pricing.price_recommendations(period, ds.menu, el, settings.period_days)
    rules = basket.pair_rules(bwin)
    upsell = basket.upsell_opportunities(rules, ds.menu, settings.basket_days, settings.upsell_acceptance)
    combos = basket.combo_suggestions(rules, ds.menu, settings.combo_discount)
    return {"menu": me, "segments": menu_engineering.segment_summary(me), "elasticities": el,
            "prices": prices, "rules": rules, "upsell": upsell, "combos": combos}


def kpi_bundle(ds: Dataset, settings: Settings, branch: str | None = None) -> dict:
    return {
        "compare": kpis.compare_periods(ds.sales, ds.end, settings.period_days, branch),
        "weekly": kpis.weekly_revenue(ds.sales, branch),
        "anomalies": kpis.detect_anomalies(ds.sales, ds.calendar),
        "category_mix": kpis.category_mix(
            kpis.filter_sales(ds.sales, ds.end - pd.Timedelta(days=settings.period_days - 1), ds.end, branch)),
    }
