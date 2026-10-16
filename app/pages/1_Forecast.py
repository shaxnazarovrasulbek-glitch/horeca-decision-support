"""Demand forecast: revenue / guests for the next 7-14 days, by day and hour."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui

ui.page("Forecast", ":material/insights:")
ds = ui.get_dataset()
branch, _ = ui.sidebar(ds, show_period=False)

st.title("Demand forecast")
st.caption("Gradient-boosting model with weekday, holiday, Ramadan, promo, weather and trend features. "
           "Retrained on the latest data every time the data changes.")

c1, c2, c3 = st.columns([2, 2, 3])
target = c1.radio("Forecast", ["revenue", "covers"], format_func=lambda t: "Revenue" if t == "revenue" else "Guests",
                  horizontal=True)
horizon = c2.radio("Horizon", [7, 14], format_func=lambda h: f"{h} days", horizontal=True, index=1)
promo = c3.toggle("What-if: run a marketing campaign during the forecast period", value=False)

fcb = ui.forecast_bundle(ds.dataset_id, 14, promo, ds)
bt = ui.backtest(ds.dataset_id, target, ds)
lo, hi = bt["band"]
fc = fcb[target].copy()
fc = fc[fc["date"] <= fc["date"].min() + pd.Timedelta(days=horizon - 1)]
daily = fcb["daily"]
hist = daily[daily["date"] > ds.end - pd.Timedelta(days=56)]
if branch != ui.ALL:
    fc, hist = fc[fc["branch"] == branch], hist[hist["branch"] == branch]
unit = "UZS" if target == "revenue" else "guests"
fmt = ui.uzs if target == "revenue" else (lambda x: f"{ui.num(x)} guests")

last_h = hist[hist["date"] > ds.end - pd.Timedelta(days=horizon)][target].sum()
tot = fc["forecast"].sum()
by_day = fc.groupby("date")["forecast"].sum()
cal = ds.calendar.assign(date=pd.to_datetime(ds.calendar["date"]))
m1, m2, m3, m4 = st.columns(4)
ui.metric(m1, f"Next {horizon} days", fmt(tot), f"{tot / last_h - 1:+.1%} vs last {horizon} days" if last_h else None, border=True)
ui.metric(m2, "Busiest day", f"{by_day.idxmax():%a %d %b}", fmt(by_day.max()), note=True, border=True)
ui.metric(m3, "Quietest day", f"{by_day.idxmin():%a %d %b}", fmt(by_day.min()), note=True, border=True)
ui.metric(m4, "Typical daily error", f"{bt['metrics'].iloc[0]['WAPE']:.1%}",
          f"{bt['improvement_vs_best_baseline']:+.0%} vs best rule of thumb", delta_color="normal", border=True)

colors = ui.branch_colors(ds.branches)
fig = go.Figure()
for b in sorted(fc["branch"].unique()):
    col = colors[b]
    h = hist[hist["branch"] == b]
    f = fc[fc["branch"] == b]
    rgb = tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))
    fig.add_trace(go.Scatter(x=list(f["date"]) + list(f["date"][::-1]),
                             y=list(f["forecast"] * hi) + list((f["forecast"] * lo)[::-1]),
                             fill="toself", fillcolor=f"rgba({rgb[0]},{rgb[1]},{rgb[2]},0.15)", line=dict(width=0),
                             hoverinfo="skip", name=f"{b} 80% range", showlegend=False))
    fig.add_trace(go.Scatter(x=h["date"], y=h[target], name=f"{b} actual", mode="lines",
                             line=dict(width=2, color=col),
                             hovertemplate="%{x|%a %d %b}<br>%{y:,.0f} " + unit + "<extra>" + b + " actual</extra>"))
    fig.add_trace(go.Scatter(x=f["date"], y=f["forecast"], name=f"{b} forecast", mode="lines+markers",
                             line=dict(width=2, color=col, dash="dash"), marker=dict(size=8, line=dict(width=2, color="white")),
                             hovertemplate="%{x|%a %d %b}<br>%{y:,.0f} " + unit + "<extra>" + b + " forecast</extra>"))
for r in cal[(cal["date"] > ds.end) & (cal["date"] <= fc["date"].max()) & (cal["holiday"] != "")].itertuples():
    fig.add_vline(x=r.date, line_dash="dot", line_color=ui.MUTED)
    fig.add_annotation(x=r.date, y=1, yref="paper", text=r.holiday, showarrow=False, font=dict(size=11, color=ui.MUTED))
fig.add_vline(x=ds.end + pd.Timedelta(hours=12), line_color=ui.MUTED, line_width=1)
fig.update_layout(title=f"{'Revenue (UZS)' if target == 'revenue' else 'Guests'} — last 8 weeks and forecast "
                        f"(shaded: 80% range from back-testing)")
ui.show(ui.style(fig, 420, hover="x unified"))

left, right = st.columns([3, 2])
with left:
    st.markdown("**Daily forecast**")
    t = fc.assign(low=fc["forecast"] * lo, high=fc["forecast"] * hi)
    t = t.merge(cal[["date", "holiday", "temp_c"]], on="date", how="left").fillna({"holiday": ""})
    t["day"] = t["date"].dt.strftime("%a %d %b")
    ui.table(t[["day", "branch", "forecast", "low", "high", "holiday", "temp_c"]],
             column_config={"forecast": ui.money_col("Forecast", "localized"), "low": ui.money_col("Low", "localized"),
                            "high": ui.money_col("High", "localized"),
                            "temp_c": st.column_config.NumberColumn("Temp °C (avg)", format="%.0f")}, height=300)
with right:
    st.markdown("**Guests by hour** (for staff planning)")
    days = sorted(fcb["covers"]["date"].unique())
    pick = st.selectbox("Day", days, format_func=lambda d: pd.Timestamp(d).strftime("%a %d %b"))
    prof = ui.forecasting.hourly_profile(ds.sales)
    cf = fcb["covers"][fcb["covers"]["date"] == pick]
    hr = ui.forecasting.split_hourly(cf, prof)
    if branch != ui.ALL:
        hr = hr[hr["branch"] == branch]
    fig = go.Figure()
    for b, g in hr.groupby("branch"):
        fig.add_trace(go.Bar(x=g["hour"], y=g["value"], name=b, marker_color=colors[b], marker_line_width=0,
                             hovertemplate="%{x}:00 — %{y:.0f} guests<extra>" + b + "</extra>"))
    fig.update_layout(barmode="group")
    fig.update_xaxes(tickmode="array", tickvals=list(range(10, 24, 2)), ticktext=[f"{h}:00" for h in range(10, 24, 2)])
    ui.show(ui.style(fig, 300))

st.subheader("How accurate is it?")
st.caption(f"Rolling-origin back-test: the model was retrained {len(bt['origins'])} times on data up to an earlier date "
           f"and asked to forecast the next {bt['horizon']} days, then compared with what really happened. "
           "WAPE = total absolute error / total actual (lower is better).")
a1, a2 = st.columns([2, 3])
with a1:
    m = bt["metrics"].copy()
    ui.table(m, column_config={"WAPE": st.column_config.NumberColumn("WAPE", format="percent"),
                               "MAPE": st.column_config.NumberColumn("MAPE", format="percent"),
                               "bias": st.column_config.NumberColumn("Bias", format="percent")})
    st.markdown("**Where the model wins** — WAPE by type of day")
    bd = bt["by_day_type"]
    ui.table(bd, column_config={c: st.column_config.NumberColumn(c, format="percent") for c in bd.columns[2:]}
             | {"n": st.column_config.NumberColumn("Days")})
with a2:
    p = bt["predictions"]
    rows = []
    for h, g in p.groupby("h"):
        rows.append({"h": h, "AI model": ui.forecasting.wape(g["actual"], g["forecast"]),
                     "Same weekday last week": ui.forecasting.wape(g["actual"], g["snaive"]),
                     "Avg of last 4 same weekdays": ui.forecasting.wape(g["actual"], g["ma4"])})
    e = pd.DataFrame(rows)
    fig = go.Figure()
    for i, col in enumerate(["AI model", "Same weekday last week", "Avg of last 4 same weekdays"]):
        fig.add_trace(go.Scatter(x=e["h"], y=e[col], name=col, mode="lines+markers",
                                 line=dict(width=2, color=ui.SERIES[i]), marker=dict(size=8),
                                 hovertemplate="day %{x}: %{y:.1%}<extra>" + col + "</extra>"))
    fig.update_layout(title="Error by days ahead")
    fig.update_yaxes(tickformat=".0%")
    fig.update_xaxes(title="days ahead")
    ui.show(ui.style(fig, 300, hover="x unified"))

ui.footer()
