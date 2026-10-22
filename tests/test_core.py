"""Unit and integration tests for the analytics core (run: pytest -q)."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

from horeca_dss import assistant, basket, forecasting, kpis, menu_engineering, operations, pricing
from horeca_dss.analysis import Settings, commercial_bundle, forecast_bundle, kpi_bundle, operations_bundle
from horeca_dss.data.generator import generate_dataset
from horeca_dss.data.loader import REQUIRED_COLUMNS, daily_totals, load_csv, load_generated


@pytest.fixture(scope="session")
def ds():
    return load_generated(seed=3, end="2026-06-30", days=300)


# ---- data ---------------------------------------------------------------------------------

def test_generator_schema_and_determinism():
    a = generate_dataset(end="2026-03-31", days=60, seed=11)["sales"]
    b = generate_dataset(end="2026-03-31", days=60, seed=11)["sales"]
    for c in REQUIRED_COLUMNS:
        assert c in a.columns
    assert (a["qty"] > 0).all() and (a["unit_price"] > 0).all()
    assert a["branch"].nunique() == 2
    assert a["qty"].sum() == b["qty"].sum()                     # same seed -> same data
    assert (a["unit_cost"] < a["unit_price"]).all()


def test_upload_with_minimal_columns():
    raw = generate_dataset(end="2026-03-31", days=30, seed=5)["sales"]
    minimal = raw[["order_id", "datetime", "branch", "item_name", "qty", "unit_price"]]
    buf = io.BytesIO()
    minimal.to_csv(buf, index=False)
    up = load_csv(buf.getvalue(), "minimal.csv")
    assert len(up.sales) == len(raw)
    assert up.sales["unit_cost"].gt(0).all()                     # derived from price
    assert any("food cost" in n for n in up.notes)


def test_upload_rejects_missing_required():
    df = pd.DataFrame({"order_id": [1], "datetime": ["2026-01-01 12:00"], "qty": [1]})
    with pytest.raises(ValueError):
        load_csv(df.to_csv(index=False).encode(), "bad.csv")


# ---- KPIs & anomalies -------------------------------------------------------------------

def test_kpi_summary_consistency(ds):
    s = kpis.summary(ds.sales)
    assert s["revenue"] == pytest.approx(ds.sales["revenue"].sum())
    assert s["avg_check"] == pytest.approx(s["revenue"] / s["orders"])
    assert 0.15 < s["food_cost_pct"] < 0.45


def test_planted_outage_is_detected(ds):
    an = kpis.detect_anomalies(ds.sales, ds.calendar, lookback_days=400)
    inc = ds.incidents.iloc[0]                                   # power outage
    hit = an[(an["branch"] == inc["branch"]) & (an["date"] == inc["start"])]
    assert len(hit) == 1
    assert hit.iloc[0]["type"] == "drop"
    assert "15:00" in hit.iloc[0]["explanation"]


# ---- forecasting ----------------------------------------------------------------------------

def test_forecast_shape_and_positivity(ds):
    fc = forecasting.DemandForecaster("revenue").fit(daily_totals(ds.sales), ds.calendar).predict(14)
    assert len(fc) == 14 * 2
    assert (fc["forecast"] >= 0).all()
    assert fc["date"].min() == ds.end + pd.Timedelta(days=1)


def test_forecast_beats_naive_baseline(ds):
    bt = forecasting.backtest(ds.sales, ds.calendar, "covers", n_origins=4)
    m = bt["metrics"].set_index("method")["WAPE"]
    assert m.iloc[0] < m.loc["Same weekday last week"]
    assert m.iloc[0] < 0.25


def test_promo_what_if_increases_forecast(ds):
    f = forecasting.DemandForecaster("covers").fit(daily_totals(ds.sales), ds.calendar)
    assert f.predict(7, promo=True)["forecast"].sum() > f.predict(7)["forecast"].sum()


# ---- menu, pricing, basket ---------------------------------------------------------------

def test_menu_engineering_segments():
    rows = []
    # two dishes in one section: A popular + high margin (Star), B unpopular + low margin (Dog)
    for i in range(80):
        rows.append({"order_id": f"o{i}", "item_id": "A", "item_name": "A", "category": "Main", "qty": 1,
                     "revenue": 50000, "food_cost": 15000})
    for i in range(10):
        rows.append({"order_id": f"p{i}", "item_id": "B", "item_name": "B", "category": "Main", "qty": 1,
                     "revenue": 30000, "food_cost": 20000})
    me = menu_engineering.menu_engineering(pd.DataFrame(rows)).set_index("item_id")
    assert me.loc["A", "segment"] == "Star"
    assert me.loc["B", "segment"] == "Dog"


def test_price_recommendation_direction():
    menu = pd.DataFrame({"item_id": ["X", "Y", "Z"], "item_name": ["X", "Y", "Z"], "category": ["Main"] * 3,
                         "price": [40000, 40000, 40000], "unit_cost": [14000, 14000, 14000]})
    el = pd.DataFrame({"item_id": ["X", "Y", "Z"], "elasticity": [-0.3, -2.5, -0.3],
                       "confidence": ["High", "High", "Low"], "method": ["estimated", "estimated", "category prior"]})
    sales = pd.DataFrame({"item_id": ["X", "Y", "Z"], "qty": [3000, 3000, 3000]})
    rec = pricing.price_recommendations(sales, menu, el, 30).set_index("item_id")
    assert rec.loc["X", "recommended_price"] > 40000             # inelastic -> raise
    assert rec.loc["Y", "recommended_price"] <= 40000            # elastic -> do not raise
    assert rec.loc["Z", "recommended_price"] == 40000            # low confidence -> test first


def test_elasticity_sign(ds):
    el = pricing.estimate_elasticities(ds.sales, ds.calendar)
    est = el[el["method"].str.startswith("estimated")]
    assert len(est) >= 5
    assert (est["elasticity"] < 0).all()


def test_basket_finds_planted_pairs(ds):
    s = kpis.filter_sales(ds.sales, ds.end - pd.Timedelta(days=89), ds.end)
    rules = basket.pair_rules(s)
    pairs = {(r.antecedent_id, r.consequent_id): r.lift for r in rules.itertuples()}
    assert pairs.get(("M06", "X02"), 0) > 1.5                    # burger -> fries
    assert pairs.get(("M01", "S01"), 0) > 1.3                    # plov -> achichuk
    up = basket.upsell_opportunities(rules, ds.menu, 90)
    assert (up["extra_revenue_month"] > 0).all()


# ---- operations ------------------------------------------------------------------------------

def test_staffing_respects_standards():
    hourly = pd.DataFrame({"date": pd.Timestamp("2026-01-01"), "branch": "A", "hour": [10, 13, 20],
                           "value": [2.0, 25.0, 40.0]})
    std = operations.StaffStandards(covers_per_waiter_hour=12, covers_per_cook_hour=18)
    plan = operations.staffing_plan(hourly, std)
    assert plan["waiters"].tolist() == [1, 3, 4]
    assert plan["cooks"].tolist() == [1, 2, 3]


def test_waste_backtest_ai_beats_naive(ds):
    wb = operations.waste_backtest(ds.sales, ds.calendar, ds.recipes, ds.ingredients, weeks=2)
    assert wb["waste_reduction"] > 0


# ---- assistant ---------------------------------------------------------------------------------

@pytest.fixture(scope="session")
def facts(ds):
    st = Settings()
    fc = forecast_bundle(ds, 14)
    return assistant.build_facts(ds, kpi_bundle(ds, st), commercial_bundle(ds, st), fc,
                                 operations_bundle(ds, fc["covers"], st))


@pytest.mark.parametrize("q,expect", [
    ("Why did revenue drop on Tuesday?", "Why:"),
    ("What should we promote this weekend?", "rarely ordered"),
    ("Which prices should we change?", "Price"),
    ("How many waiters do we need?", "staff-hours"),
    ("Что закупить?", "Purchase plan"),
])
def test_offline_assistant_intents(facts, q, expect):
    bot = assistant.Assistant(facts, api_key=None)
    bot.client = None                                            # force offline even if a key is set
    res = bot.ask(q)
    assert expect in res["text"]
    assert res["engine"].startswith("Offline")


class _Resp:
    def __init__(self, code, payload=None):
        self.status_code, self._p = code, payload or {}

    def json(self):
        return self._p


def test_gemini_success_and_fallback(facts, monkeypatch):
    ok = {"candidates": [{"content": {"parts": [{"text": "Revenue fell because of an outage."}]}}]}
    monkeypatch.setattr(assistant.requests, "post", lambda *a, **k: _Resp(200, ok))
    bot = assistant.Assistant(facts, api_key="test-key", model="gemini-test")
    res = bot.ask("Why did revenue drop?")
    assert res["engine"].startswith("Gemini") and "outage" in res["text"]

    monkeypatch.setattr(assistant.requests, "post", lambda *a, **k: _Resp(429))
    res = bot.ask("Why did revenue drop?")
    assert res["engine"].startswith("Offline") and res["error"]


def test_context_contains_key_numbers(facts):
    ctx = assistant.context_text(facts)
    assert "FORECAST next 7 days" in ctx and "MENU GROUPS" in ctx and "Popular & profitable" in ctx and "UPSELL" in ctx
    assert len(ctx) < 12000                                      # stays small for the free tier


# ---- added after the PM mentor review (21 Oct 2026) ----------------------------------------

def test_feedback_log_roundtrip(tmp_path):
    from horeca_dss import feedback as fb
    path = tmp_path / "fb.csv"
    fb.record("Pricing", "Plov", "Plov 49000 -> 52000", rating=1, role="Branch manager", path=path)
    fb.record("Pricing", "Plov", "Plov 49000 -> 52000", rating=0, role="Branch manager", path=path)  # changed vote
    fb.record("Upsell", "Medovik", "With Medovik suggest Cappuccino", rating=1, path=path)
    fb.record("Upsell", "Medovik", "", rating=None, comment="Good, but not at lunch", path=path)
    df = fb.load(path)
    assert len(df) == 4
    s = fb.summary(df).set_index("module")
    assert s.loc["Pricing", "ratings"] == 1 and s.loc["Pricing", "useful"] == 0   # last vote counts
    assert s.loc["Upsell", "useful_share"] == 1.0 and s.loc["Upsell", "comments"] == 1
    ov = fb.overall(df)
    assert ov["ratings"] == 2 and ov["useful_share"] == 0.5 and ov["comments"] == 1


def test_feedback_empty(tmp_path):
    from horeca_dss import feedback as fb
    df = fb.load(tmp_path / "missing.csv")
    assert df.empty and fb.summary(df).empty and fb.overall(df)["useful_share"] is None


def test_more_branches_for_scale_test():
    from horeca_dss.data.catalog import make_branches
    from horeca_dss.data.loader import load_generated
    br = make_branches(5)
    assert len(br) == 5 and len({b.name for b in br}) == 5
    ds = load_generated(seed=3, end="2026-03-31", days=60, n_branches=4)
    assert ds.sales["branch"].nunique() == 4 and ds.dataset_id.endswith("-b4")
    assert ds.sales["order_id"].is_unique is False or ds.sales["order_id"].nunique() > 0


def test_gemini_payload_and_timing(monkeypatch):
    from horeca_dss import assistant as a
    p = a.build_payload("sys", [{"role": "user", "parts": [{"text": "hi"}]}], "gemini-2.5-flash")
    assert p["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert "thinkingConfig" not in a.build_payload("sys", [], "gemini-flash-latest")["generationConfig"]

    class R:
        def __init__(self, code, body=None):
            self.status_code, self._b = code, body or {}

        def json(self):
            return self._b

    calls = []

    def fake_post(url, json, timeout, headers):
        calls.append(("thinkingConfig" in json["generationConfig"], url))
        if len(calls) == 1:
            return R(400)          # model rejects the thinking setting -> retry without it
        return R(200, {"candidates": [{"content": {"parts": [{"text": "Revenue fell because of the outage."}]}}]})

    monkeypatch.setattr(a.requests, "post", fake_post)
    facts = {"kpis": {}, "alerts": []}
    monkeypatch.setattr(a, "context_text", lambda f: "CONTEXT")
    bot = a.Assistant(facts, api_key="test-key")
    res = bot.ask("Why did revenue drop?")
    assert res["engine"].startswith("Gemini") and res["error"] is None
    assert res["seconds"] is not None and res["seconds"] >= 0
    assert calls[0][0] is True and calls[1][0] is False


def test_precomputed_results_match_fresh_computation():
    """The stored results for the default demo data must equal a fresh computation."""
    from pandas.testing import assert_frame_equal
    from horeca_dss import precompute
    from horeca_dss.data.loader import load_generated
    ds = load_generated(seed=42, end="2026-10-15", days=365)
    pre = precompute.load("backtest_revenue", ds.dataset_id)
    assert pre is not None, "run python scripts/precompute.py"
    fresh = forecasting.backtest(ds.sales, ds.calendar, "revenue")
    for key in ("predictions", "metrics", "by_day_type"):
        assert_frame_equal(pre[key].reset_index(drop=True), fresh[key].reset_index(drop=True),
                           check_dtype=False, check_exact=False, rtol=1e-9)
    assert abs(pre["improvement_vs_best_baseline"] - fresh["improvement_vs_best_baseline"]) < 1e-12
    assert tuple(pre["band"]) == tuple(fresh["band"]) and pre["horizon"] == fresh["horizon"]
    wb = precompute.load("waste_backtest", ds.dataset_id)
    assert wb is not None and abs(wb["waste_reduction"] - 0.3526042006292438) < 1e-9
    assert precompute.load("backtest_revenue", "some-other-dataset") is None
