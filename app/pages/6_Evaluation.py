"""Evaluation: how well does each module work, and what is it worth? (for the internship report)"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from horeca_dss.data.catalog import COMPANIONS, DESSERT_COMPANIONS

ui.page("Evaluation", ":material/science:")
ds = ui.get_dataset()
_, period = ui.sidebar(ds, show_branch=False)

st.title("Evaluation")
st.caption("Back-tests and simulations that measure each module. With generated data we also know the ground "
           "truth (planted price sensitivities, item pairings and incidents), so we can check that the methods recover it.")

bt_r = ui.backtest(ds.dataset_id, "revenue", ds)
bt_c = ui.backtest(ds.dataset_id, "covers", ds)
c = ui.commercial_bundle(ds.dataset_id, ui.ALL, period, st.session_state.get("upsell_acceptance", 0.10), ds)
ops = ui.operations_bundle(ds.dataset_id, 14, ui.staff_tuple(), 0.10, 7, ds)
wb = ui.waste_backtest(ds.dataset_id, ds) if ds.recipes is not None else None
k = ui.kpi_bundle(ds.dataset_id, ui.ALL, period, ds)

# ---- business impact -------------------------------------------------------------------
prices = c["prices"]
price_gain = prices.loc[prices["recommended_price"] != prices["current_price"], "cm_uplift_month"].sum()
upsell_gain = c["upsell"].head(5)["extra_cm_month"].sum()
labour_gain = ops["staff_comparison"]["cost_saved"].sum() * 30 / 7
waste_gain = 0.0
if wb is not None:
    s = wb["summary"]
    diff = s.loc[s["method"].str.startswith("Naive"), "waste_cost"].iloc[0] - s.loc[s["method"].str.startswith("AI"), "waste_cost"].iloc[0]
    waste_gain = diff * 30 / (7 * wb["weeks"])
monthly_rev = k["compare"]["current"]["revenue"] * 30 / period
impact = pd.DataFrame([
    {"lever": "Price changes (confident items only)", "monthly_gain": price_gain, "basis": "elasticity model, volume drop ≤ 8%"},
    {"lever": "Upsell scripts (top 5)", "monthly_gain": upsell_gain, "basis": f"{st.session_state.get('upsell_acceptance', 0.10):.0%} of guests accept"},
    {"lever": "Demand-based staff schedule", "monthly_gain": labour_gain, "basis": "vs fixed schedule at 85th percentile"},
    {"lever": "Forecast-based perishable ordering", "monthly_gain": waste_gain, "basis": "simulated last 4 weeks vs 'last week + 15%'"},
])
total = impact["monthly_gain"].sum()
st.subheader("Estimated business impact")
m1, m2, m3 = st.columns(3)
ui.metric(m1, "Total gain per month (margin + cost savings)", ui.uzs(total), border=True)
ui.metric(m2, "Relative to monthly revenue", f"{total / monthly_rev:.1%}", f"of {ui.uzs(monthly_rev)}", note=True, border=True)
ui.metric(m3, "Per year", ui.uzs(total * 12), border=True)
fig = go.Figure(go.Bar(x=impact["monthly_gain"], y=impact["lever"], orientation="h", marker_color=ui.SERIES[0],
                       marker_line_width=0, text=[ui.uzs(v) for v in impact["monthly_gain"]], textposition="auto",
                       hovertemplate="%{y}: %{x:,.0f} UZS / month<extra></extra>"))
fig.update_yaxes(autorange="reversed")
ui.show(ui.style(fig, 260, legend=False))
ui.table(impact, column_config={"monthly_gain": ui.money_col("Gain / month (UZS)"), "basis": "Assumption"})
st.caption("These are model-based estimates on synthetic data; real impact must be confirmed with an A/B pilot.")

# ---- forecast ----------------------------------------------------------------------------
st.subheader("1 · Forecast accuracy (rolling-origin back-test)")
rows = []
for name, bt in [("Revenue", bt_r), ("Guests", bt_c)]:
    m = bt["metrics"].set_index("method")
    rows.append({"target": name, "AI model WAPE": m.iloc[0]["WAPE"], "Same weekday last week": m.iloc[1]["WAPE"],
                 "Avg of last 4 same weekdays": m.iloc[2]["WAPE"], "Improvement vs best rule": bt["improvement_vs_best_baseline"],
                 "AI model bias": m.iloc[0]["bias"]})
fc_tab = pd.DataFrame(rows)
ui.table(fc_tab, column_config={col: st.column_config.NumberColumn(col, format="percent") for col in fc_tab.columns[1:]})
bd = bt_r["by_day_type"]
st.caption("Revenue WAPE by type of day — the model's advantage comes from knowing holidays, promotions and Ramadan:")
ui.table(bd, column_config={c: st.column_config.NumberColumn(c, format="percent") for c in bd.columns[2:]}
         | {"n": st.column_config.NumberColumn("Days")})

# ---- elasticity recovery -----------------------------------------------------------------
st.subheader("2 · Price elasticity recovery")
el = c["elasticities"]
if ds.truth is not None:
    s = ds.sales[ds.sales["date"] > ds.end - pd.Timedelta(days=90)]
    share = s.groupby(["category", "item_id"], observed=True)["qty"].sum()
    share = (share / share.groupby(level="category", observed=True).transform("sum")).droplevel("category")
    t = ds.truth.astype({"item_id": str}).set_index("item_id")
    e = el[el["method"].str.startswith("estimated")].astype({"item_id": str}).set_index("item_id")
    e = e.join(t["true_elasticity"]).join(share.rename("share"))
    e["true_effective"] = e["true_elasticity"] * (1 - e["share"])   # within-section substitution
    e = e.join(ds.menu.astype({"item_id": str}).set_index("item_id")["item_name"])
    corr = float(np.corrcoef(e["elasticity"], e["true_effective"])[0, 1]) if len(e) > 2 else float("nan")
    mae = float((e["elasticity"] - e["true_effective"]).abs().mean())
    a1, a2 = st.columns([2, 3])
    ui.metric(a1, "Correlation estimated vs true", f"{corr:.2f}", f"{len(e)} items with price changes", note=True, border=True)
    ui.metric(a1, "Mean absolute error", f"{mae:.2f}", note=True, border=True)
    a1.caption("Approximate true value = planted elasticity × (1 − item share), the effective response when guests switch "
               "between dishes of the same section. Items without price changes use a category prior.")
    fig = go.Figure(go.Scatter(x=e["true_effective"], y=e["elasticity"], mode="markers+text", text=e["item_name"],
                               textposition="top center", textfont=dict(size=10),
                               marker=dict(size=10, color=ui.SERIES[0], line=dict(width=2, color="white")),
                               hovertemplate="%{text}<br>true %{x:.2f} · estimated %{y:.2f}<extra></extra>"))
    lim = [min(e["true_effective"].min(), e["elasticity"].min()) - 0.2, 0]
    fig.add_trace(go.Scatter(x=lim, y=lim, mode="lines", line=dict(color=ui.MUTED, dash="dot", width=1), hoverinfo="skip"))
    fig.update_xaxes(title="true effective elasticity")
    fig.update_yaxes(title="estimated")
    with a2:
        ui.show(ui.style(fig, 360, legend=False))
else:
    st.info("Ground truth is only available for generated data.")

# ---- basket + anomalies ------------------------------------------------------------------
st.subheader("3 · Item pairings and incidents found")
b1, b2 = st.columns(2)
with b1:
    planted = {(a, b) for a, comps in {**COMPANIONS, **DESSERT_COMPANIONS}.items() for b, _ in comps}
    found = {(r.antecedent_id, r.consequent_id) for r in c["rules"].itertuples() if r.lift >= 1.5}
    hit = planted & found
    ui.metric(st, "Planted pairings recovered (lift ≥ 1.5)", f"{len(hit)} / {len(planted)}", border=True)
    names = ds.menu.astype({"item_id": str}).set_index("item_id")["item_name"]
    st.caption("Recovered: " + ", ".join(f"{names[a]} → {names[b]}" for a, b in sorted(hit)))
with b2:
    if ds.incidents is not None:
        an = ui.kpis.detect_anomalies(ds.sales, ds.calendar, lookback_days=400)
        drops = an[an["type"] == "drop"]
        rows = []
        for inc in ds.incidents.itertuples():
            days = pd.date_range(inc.start, inc.end)
            det = drops[(drops["branch"] == inc.branch) & (drops["date"].isin(days))]
            rows.append({"incident": inc.description, "branch": inc.branch, "dates": f"{inc.start:%d %b} – {inc.end:%d %b}",
                         "detected days": f"{len(det)} / {len(days)}"})
        ui.metric(st, "Incidents detected", f"{sum(int(r['detected days'].split('/')[0]) > 0 for r in rows)} / {len(rows)}", border=True)
        ui.table(pd.DataFrame(rows))

# ---- export --------------------------------------------------------------------------------
st.subheader("Export for the report")
md = ["# Evaluation results", "", f"Data: {ds.source}, {ds.start:%Y-%m-%d} – {ds.end:%Y-%m-%d}", "",
      "## Business impact (per month)", ui.to_markdown(impact.assign(monthly_gain=impact["monthly_gain"].round(0))), "",
      "## Forecast accuracy (WAPE)", ui.to_markdown(fc_tab.round(4)), "",
      "## Revenue WAPE by day type", ui.to_markdown(bd.round(4))]
st.download_button("Download results (Markdown)", "\n".join(md), file_name="evaluation_results.md", icon=":material/download:")

ui.footer()
