"""Data: switch between generated demo data and your own POS export."""
import io

import streamlit as st

import ui
from horeca_dss.data.generator import generate_dataset
from horeca_dss.data.loader import OPTIONAL_COLUMNS, REQUIRED_COLUMNS

ui.page("Data", ":material/database:")
ds = ui.get_dataset()
ui.sidebar(ds, show_branch=False, show_period=False)

st.title("Data")
st.caption("The platform works on order lines from a POS system (one row per item in an order).")

mode = st.radio("Data source", ["generated", "upload"], horizontal=True,
                index=0 if st.session_state.get("data_mode", "generated") == "generated" else 1,
                format_func=lambda m: "Generated demo data" if m == "generated" else "Upload my POS export (CSV)")

if mode == "generated":
    st.session_state["data_mode"] = "generated"
    c1, c2, c3 = st.columns([1, 1, 2])
    seed = c1.number_input("Random seed", 1, 9999, st.session_state.get("seed", 42))
    days = c2.select_slider("History (days)", [180, 270, 365, 540], value=st.session_state.get("days", 365))
    if c3.button("Generate", type="primary", icon=":material/autorenew:"):
        st.session_state["seed"], st.session_state["days"] = int(seed), int(days)
        st.session_state["chat"] = []
        st.rerun()
    st.info("Synthetic chain of 2 restaurants in Tashkent (Chilanzar: family district, Yunusabad: business district). "
            "It contains weekly/hourly patterns, Uzbek holidays, Ramadan, weather effects, promo campaigns, price "
            "changes, typical item pairings and two operational incidents — so every module has something real to find.",
            icon=":material/info:")
else:
    st.markdown("**Required columns:** " + ", ".join(f"`{c}`" for c in REQUIRED_COLUMNS))
    st.markdown("**Optional columns:** " + ", ".join(f"`{c}`" for c in OPTIONAL_COLUMNS)
                + " — missing ones are filled with sensible defaults.")
    sample = generate_dataset(days=28, seed=7)["sales"]
    buf = io.StringIO()
    sample.to_csv(buf, index=False)
    st.download_button("Download a template CSV (28 days of sample data)", buf.getvalue(), "pos_export_template.csv",
                       mime="text/csv", icon=":material/download:")
    f = st.file_uploader("POS export (CSV)", type=["csv"])
    if f is not None:
        try:
            new = ui.set_upload(f)
            st.success(f"Loaded {len(new.sales):,} order lines, {new.sales['order_id'].nunique():,} orders, "
                       f"{new.start:%d %b %Y} – {new.end:%d %b %Y}.")
            st.session_state["chat"] = []
            ds = new
        except ValueError as e:
            st.error(str(e))
    elif st.session_state.get("uploaded_ds") is None:
        st.warning("No file uploaded yet — the app keeps using the generated data.")
        st.session_state["data_mode"] = "generated"

ds = ui.get_dataset()
st.subheader("Current dataset")
orders = ds.sales.drop_duplicates("order_id")
q = st.columns(5)
ui.metric(q[0], "Order lines", ui.num(len(ds.sales)), border=True)
ui.metric(q[1], "Orders", ui.num(len(orders)), border=True)
ui.metric(q[2], "Days", ui.num(ds.sales["date"].nunique()), border=True)
ui.metric(q[3], "Branches", len(ds.branches), border=True)
ui.metric(q[4], "Menu items", ds.sales["item_id"].nunique(), border=True)
for n in ds.notes:
    st.caption(f"• {n}")
if ds.incidents is not None and len(ds.incidents):
    with st.expander("Planted incidents (ground truth for testing anomaly detection)"):
        ui.table(ds.incidents[["branch", "start", "end", "description"]])
st.markdown("**Preview**")
ui.table(ds.sales.head(200).drop(columns=["date", "hour", "revenue", "food_cost"]), height=320)
with st.expander("Menu"):
    ui.table(ds.menu, column_config={"price": ui.money_col("Price"), "unit_cost": ui.money_col("Unit cost")})
with st.expander("Calendar (holidays, Ramadan, promo, temperature)"):
    cal = ds.calendar.copy()
    ui.table(cal[(cal["holiday"] != "") | cal["promo"]].tail(60))

ui.footer()
