"""Overview: KPIs, trends, alerts and this week's top recommendations."""
import plotly.graph_objects as go
import streamlit as st

import ui

ui.page("Overview", ":material/dashboard:")
ds = ui.get_dataset()
branch, period = ui.sidebar(ds)

st.title("HoReCa Decision-Support Platform")
st.caption("AI-enabled decision support for revenue maximisation and operational efficiency "
           "in restaurants · demo chain with two branches in Tashkent")

k = ui.kpi_bundle(ds.dataset_id, branch, period, ds)
cmp_ = k["compare"]
cur, d = cmp_["current"], cmp_["delta"]
start, end = cmp_["period"]
st.subheader(f"Last {period} days · {start:%d %b} – {end:%d %b %Y}")
st.caption(f"{branch} · change vs the previous {period} days")

cols = st.columns(6)
tiles = [
    ("Revenue, UZS", ui.short(cur["revenue"]), d["revenue"], "normal"),
    ("Orders", ui.num(cur["orders"]), d["orders"], "normal"),
    ("Guests", ui.num(cur["covers"]), d["covers"], "normal"),
    ("Avg check, UZS", ui.short(cur["avg_check"]), d["avg_check"], "normal"),
    ("Food cost", f"{cur['food_cost_pct']:.1%}", d["food_cost_pct"], "inverse"),
    ("Gross margin, UZS", ui.short(cur["gross_margin"]), d["gross_margin"], "normal"),
]
for col, (label, value, delta, color) in zip(cols, tiles):
    ui.metric(col, label, value, None if delta is None else f"{delta:+.1%}", delta_color=color, border=True)

left, right = st.columns([3, 2])
with left:
    w = k["weekly"]
    colors = ui.branch_colors(ds.branches)
    fig = go.Figure()
    for b, g in w.groupby("branch"):
        fig.add_trace(go.Scatter(x=g["week"], y=g["revenue"], name=b, mode="lines",
                                 line=dict(width=2, color=colors.get(b, ui.SERIES[0])),
                                 hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} UZS<extra>" + b + "</extra>"))
    fig.update_layout(title="Weekly revenue by branch (UZS)")
    ui.show(ui.style(fig, 340, hover="x unified"))
with right:
    s = ui.kpis.filter_sales(ds.sales, start, end, branch)
    hm = ui.kpis.hour_dow_heatmap(s)
    fig = go.Figure(go.Heatmap(z=hm.values, x=[f"{h}:00" for h in hm.columns], y=list(hm.index),
                               colorscale=[[i / (len(ui.BLUES) - 1), c] for i, c in enumerate(ui.BLUES)],
                               hovertemplate="%{y} %{x}<br>%{z:,.0f} UZS per day<extra></extra>",
                               colorbar=dict(title="UZS", thickness=10), xgap=2, ygap=2))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(tickangle=0, dtick=2)
    fig.update_layout(title="When revenue happens (avg per day)")
    ui.show(ui.style(fig, 340, legend=False))

st.subheader("Alerts")
an = k["anomalies"]
an = an[(an["date"] >= start) & (an["date"] <= end)]
if branch != ui.ALL:
    an = an[an["branch"] == branch]
drops = an[an["type"] == "drop"]
spikes = an[an["type"] == "spike"]
if drops.empty:
    st.success("No unusual revenue drops in this period.", icon=":material/check_circle:")
for _, a in drops.head(4).iterrows():
    st.error(f"**{a['date']:%a %d %b} · {a['branch']}: revenue {a['deviation']:+.0%}** "
             f"({ui.uzs(a['revenue'])} vs a normal {a['weekday']} ~{ui.uzs(a['expected'])}) — {a['explanation']}",
             icon=":material/trending_down:")
if len(spikes):
    with st.expander(f"{len(spikes)} days with unusually high revenue"):
        ui.table(spikes.assign(deviation=spikes["deviation"].map(lambda x: f"{x:+.0%}"))[
            ["date", "weekday", "branch", "deviation", "explanation"]],
            column_config={"date": st.column_config.DateColumn("Date", format="ddd DD MMM")})

st.subheader("This week's recommendations")
c = ui.commercial_bundle(ds.dataset_id, branch, period, st.session_state.get("upsell_acceptance", 0.10), ds)
fc = ui.forecast_bundle(ds.dataset_id, 14, False, ds)
ops = ui.operations_bundle(ds.dataset_id, 14, ui.staff_tuple(), 0.10, 7, ds)
rev7 = fc["revenue"][fc["revenue"]["date"] <= fc["revenue"]["date"].min() + ui.pd.Timedelta(days=6)]
if branch != ui.ALL:
    rev7 = rev7[rev7["branch"] == branch]
r1, r2, r3, r4 = st.columns(4)
with r1.container(border=True):
    st.markdown("**:material/insights: Next 7 days**")
    st.markdown(f"Expected revenue **{ui.uzs(rev7['forecast'].sum())}**")
    st.page_link("pages/1_Forecast.py", label="Open forecast", icon=":material/arrow_forward:")
    ui.feedback("Forecast", "next 7 days", f"Expected revenue {ui.uzs(rev7['forecast'].sum())}", "ov_fc")
with r2.container(border=True):
    st.markdown("**:material/add_shopping_cart: Upsell**")
    if len(c["upsell"]):
        u = c["upsell"].iloc[0]
        st.markdown(f"{u['script']} — **+{ui.uzs(u['extra_cm_month'])}** margin / month")
    st.page_link("pages/3_Pricing_and_Upsell.py", label="All upsell ideas", icon=":material/arrow_forward:")
    if len(c["upsell"]):
        ui.feedback("Upsell", str(u["script"])[:60], str(u["script"]), "ov_up")
with r3.container(border=True):
    st.markdown("**:material/sell: Price**")
    pa = c["prices"][c["prices"]["recommended_price"] != c["prices"]["current_price"]]
    if len(pa):
        p = pa.iloc[0]
        st.markdown(f"{p['item_name']}: {ui.num(p['current_price'])} → **{ui.num(p['recommended_price'])} UZS**")
    else:
        st.markdown("No confident price changes.")
    st.page_link("pages/3_Pricing_and_Upsell.py", label="Pricing", icon=":material/arrow_forward:")
    if len(pa):
        ui.feedback("Pricing", str(p["item_name"]),
                    f"{p['item_name']}: {ui.num(p['current_price'])} -> {ui.num(p['recommended_price'])} UZS", "ov_pr")
with r4.container(border=True):
    st.markdown("**:material/groups: Staffing**")
    comp = ops["staff_comparison"]
    if branch != ui.ALL:
        comp = comp[comp["branch"] == branch]
    st.markdown(f"Demand-based shifts save **{int(comp['hours_saved'].sum())} staff-hours** next week")
    st.page_link("pages/4_Operations.py", label="Operations", icon=":material/arrow_forward:")
    ui.feedback("Staffing", "next week", f"Demand-based shifts save {int(comp['hours_saved'].sum())} staff-hours", "ov_st")

with st.expander("Revenue by category"):
    cm = k["category_mix"]
    fig = go.Figure(go.Bar(x=cm["revenue"], y=cm["category"], orientation="h", marker_color=ui.SERIES[0],
                           marker_line_width=0, hovertemplate="%{y}: %{x:,.0f} UZS<extra></extra>",
                           text=[f"{s:.0%}" for s in cm["share"]], textposition="outside"))
    fig.update_yaxes(autorange="reversed")
    ui.show(ui.style(fig, 300, legend=False))

ui.footer()
