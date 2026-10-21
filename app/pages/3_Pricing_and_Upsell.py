"""Revenue levers: price changes, upsell scripts and combos."""
import plotly.graph_objects as go
import streamlit as st

import ui

ui.page("Pricing & upsell", ":material/sell:")
ds = ui.get_dataset()
branch, period = ui.sidebar(ds)

st.title("Pricing & upsell")
st.caption("Where can we earn more per guest without losing guests?")

acc = st.session_state.get("upsell_acceptance", 0.10)
c = ui.commercial_bundle(ds.dataset_id, branch, period, acc, ds)
tab_p, tab_u, tab_e = st.tabs(["Price recommendations", "Upsell & combos", "Price elasticity"])

with tab_p:
    p = c["prices"]
    act = p[p["recommended_price"] != p["current_price"]]
    tests = p[p["confidence"] == "Low"]
    m1, m2, m3 = st.columns(3)
    ui.metric(m1, "Extra margin per month", ui.uzs(act["cm_uplift_month"].sum()), f"{len(act)} price changes",
              note=True, border=True)
    ui.metric(m2, "Expected change in portions sold", f"{(act['exp_qty_change_pct'] * act['qty_month']).sum() / max(act['qty_month'].sum(), 1):+.1%}",
              "on changed items", note=True, border=True)
    ui.metric(m3, "Dishes needing a price test", f"{len(tests)}", "not enough price history", note=True, border=True)
    if len(act):
        a = act.sort_values("cm_uplift_month")
        fig = go.Figure(go.Bar(
            x=a["cm_uplift_month"], y=a["item_name"], orientation="h", marker_color=ui.SERIES[0], marker_line_width=0,
            text=[f"{r.current_price:,.0f} → {r.recommended_price:,.0f}" for r in a.itertuples()], textposition="auto",
            hovertemplate="%{y}<br>+%{x:,.0f} UZS margin / month<extra></extra>"))
        fig.update_layout(title="Monthly margin gain per recommended price change (UZS)")
        ui.show(ui.style(fig, 80 + 34 * len(a), legend=False))
    else:
        st.info("No confident price changes for this selection. Run price tests to learn demand.")
    ui.table(p[["item_name", "category", "current_price", "recommended_price", "change_pct", "elasticity", "confidence",
                "exp_qty_change_pct", "cm_uplift_month", "next_step"]],
             column_config={"item_name": "Dish", "category": "Category",
                            "current_price": ui.money_col("Current price"),
                            "recommended_price": ui.money_col("Recommended"),
                            "change_pct": st.column_config.NumberColumn("Change", format="percent"),
                            "elasticity": st.column_config.NumberColumn("Elasticity", format="%.2f"),
                            "confidence": "Confidence",
                            "exp_qty_change_pct": st.column_config.NumberColumn("Portions change", format="percent"),
                            "cm_uplift_month": ui.money_col("Margin gain / month"),
                            "next_step": st.column_config.TextColumn("Next step", width="large")}, height=420)
    with st.expander("How the recommendation is made"):
        st.markdown(
            "- **Elasticity** = % change in portions per guest when the dish's price rises 1% relative to its menu "
            "section, estimated from past price changes (controls: weekday, temperature, branch, trend).\n"
            "- Candidate moves of −10%, −5%, 0, +5%, +10% are scored with a constant-elasticity demand curve; the move "
            "with the highest **contribution margin** wins, as long as portions sold fall by no more than 8%.\n"
            "- Dishes without enough price history are **not** changed: the platform proposes a 2-week price test.\n"
            "- Roll changes out in one branch first and compare with the other branch (A/B test).")

with tab_u:
    acc_new = st.slider("Share of guests who accept a waiter's suggestion", 0.05, 0.30, acc, 0.01, format="%.2f")
    if abs(acc_new - acc) > 1e-9:
        st.session_state["upsell_acceptance"] = acc_new
        st.rerun()
    u = c["upsell"]
    m1, m2 = st.columns(2)
    ui.metric(m1, "Extra revenue / month (top 5 scripts)", ui.uzs(u.head(5)["extra_revenue_month"].sum()), border=True)
    ui.metric(m2, "Extra margin / month (top 5 scripts)", ui.uzs(u.head(5)["extra_cm_month"].sum()), border=True)
    st.markdown("**Waiter / app suggestion scripts** — based on what guests already buy together")
    ui.table(u[["script", "confidence", "lift", "missed_orders_month", "extra_revenue_month", "extra_cm_month"]],
             column_config={"script": st.column_config.TextColumn("Script", width="large"),
                            "confidence": st.column_config.NumberColumn("Attach rate now", format="percent"),
                            "lift": st.column_config.NumberColumn("Lift", format="%.1f×"),
                            "missed_orders_month": st.column_config.NumberColumn("Missed orders / month", format="localized"),
                            "extra_revenue_month": ui.money_col("Extra revenue / month"),
                            "extra_cm_month": ui.money_col("Extra margin / month")})
    st.markdown("**Combo ideas** — strongest pairs bundled at a 7% discount")
    ui.table(c["combos"], column_config={
        "combo": st.column_config.TextColumn("Combo", width="medium"), "separate_price": ui.money_col("Separately"),
        "combo_price": ui.money_col("Combo price"), "guest_saves": ui.money_col("Guest saves"),
        "combo_margin": ui.money_col("Margin"), "combo_margin_pct": st.column_config.NumberColumn("Margin %", format="percent"),
        "lift": st.column_config.NumberColumn("Lift", format="%.1f×"),
        "orders_together_pct": st.column_config.NumberColumn("Orders with both", format="percent")})
    with st.expander("All association rules (top 40 by lift)"):
        st.caption("Lift > 1 means the two items are bought together more often than chance. "
                   "Attach rate = share of orders with the first item that also contain the second.")
        ui.table(c["rules"].head(40)[["antecedent", "consequent", "orders_with_both", "support", "confidence", "lift"]],
                 column_config={"support": st.column_config.NumberColumn("Support", format="percent"),
                                "confidence": st.column_config.NumberColumn("Attach rate", format="percent"),
                                "lift": st.column_config.NumberColumn("Lift", format="%.2f")})

with tab_e:
    e = c["elasticities"].merge(ds.menu[["item_id", "item_name", "category"]].astype({"item_id": str}),
                                on="item_id", how="left")
    est = e[e["method"].str.startswith("estimated")].sort_values("elasticity")
    st.caption("How strongly demand reacts to price. −1.0 means +10% price → about −10% portions. "
               "Values closer to 0 mean guests barely react (pricing power).")
    if len(est):
        fig = go.Figure(go.Scatter(
            x=est["elasticity"], y=est["item_name"], mode="markers", marker=dict(size=10, color=ui.SERIES[0]),
            error_x=dict(type="data", array=1.96 * est["se"].fillna(0), color=ui.MUTED, thickness=1.5),
            hovertemplate="%{y}: %{x:.2f}<extra></extra>"))
        fig.add_vline(x=-1, line_dash="dot", line_color=ui.MUTED)
        fig.update_layout(title="Estimated elasticities with 95% interval")
        ui.show(ui.style(fig, 80 + 30 * len(est), legend=False))
    ui.table(e[["item_name", "category", "elasticity", "se", "confidence", "method", "days_with_price_change", "n_obs"]],
             column_config={"elasticity": st.column_config.NumberColumn("Elasticity", format="%.2f"),
                            "se": st.column_config.NumberColumn("Std. error", format="%.2f"),
                            "days_with_price_change": st.column_config.NumberColumn("Days with different price"),
                            "n_obs": st.column_config.NumberColumn("Days observed")})

ui.page_feedback("Pricing & upsell", "price recommendations, upsell scripts and combos")

ui.footer()
