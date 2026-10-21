"""Shared Streamlit helpers: data loading, caching, sidebar, formatting, chart style."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

try:  # optional .env support
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover
    pass

from horeca_dss import analysis, assistant, forecasting, kpis, operations  # noqa: E402
from horeca_dss import feedback as fb  # noqa: E402
from horeca_dss import precompute  # noqa: E402
from horeca_dss.data.loader import Dataset, load_csv, load_generated  # noqa: E402

APP_NAME = "HoReCa Decision-Support Platform"
ALL = kpis.ALL

# Validated categorical palette (fixed order) + single-hue sequential ramp + status colours
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b"}
MUTED = "#8a8985"
SEGMENT_STYLE = {"Star": (SERIES[0], "star"), "Plowhorse": (SERIES[1], "square"),
                 "Puzzle": (SERIES[2], "diamond"), "Dog": (SERIES[3], "x")}


# ---------------------------------------------------------------------------------------
# page + data
# ---------------------------------------------------------------------------------------

def page(title: str, icon: str = ":material/restaurant:", layout: str = "wide") -> None:
    st.set_page_config(page_title=f"{title} | HoReCa DSS", page_icon=icon, layout=layout)


@st.cache_resource(show_spinner="Generating one year of restaurant sales...")
def _generated(seed: int, days: int, end: str) -> Dataset:
    return load_generated(seed=seed, end=end, days=days)


EVAL_END = "2026-10-15"   # the evaluation date used in the README and the internship report


def data_end() -> str:
    """Last day of the generated demo data. Default: the evaluation date, so the app shows the same numbers
    as the report. Set HORECA_DATA_END=yesterday (or pick it on the Data page) for a rolling window."""
    choice = st.session_state.get("data_end") or os.environ.get("HORECA_DATA_END", EVAL_END)
    if str(choice).lower() == "yesterday":
        return (pd.Timestamp.today().normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return str(choice)


def get_dataset() -> Dataset:
    ss = st.session_state
    if ss.get("uploaded_ds") is not None and ss.get("data_mode") == "upload":
        return ss["uploaded_ds"]
    seed = ss.get("seed", 42)
    days = ss.get("days", 365)
    end = data_end()
    ds = _generated(seed, days, end)
    ss["_ds_id"] = ds.dataset_id
    return ds


def set_upload(file) -> Dataset:
    ds = load_csv(file.getvalue(), file.name)
    st.session_state["uploaded_ds"] = ds
    st.session_state["data_mode"] = "upload"
    return ds


def _secrets_to_env() -> None:
    """Streamlit Community Cloud: make a GEMINI_API_KEY added under Settings -> Secrets visible
    without a reboot (reading st.secrets loads the file and copies root keys to os.environ)."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return
    try:
        for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL"):
            if k in st.secrets and not os.environ.get(k):
                os.environ[k] = str(st.secrets[k])
    except Exception:  # no secrets file (local run without .streamlit/secrets.toml)
        pass


def sidebar(ds: Dataset, show_branch: bool = True, show_period: bool = True) -> tuple[str, int]:
    _secrets_to_env()
    with st.sidebar:
        st.markdown(f"**{APP_NAME}**")
        st.caption(f"Data: {ds.source} · {ds.start:%d %b %Y} – {ds.end:%d %b %Y}")
        branch, period = ALL, st.session_state.get("period_days", 28)
        if show_branch:
            options = [ALL] + ds.branches
            current = st.session_state.get("branch", ALL)
            branch = st.selectbox("Branch", options, index=options.index(current) if current in options else 0)
            st.session_state["branch"] = branch
        if show_period:
            choices = [7, 14, 28, 56, 91]
            period = st.select_slider("Analysis period (days)", choices, value=period if period in choices else 28)
            st.session_state["period_days"] = period
        engine = "Gemini" if assistant.get_api_key() or st.session_state.get("session_api_key") else "offline rules"
        st.caption(f"AI assistant engine: {engine}")
        roles = ["Branch manager", "Operations manager", "Owner / director", "Mentor / reviewer", "Other"]
        st.selectbox("Your role (saved with your 👍/👎 feedback)", roles, key="fb_role")
    return branch, period


# ---------------------------------------------------------------------------------------
# cached analytics (keyed by dataset_id; the dataset object itself is not hashed)
# ---------------------------------------------------------------------------------------

def settings(period: int = 28) -> analysis.Settings:
    s = analysis.Settings(period_days=period)
    s.staff = operations.StaffStandards(**st.session_state.get("staff_standards", {}))
    s.upsell_acceptance = st.session_state.get("upsell_acceptance", 0.10)
    return s


@st.cache_data(show_spinner="Calculating KPIs...")
def kpi_bundle(dataset_id: str, branch: str, period: int, _ds: Dataset) -> dict:
    return analysis.kpi_bundle(_ds, analysis.Settings(period_days=period), branch)


@st.cache_data(show_spinner="Analysing menu, prices and baskets...")
def commercial_bundle(dataset_id: str, branch: str, period: int, acceptance: float, _ds: Dataset) -> dict:
    s = analysis.Settings(period_days=period, upsell_acceptance=acceptance)
    return analysis.commercial_bundle(_ds, s, branch)


@st.cache_data(show_spinner="Training the forecast model...")
def forecast_bundle(dataset_id: str, horizon: int, promo: bool, _ds: Dataset) -> dict:
    return analysis.forecast_bundle(_ds, horizon, promo)


@st.cache_data(show_spinner="Building staffing and purchase plans...")
def operations_bundle(dataset_id: str, horizon: int, staff: tuple, safety: float, days: int, _ds: Dataset) -> dict:
    fc = forecast_bundle(dataset_id, horizon, False, _ds)
    s = analysis.Settings(safety_stock=safety)
    s.staff = operations.StaffStandards(*staff)
    return analysis.operations_bundle(_ds, fc["covers"], s, days)


@st.cache_data(show_spinner="Back-testing the forecast (8 rolling origins)...")
def backtest(dataset_id: str, target: str, _ds: Dataset) -> dict:
    pre = precompute.load(f"backtest_{target}", dataset_id)   # default demo data: stored result
    return pre if pre is not None else forecasting.backtest(_ds.sales, _ds.calendar, target)


@st.cache_data(show_spinner="Simulating 4 weeks of ingredient ordering...")
def waste_backtest(dataset_id: str, _ds: Dataset) -> dict:
    pre = precompute.load("waste_backtest", dataset_id)
    return pre if pre is not None else operations.waste_backtest(_ds.sales, _ds.calendar, _ds.recipes, _ds.ingredients)


def staff_tuple() -> tuple:
    s = operations.StaffStandards(**st.session_state.get("staff_standards", {}))
    return (s.covers_per_waiter_hour, s.covers_per_cook_hour, s.min_waiters, s.min_cooks, s.hourly_wage)


def facts(ds: Dataset, with_eval: bool = True) -> dict:
    period = st.session_state.get("period_days", 28)
    k = kpi_bundle(ds.dataset_id, ALL, period, ds)
    c = commercial_bundle(ds.dataset_id, ALL, period, st.session_state.get("upsell_acceptance", 0.10), ds)
    fc = forecast_bundle(ds.dataset_id, 14, False, ds)
    ops = operations_bundle(ds.dataset_id, 14, staff_tuple(), 0.10, 7, ds)
    bt = backtest(ds.dataset_id, "revenue", ds) if with_eval else None
    wb = waste_backtest(ds.dataset_id, ds) if (with_eval and ds.recipes is not None) else None
    return assistant.build_facts(ds, k, c, fc, ops, bt, wb)


# ---------------------------------------------------------------------------------------
# formatting + charts
# ---------------------------------------------------------------------------------------

def uzs(x: float) -> str:
    return assistant.fmt_uzs(x)


def metric(col, label: str, value, delta=None, delta_color: str = "normal", note: bool = False, **kw):
    """st.metric with a border; `note=True` shows the delta as a neutral note (no arrow)."""
    kw.setdefault("border", True)
    if note:
        delta_color = "off"
        kw["delta_arrow"] = "off"
    try:
        return col.metric(label, value, delta, delta_color=delta_color, **kw)
    except TypeError:  # older Streamlit without delta_arrow / border
        kw.pop("delta_arrow", None)
        kw.pop("border", None)
        return col.metric(label, value, delta, delta_color=delta_color, **kw)


def short(x: float) -> str:
    """Compact number for KPI tiles: 1.45 bn, 794 M, 188 k."""
    x = float(x)
    for div, suf in ((1e9, " bn"), (1e6, " M"), (1e3, " k")):
        if abs(x) >= div:
            v = x / div
            return f"{v:.2f}{suf}" if abs(v) < 10 else f"{v:.1f}{suf}" if abs(v) < 100 else f"{v:.0f}{suf}"
    return f"{x:.0f}"


def num(x: float) -> str:
    return f"{x:,.0f}".replace(",", "\u00a0")


def pct(x, signed: bool = True) -> str:
    return assistant.pct(x, signed)


def branch_colors(branches: list[str]) -> dict[str, str]:
    return {b: SERIES[i % len(SERIES)] for i, b in enumerate(sorted(branches))}


def style(fig: go.Figure, height: int = 360, hover: str = "closest", legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=56 if legend else 40, b=8), hovermode=hover,
        title=dict(x=0, xanchor="left", y=0.98, yanchor="top", font=dict(size=15)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, title=None) if legend else None,
        showlegend=legend, font=dict(size=13), bargap=0.25,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, ticks="outside", ticklen=4)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.18)", zeroline=False)
    return fig


def show(fig: go.Figure) -> None:
    try:
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    except TypeError:  # older Streamlit
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def table(df: pd.DataFrame, **kw) -> None:
    df = df.copy()
    for c in df.columns:  # money-sized floats are shown without decimals
        if pd.api.types.is_float_dtype(df[c]) and df[c].abs().median() >= 100:
            df[c] = df[c].round(0)
    try:
        st.dataframe(df, width="stretch", hide_index=True, **kw)
    except TypeError:  # older Streamlit
        st.dataframe(df, use_container_width=True, hide_index=True, **kw)


def money_col(label: str, fmt: str = "localized"):
    return st.column_config.NumberColumn(label, format=fmt)


def to_markdown(df: pd.DataFrame) -> str:
    """Small Markdown table writer (avoids the optional `tabulate` dependency)."""
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(f"{v:.4g}" if isinstance(v, float) else str(v) for v in row) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------
# manager feedback ("Was this useful?") - every click is one row in data/feedback_log.csv
# ---------------------------------------------------------------------------------------

def _fb_context() -> dict:
    ss = st.session_state
    return {"role": ss.get("fb_role", ""), "branch": ss.get("branch", ALL), "dataset": ss.get("_ds_id", "")}


def feedback(module: str, item: str, recommendation: str, key: str) -> None:
    """Thumbs up / down plus an optional comment for one recommendation."""
    k = f"fb_{key}"

    def _rate():
        v = st.session_state.get(k)
        if v is not None:
            fb.record(module, item, recommendation, rating=int(v), **_fb_context())
            st.toast("Feedback saved. Thank you!", icon=":material/check_circle:")

    def _comment():
        text = st.session_state.get(f"{k}_c", "").strip()
        if text:
            fb.record(module, item, recommendation, rating=None, comment=text, **_fb_context())
            st.toast("Comment saved. Thank you!", icon=":material/check_circle:")

    a, b = st.columns([2, 3], vertical_alignment="center")
    with a:
        st.feedback("thumbs", key=k, on_change=_rate)
    with b:
        with st.popover("Comment"):
            st.text_input("What would make this more useful?", key=f"{k}_c", on_change=_comment)


def page_feedback(module: str, recommendation: str) -> None:
    with st.container(border=True):
        st.markdown(f"**Was this page useful for your decisions?** "
                    f"Your rating helps us measure usefulness in the pilot.")
        feedback(module, "page", recommendation, key=f"page_{module}")


def footer() -> None:
    st.divider()
    st.caption("Prototype for the ITPU / EPAM Master's internship · Rasulbek Shaxnazarov · "
               "Generated data is synthetic and for demonstration only.")
