"""Menu engineering: which dishes to keep, fix, promote or remove."""
import plotly.graph_objects as go
import streamlit as st

import ui
from horeca_dss.menu_engineering import ACTIONS, SEGMENTS, menu_engineering, segment_summary

ui.page("Menu engineering", ":material/restaurant_menu:")
ds = ui.get_dataset()
branch, period = ui.sidebar(ds)

st.title("Menu engineering")
st.caption("Kasavana & Smith matrix: each dish is compared with the others in its menu section on popularity "
           "(share of portions sold) and contribution margin (price − ingredient cost).")

end = ds.end
s = ui.kpis.filter_sales(ds.sales, end - ui.pd.Timedelta(days=period - 1), end, branch)
whole = st.toggle("Compare across the whole menu instead of within each category", value=False)
me = menu_engineering(s, by_category=not whole)
seg = segment_summary(me)

cols = st.columns(4)
for col, (_, r) in zip(cols, seg.iterrows()):
    with col.container(border=True):
        st.markdown(f"**{r['segment']}s** · {int(r['items'])} dishes")
        st.markdown(f"<span style='font-size:1.9rem;font-weight:600'>{r['cm_share']:.0%}</span> of total margin",
                    unsafe_allow_html=True)

cats = sorted(me["category"].unique())
pick = st.multiselect("Categories", cats, default=cats)
view = me[me["category"].isin(pick)]

fig = go.Figure()
for name in SEGMENTS:
    g = view[view["segment"] == name]
    if g.empty:
        continue
    color, symbol = ui.SEGMENT_STYLE[name]
    size = 10 + 30 * (g["total_cm"] / max(view["total_cm"].max(), 1)) ** 0.5
    keep = 2 if name in ("Star", "Plowhorse") else 3
    label = g["item_name"].where(g["total_cm"].rank(ascending=False) <= keep, "")
    fig.add_trace(go.Scatter(
        x=g["popularity_index"], y=g["margin_index"], mode="markers+text", name=name, text=label,
        textposition="top center", textfont=dict(size=11),
        marker=dict(size=size, color=color, symbol=symbol, line=dict(width=2, color="white"), opacity=0.9),
        customdata=g[["item_name", "category", "qty", "cm", "total_cm", "mix_pct"]].to_numpy(),
        hovertemplate="<b>%{customdata[0]}</b> (%{customdata[1]})<br>Sold: %{customdata[2]:,.0f} portions"
                      " (%{customdata[5]:.1%} of section)<br>Margin per portion: %{customdata[3]:,.0f} UZS"
                      "<br>Total margin: %{customdata[4]:,.0f} UZS<extra>" + name + "</extra>"))
fig.add_hline(y=1, line_dash="dot", line_color=ui.MUTED)
fig.add_vline(x=1, line_dash="dot", line_color=ui.MUTED)
xmax = max(view["popularity_index"].max() * 1.1, 2.2) if len(view) else 2.2
ymax = max(view["margin_index"].max() * 1.08, 1.5) if len(view) else 1.5
ymin = min(view["margin_index"].min() * 0.92, 0.6) if len(view) else 0.6
for x, y, txt in [(xmax * 0.97, ymax * 0.99, "STARS"), (xmax * 0.97, ymin, "PLOWHORSES"),
                  (0.05, ymax * 0.99, "PUZZLES"), (0.05, ymin, "DOGS")]:
    fig.add_annotation(x=x, y=y, text=txt, showarrow=False, font=dict(size=11, color=ui.MUTED),
                       xanchor="right" if x > 1 else "left")
fig.update_xaxes(title="Popularity vs section threshold (1 = threshold)", range=[0, xmax])
fig.update_yaxes(title="Margin per portion vs section average (1 = average)", range=[ymin * 0.95, ymax * 1.03])
fig.update_layout(title="Popularity × profitability (bubble size = total margin earned)")
ui.show(ui.style(fig, 520))

with st.expander("What each segment means and what to do", expanded=False):
    for name in SEGMENTS:
        st.markdown(f"**{name}** — {ACTIONS[name]}")

st.markdown("**All dishes**")
t = view[["item_name", "category", "segment", "qty", "mix_pct", "price", "unit_cost", "cm", "total_cm",
          "food_cost_pct", "action"]]
ui.table(t, column_config={
    "item_name": "Dish", "category": "Category", "segment": "Segment", "qty": st.column_config.NumberColumn("Portions", format="localized"),
    "mix_pct": st.column_config.NumberColumn("Share of section", format="percent"),
    "price": ui.money_col("Avg price"), "unit_cost": ui.money_col("Cost"), "cm": ui.money_col("Margin / portion"),
    "total_cm": ui.money_col("Total margin"), "food_cost_pct": st.column_config.NumberColumn("Food cost", format="percent"),
    "action": st.column_config.TextColumn("Recommended action", width="large")}, height=460)

ui.footer()
