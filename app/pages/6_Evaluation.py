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

# ---- manager feedback ------------------------------------------------------------------------
st.subheader("4 · Manager feedback on recommendations")
log = ui.fb.load()
ov = ui.fb.overall(log)
f1, f2, f3 = st.columns(3)
ui.metric(f1, "Recommendations rated", ui.num(ov["ratings"]), border=True)
ui.metric(f2, "Rated useful", "–" if ov["useful_share"] is None else f"{ov['useful_share']:.0%}",
          f"pilot target: at least {ov['target']:.0%}", note=True, border=True)
ui.metric(f3, "Comments", ui.num(ov["comments"]), border=True)
fb_summary = ui.fb.summary(log)
if ov["ratings"] == 0 and ov["comments"] == 0:
    st.info("No ratings yet. Every recommendation in the app has a 👍 / 👎 and a comment box. Each click is saved "
            "with the manager's role (sidebar), so in the pilot we can measure how useful each module is for "
            "branch and operations managers.", icon=":material/thumbs_up_down:")
else:
    ui.table(fb_summary, column_config={"module": "Module", "ratings": "Ratings", "useful": "Useful",
                                        "useful_share": st.column_config.NumberColumn("Share useful", format="percent"),
                                        "comments": "Comments"})
    com = log[log["comment"].fillna("").str.strip() != ""].sort_values("timestamp", ascending=False)
    if len(com):
        st.caption("Latest comments")
        ui.table(com[["timestamp", "module", "role", "comment"]].head(8),
                 column_config={"timestamp": st.column_config.DatetimeColumn("When", format="DD MMM HH:mm")})
    st.download_button("Download feedback log (CSV)", log.to_csv(index=False), file_name="feedback_log.csv",
                       icon=":material/download:")

# ---- scale test --------------------------------------------------------------------------
st.subheader("5 · Scale test: more branches, more data")
scale_file = ui.ROOT / "docs" / "scale_test.json"
scale = pd.read_json(scale_file) if scale_file.exists() else None
if scale is not None and len(scale):
    sc = pd.DataFrame({
        "Branches": scale["branches"], "Orders": scale["orders"], "Order lines": scale["order_lines"],
        "Full analysis (s)": scale["total_seconds"].round(1),
        "Forecast WAPE": scale["wape"], "Best rule WAPE": scale["best_rule_wape"],
    })
    s1, s2 = st.columns([3, 2])
    with s1:
        ui.table(sc, column_config={"Orders": ui.money_col("Orders"), "Order lines": ui.money_col("Order lines"),
                                    "Forecast WAPE": st.column_config.NumberColumn(format="percent"),
                                    "Best rule WAPE": st.column_config.NumberColumn(format="percent")})
        st.caption(f"Measured with `python scripts/scale_test.py`: all steps the app runs on its first start, one year "
                   f"of data per size. {scale['order_lines'].iloc[-1] / scale['order_lines'].iloc[0]:.1f}x more data took "
                   f"{scale['total_seconds'].iloc[-1] / scale['total_seconds'].iloc[0]:.1f}x more time. The AI fact sheet "
                   f"grows only from ~{scale['ai_context_tokens'].iloc[0]:,} to ~{scale['ai_context_tokens'].iloc[-1]:,} "
                   f"tokens. After the first run every step is cached, so pages open in about a second.")
    with s2:
        fig = go.Figure(go.Scatter(x=scale["branches"], y=scale["total_seconds"], mode="lines+markers",
                                   customdata=scale["order_lines"], marker=dict(size=9, color=ui.SERIES[0]),
                                   line=dict(color=ui.SERIES[0], width=2),
                                   hovertemplate="%{x} branches · %{customdata:,.0f} order lines<br>%{y:.1f} s<extra></extra>"))
        fig.update_xaxes(title="branches (one year of data each)", tickvals=list(scale["branches"]))
        fig.update_yaxes(title="seconds", rangemode="tozero")
        fig.update_layout(title="Time for the full analysis")
        ui.show(ui.style(fig, 300, legend=False))
else:
    st.info("Run `python scripts/scale_test.py` to measure 2, 5 and 10 branches.")

# ---- real-world validation -----------------------------------------------------------------
st.subheader("6 · Next step: validation with a real restaurant")
st.markdown(
    "- **Pilot, 6 weeks:** one real restaurant chain, POS export (iiko / R-Keeper / Poster). Weeks 1–2 baseline, "
    "weeks 3–6 one branch follows the platform, the other works as usual (A/B).\n"
    "- **KPIs and targets:** forecast error (WAPE) ≤ 15% and better than the manager's rule; perishable waste −15%; "
    "staff-hours −5% with no more understaffed peak hours; margin from price and upsell actions measured per week.\n"
    "- **Manager feedback:** every recommendation rated 👍 / 👎 in the app (target ≥ 70% useful), a weekly "
    "15-minute interview and a short survey (usefulness, ease of use, trust) at the end.\n"
    "- **Scale:** after the pilot, 3–5 restaurants; heavy steps move to a nightly job with results in a database.")
st.page_link("https://github.com/shaxnazarovrasulbek-glitch/horeca-decision-support/blob/main/docs/validation_plan.md",
             label="Full validation plan (GitHub)", icon=":material/open_in_new:")

# ---- export --------------------------------------------------------------------------------
st.subheader("Export for the report")
md = ["# Evaluation results", "", f"Data: {ds.source}, {ds.start:%Y-%m-%d} – {ds.end:%Y-%m-%d}", "",
      "## Business impact (per month)", ui.to_markdown(impact.assign(monthly_gain=impact["monthly_gain"].round(0))), "",
      "## Forecast accuracy (WAPE)", ui.to_markdown(fc_tab.round(4)), "",
      "## Revenue WAPE by day type", ui.to_markdown(bd.round(4))]
if len(fb_summary):
    md += ["", "## Manager feedback (latest rating per recommendation)", ui.to_markdown(fb_summary.round(3))]
if scale is not None and len(scale):
    md += ["", "## Scale test", ui.to_markdown(scale[["branches", "orders", "order_lines", "total_seconds", "wape"]].round(3))]
st.download_button("Download results (Markdown)", "\n".join(md), file_name="evaluation_results.md", icon=":material/download:")

ui.footer()
