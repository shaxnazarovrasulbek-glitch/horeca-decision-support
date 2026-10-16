"""Operations: demand-based staff schedule, purchase list and waste simulation."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from horeca_dss.operations import StaffStandards

ui.page("Operations", ":material/groups:")
ds = ui.get_dataset()
branch, _ = ui.sidebar(ds, show_period=False)

st.title("Operations")
st.caption("Turn the guest forecast into a staff schedule and a purchase list for the next 7 days.")

with st.expander("Service standards (edit to match your restaurant)"):
    cur = StaffStandards(**st.session_state.get("staff_standards", {}))
    c1, c2, c3, c4 = st.columns(4)
    w = c1.number_input("Guests per waiter per hour", 4.0, 40.0, float(cur.covers_per_waiter_hour), 1.0)
    k = c2.number_input("Guests per cook per hour", 4.0, 60.0, float(cur.covers_per_cook_hour), 1.0)
    wage = c3.number_input("Cost per staff-hour (UZS)", 5000.0, 200000.0, float(cur.hourly_wage), 1000.0)
    safety = c4.slider("Safety stock for purchasing", 0.0, 0.30, st.session_state.get("safety", 0.10), 0.01)
    new = {"covers_per_waiter_hour": w, "covers_per_cook_hour": k, "hourly_wage": wage}
    if new != {key: getattr(cur, key) for key in new} or safety != st.session_state.get("safety", 0.10):
        st.session_state["staff_standards"] = {**st.session_state.get("staff_standards", {}), **new}
        st.session_state["safety"] = safety
        st.rerun()

safety = st.session_state.get("safety", 0.10)
ops = ui.operations_bundle(ds.dataset_id, 14, ui.staff_tuple(), safety, 7, ds)
plan = ops["staffing"]
comp = ops["staff_comparison"]
if branch != ui.ALL:
    plan, comp = plan[plan["branch"] == branch], comp[comp["branch"] == branch]

tab_s, tab_p, tab_w = st.tabs(["Staff schedule", "Purchase list", "Waste simulation"])

with tab_s:
    m1, m2, m3, m4 = st.columns(4)
    ui.metric(m1, "Staff-hours planned (7 days)", ui.num(comp["planned_hours"].sum()), border=True)
    ui.metric(m2, "vs fixed schedule", ui.num(comp["fixed_hours"].sum()),
              f"-{ui.num(comp['hours_saved'].sum())} hours", delta_color="inverse", border=True)
    ui.metric(m3, "Labour cost saved", ui.uzs(comp["cost_saved"].sum()), border=True)
    ui.metric(m4, "Understaffed hours avoided", ui.num(comp["understaffed_hours_fixed"].sum()),
              "peaks a fixed schedule misses", note=True, border=True)
    role = st.radio("Role", ["waiters", "cooks"], horizontal=True, format_func=str.capitalize)
    for b, g in plan.groupby("branch"):
        pv = g.pivot_table(index="date", columns="hour", values=role, aggfunc="sum")
        fig = go.Figure(go.Heatmap(
            z=pv.values, x=[f"{h}:00" for h in pv.columns], y=[d.strftime("%a %d %b") for d in pv.index],
            text=pv.values, texttemplate="%{text}", colorscale=[[i / (len(ui.BLUES) - 1), c] for i, c in enumerate(ui.BLUES)],
            hovertemplate="%{y} %{x}<br>%{z} " + role + "<extra>" + b + "</extra>", showscale=False, xgap=2, ygap=2))
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(title=f"{b} — {role} needed per hour")
        ui.show(ui.style(fig, 320, legend=False))

    st.markdown("**Shift blocks** (consecutive hours with the same headcount)")
    rows = []
    for (b, d), g in plan.sort_values("hour").groupby(["branch", "date"]):
        blocks, start, val = [], g["hour"].iloc[0], g[role].iloc[0]
        for h, v in zip(g["hour"].iloc[1:], g[role].iloc[1:]):
            if v != val:
                blocks.append(f"{start}–{h}: {val}")
                start, val = h, v
        blocks.append(f"{start}–{g['hour'].iloc[-1] + 1}: {val}")
        rows.append({"branch": b, "day": d.strftime("%a %d %b"), "guests": round(g["guests"].sum()),
                     f"{role} per block": " · ".join(blocks), "staff-hours": int(g[role].sum())})
    ui.table(pd.DataFrame(rows), column_config={"guests": st.column_config.NumberColumn("Forecast guests")})
    with st.expander("Comparison with a fixed schedule"):
        st.caption("Fixed schedule = the same headcount every opening hour, sized to cover 85% of hours "
                   "(a common practice). It overstaffs quiet hours and still misses the biggest peaks.")
        ui.table(comp, column_config={"cost_saved": ui.money_col("Cost saved (UZS)")})

with tab_p:
    if "purchase" not in ops:
        st.info("Purchasing needs recipes (bill of materials) for the menu items.")
    else:
        pl = ops["purchase"]
        if branch != ui.ALL:
            pl = pl[pl["branch"] == branch]
        m1, m2, m3 = st.columns(3)
        ui.metric(m1, "Purchases next 7 days", ui.uzs(pl["order_cost"].sum()), f"incl. {safety:.0%} safety stock",
                  note=True, border=True)
        per = pl[pl["ordering"].str.startswith("daily")]
        ui.metric(m2, "Perishables (order daily)", ui.uzs(per["order_cost"].sum()),
                  f"{per['order_cost'].sum() / max(pl['order_cost'].sum(), 1):.0%} of purchases", note=True, border=True)
        ui.metric(m3, "Ingredients", f"{pl['ingredient'].nunique()}", border=True)
        top = pl.groupby("ingredient", as_index=False)["order_cost"].sum().sort_values("order_cost").tail(12)
        fig = go.Figure(go.Bar(x=top["order_cost"], y=top["ingredient"], orientation="h", marker_color=ui.SERIES[0],
                               marker_line_width=0, hovertemplate="%{y}: %{x:,.0f} UZS<extra></extra>"))
        fig.update_layout(title="Purchase cost by ingredient, next 7 days (UZS)")
        ui.show(ui.style(fig, 420, legend=False))
        ui.table(pl[["branch", "ingredient", "need", "order_qty", "unit", "unit_cost", "order_cost", "ordering"]],
                 column_config={"need": st.column_config.NumberColumn("Forecast use", format="%.1f"),
                                "order_qty": st.column_config.NumberColumn("Order qty", format="%.1f"),
                                "unit_cost": ui.money_col("Unit cost"), "order_cost": ui.money_col("Cost (UZS)")})
        d = ops["needs"]
        if branch != ui.ALL:
            d = d[d["branch"] == branch]
        with st.expander("Daily need for perishable ingredients"):
            pv = d[d["shelf_life_days"] <= 3].pivot_table(index="ingredient", columns="date", values="need", aggfunc="sum")
            pv.columns = [c.strftime("%a %d") for c in pv.columns]
            st.dataframe(pv.round(1))

with tab_w:
    if ds.recipes is None:
        st.info("Needs recipes.")
    else:
        wb = ui.waste_backtest(ds.dataset_id, ds)
        s = wb["summary"]
        naive = s[s["method"].str.startswith("Naive")].iloc[0]
        ai = s[s["method"].str.startswith("AI")].iloc[0]
        st.caption(f"Simulation of the last {wb['weeks']} weeks: every day each branch orders perishables "
                   f"({', '.join(wb['perishables'])}). Unused perishables spoil (waste); missing quantity is a shortage.")
        m1, m2, m3 = st.columns(3)
        ui.metric(m1, "Perishable waste reduced by", f"{wb['waste_reduction']:.0%}", border=True)
        ui.metric(m2, "Waste cost (AI vs naive)", ui.uzs(ai["waste_cost"]), f"-{ui.uzs(naive['waste_cost'] - ai['waste_cost'])}",
                  delta_color="inverse", border=True)
        ui.metric(m3, "Shortages (AI vs naive)", f"{ai['shortage_pct_of_use']:.1%}", f"{ai['shortage_pct_of_use'] - naive['shortage_pct_of_use']:+.1%} pts",
                  delta_color="inverse", border=True)
        wk = wb["weekly"]
        fig = go.Figure()
        for mname, g in wk.groupby("method", sort=False):
            fig.add_trace(go.Bar(x=g["week_start"].dt.strftime("week of %d %b"), y=g["waste_cost"], name=mname,
                                 marker_color=ui.SERIES[0] if mname.startswith("AI") else ui.SERIES[1],
                                 marker_line_width=0, hovertemplate="%{x}: %{y:,.0f} UZS<extra>" + mname + "</extra>"))
        fig.update_layout(barmode="group", title="Weekly cost of spoiled perishables (UZS)")
        ui.show(ui.style(fig, 340))
        ui.table(s, column_config={c: ui.money_col(c.replace("_", " ").capitalize()) for c in
                                   ["waste_cost", "shortage_cost", "purchased_cost", "used_cost"]} |
                 {"waste_pct_of_purchases": st.column_config.NumberColumn("Waste % of purchases", format="percent"),
                  "shortage_pct_of_use": st.column_config.NumberColumn("Shortage % of use", format="percent")})

ui.footer()
