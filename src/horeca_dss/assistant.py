"""AI assistant: explains the platform's numbers in plain language.

* Facts are computed by the analytics modules (never by the language model).
* Gemini (Google AI Studio API, free tier works) turns them into answers in
  English, Russian or Uzbek.
* If no API key is configured, the quota is exhausted or the network is down,
  a rule-based assistant answers from the same facts, so the demo never breaks.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

import pandas as pd
import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ("gemini-flash-latest", "gemini-2.5-flash-lite")

SYSTEM_PROMPT = """You are "HoReCa Copilot", an AI decision-support analyst for a restaurant chain in
Tashkent, Uzbekistan. You help the manager increase revenue and run operations efficiently.

Rules:
- Use ONLY the facts in the CONTEXT below. Never invent numbers, dates or items.
- Quote concrete numbers (amounts in UZS, percentages, dates, item names) from the context.
- Start with a one-sentence answer, then "Why:" with the evidence, then "What to do:" with
  2-4 concrete, prioritised actions (who does what, by when).
- If the context cannot answer the question, say so and name the data that would be needed.
- Reply in the language of the question (English, Russian or Uzbek). Keep it under 250 words
  unless the user asks for more detail. Use short bullet points.
"""


def fmt_uzs(x: float) -> str:
    x = float(x)
    if abs(x) >= 1e9:
        return f"{x / 1e9:.2f} bn UZS"
    if abs(x) >= 1e6:
        return f"{x / 1e6:.1f} M UZS"
    return f"{x:,.0f} UZS".replace(",", " ")


def pct(x: float | None, signed: bool = True) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    return f"{x:+.1%}" if signed else f"{x:.1%}"


# ---------------------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------------------

def build_facts(ds, kpi: dict, commercial: dict, fc: dict, ops: dict,
                backtest: dict | None = None, waste: dict | None = None) -> dict:
    cmp_ = kpi["compare"]
    cur, prev, delta = cmp_["current"], cmp_["previous"], cmp_["delta"]
    start, end = cmp_["period"]
    by_branch = {}
    from .kpis import compare_periods
    for b in ds.branches:
        c = compare_periods(ds.sales, ds.end, (end - start).days + 1, b)
        by_branch[b] = c
    an = kpi["anomalies"]
    an = an[an["date"] >= ds.end - pd.Timedelta(days=45)] if len(an) else an
    rev_fc, cov_fc = fc["revenue"], fc["covers"]
    first7 = rev_fc["date"] <= rev_fc["date"].min() + pd.Timedelta(days=6)
    daily = fc["daily"]
    last7 = daily[daily["date"] > ds.end - pd.Timedelta(days=7)]
    cal = ds.calendar.assign(date=pd.to_datetime(ds.calendar["date"]))
    me = commercial["menu"]
    prices = commercial["prices"]
    facts = {
        "source": ds.source,
        "data_period": f"{ds.start:%Y-%m-%d} to {ds.end:%Y-%m-%d}",
        "branches": ds.branches,
        "kpi_period": f"{start:%Y-%m-%d} to {end:%Y-%m-%d}",
        "kpi": cur, "kpi_prev": prev, "kpi_delta": delta, "kpi_by_branch": by_branch,
        "anomalies": an.to_dict("records") if len(an) else [],
        "forecast_7d": rev_fc[first7].groupby("branch")["forecast"].sum().to_dict(),
        "forecast_guests_7d": cov_fc[cov_fc["date"] <= cov_fc["date"].min() + pd.Timedelta(days=6)]
        .groupby("branch")["forecast"].sum().to_dict(),
        "last_7d_revenue": last7.groupby("branch")["revenue"].sum().to_dict(),
        "forecast_daily": rev_fc[first7].assign(day=lambda d: d["date"].dt.strftime("%a %d %b"))
        [["day", "branch", "forecast"]].to_dict("records"),
        "upcoming_holidays": [f"{r.date:%a %d %b}: {r.holiday}" for r in
                              cal[(cal["date"] > ds.end) & (cal["holiday"] != "")].itertuples()][:5],
        "segments": {s: me[me["segment"] == s]["item_name"].tolist() for s in ["Star", "Plowhorse", "Puzzle", "Dog"]},
        "menu_table": me[["item_name", "category", "qty", "cm", "segment"]].to_dict("records"),
        "price_actions": prices[prices["recommended_price"] != prices["current_price"]].head(8).to_dict("records"),
        "price_tests": prices[prices["confidence"] == "Low"]["item_name"].head(8).tolist(),
        "upsell": commercial["upsell"].head(6).to_dict("records"),
        "combos": commercial["combos"].head(4).to_dict("records") if len(commercial["combos"]) else [],
    }
    st = ops.get("staffing")
    if st is not None:
        comp = ops["staff_comparison"]
        peaks = st.groupby(["branch", "hour"])["guests"].mean().reset_index()
        facts["staffing"] = {
            "hours_saved_7d": int(comp["hours_saved"].sum()),
            "cost_saved_7d": float(comp["cost_saved"].sum()),
            "understaffed_hours_fixed": int(comp["understaffed_hours_fixed"].sum()),
            "peak_hour": {b: int(g.loc[g["guests"].idxmax(), "hour"]) for b, g in peaks.groupby("branch")},
            "max_waiters": st.groupby("branch")["waiters"].max().to_dict(),
        }
    if ops.get("purchase") is not None:
        p = ops["purchase"]
        facts["purchase_top"] = (p.groupby(["ingredient", "unit"], as_index=False)[["order_qty", "order_cost"]]
                                 .sum().sort_values("order_cost", ascending=False).head(8).to_dict("records"))
    if backtest is not None:
        m = backtest["metrics"]
        facts["accuracy"] = {"model_wape": float(m.iloc[0]["WAPE"]), "best_baseline_wape": float(m.iloc[1:]["WAPE"].min()),
                             "improvement": float(backtest["improvement_vs_best_baseline"])}
    if waste is not None:
        facts["waste_reduction"] = float(waste["waste_reduction"])
    return facts


def context_text(f: dict) -> str:
    k, d = f["kpi"], f["kpi_delta"]
    lines = [
        f"DATA: {f['source']}; {f['data_period']}; branches: {', '.join(f['branches'])}. Currency UZS.",
        f"KPIs {f['kpi_period']} (vs previous period of equal length): revenue {fmt_uzs(k['revenue'])} ({pct(d['revenue'])}), "
        f"orders {k['orders']:,} ({pct(d['orders'])}), guests {k['covers']:,} ({pct(d['covers'])}), "
        f"average check {fmt_uzs(k['avg_check'])} ({pct(d['avg_check'])}), food cost {pct(k['food_cost_pct'], False)}.",
    ]
    for b, c in f["kpi_by_branch"].items():
        lines.append(f"  {b}: revenue {fmt_uzs(c['current']['revenue'])} ({pct(c['delta']['revenue'])}), "
                     f"avg check {fmt_uzs(c['current']['avg_check'])} ({pct(c['delta']['avg_check'])}), "
                     f"guests {c['current']['covers']:,} ({pct(c['delta']['covers'])}).")
    lines.append("ANOMALIES (last 45 days, revenue vs same-weekday median of previous 4 weeks):")
    for a in f["anomalies"][:10]:
        lines.append(f"  {a['date']:%Y-%m-%d} {a['weekday']} {a['branch']}: {a['type']} {pct(a['deviation'])} "
                     f"(revenue {fmt_uzs(a['revenue'])} vs expected {fmt_uzs(a['expected'])}) - {a['explanation']}")
    if not f["anomalies"]:
        lines.append("  none")
    lines.append("FORECAST next 7 days revenue: " + "; ".join(
        f"{b} {fmt_uzs(v)} (last 7 days actual {fmt_uzs(f['last_7d_revenue'].get(b, 0))})" for b, v in f["forecast_7d"].items()))
    lines.append("FORECAST next 7 days guests: " + "; ".join(f"{b} {v:,.0f}" for b, v in f["forecast_guests_7d"].items()))
    lines.append("Daily revenue forecast: " + "; ".join(f"{r['day']} {r['branch']} {fmt_uzs(r['forecast'])}" for r in f["forecast_daily"]))
    if f["upcoming_holidays"]:
        lines.append("Upcoming holidays: " + "; ".join(f["upcoming_holidays"]))
    if "accuracy" in f:
        a = f["accuracy"]
        lines.append(f"Forecast accuracy (backtest WAPE): model {pct(a['model_wape'], False)} vs best manager rule "
                     f"{pct(a['best_baseline_wape'], False)} ({pct(a['improvement'])} relative improvement).")
    lines.append("MENU ENGINEERING (last period, within each category):")
    for s, items in f["segments"].items():
        lines.append(f"  {s}: {', '.join(items) if items else '-'}")
    lines.append("PRICE ACTIONS (confident elasticity estimates): " + ("; ".join(
        f"{p['item_name']} {p['current_price']:,.0f} -> {p['recommended_price']:,.0f} UZS "
        f"(elasticity {p['elasticity']:.2f}, +{fmt_uzs(p['cm_uplift_month'])} margin/month)" for p in f["price_actions"]) or "none"))
    lines.append("Items needing a price test (not enough price history): " + ", ".join(f["price_tests"]))
    lines.append("UPSELL scripts (10% acceptance assumed): " + "; ".join(
        f"{u['script']} (attach rate now {u['confidence']:.0%}, lift {u['lift']:.1f}, +{fmt_uzs(u['extra_cm_month'])} margin/month)"
        for u in f["upsell"]))
    if f["combos"]:
        lines.append("COMBO ideas: " + "; ".join(f"{c['combo']} for {c['combo_price']:,.0f} UZS (margin {c['combo_margin_pct']:.0%})"
                                               for c in f["combos"]))
    if "staffing" in f:
        s = f["staffing"]
        lines.append(f"STAFFING next 7 days: demand-based schedule saves {s['hours_saved_7d']} staff-hours "
                     f"({fmt_uzs(s['cost_saved_7d'])}) vs a fixed schedule and removes {s['understaffed_hours_fixed']} understaffed hours. "
                     f"Peak hour: {s['peak_hour']}. Max waiters needed: {s['max_waiters']}.")
    if "purchase_top" in f:
        lines.append("PURCHASING next 7 days (top cost, incl. safety stock): " + "; ".join(
            f"{p['ingredient']} {p['order_qty']:.0f} {p['unit']} ({fmt_uzs(p['order_cost'])})" for p in f["purchase_top"]))
    if "waste_reduction" in f:
        lines.append(f"Waste backtest: forecast-based ordering cuts perishable waste by {pct(f['waste_reduction'], False)} vs 'last week + 15%'.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------
# Offline (rule-based) answers
# ---------------------------------------------------------------------------------------

INTENTS = [
    ("drop", r"drop|declin|fell|fall|down|why|lower|decreas|упал|сниз|паден|почему|tush|kamay|pasay|nega"),
    ("promote", r"promot|advert|marketing|campaign|weekend|реклам|продвиж|акци|reklama|aksiya"),
    ("price", r"price|pricing|expensive|cheap|цен|стоим|narx"),
    ("staff", r"staff|shift|schedule|waiter|cook|employee|персонал|смен|официант|повар|xodim|smena|ofitsiant"),
    ("purchase", r"buy|purchase|stock|ingredient|order from|supplier|закуп|продукт|склад|xarid|mahsulot|ombor"),
    ("waste", r"waste|spoil|списан|отход|isrof"),
    ("upsell", r"upsell|combo|cross|suggest|bundle|комбо|допрод|sotuv"),
    ("menu", r"menu|dish|item|remove|best sell|popular|меню|блюд|taom"),
    ("forecast", r"forecast|next week|tomorrow|expect|predict|plan|прогноз|завтра|prognoz|ertaga|kelasi"),
]


def detect_intent(q: str) -> str:
    ql = q.lower()
    for name, pattern in INTENTS:
        if re.search(pattern, ql):
            return name
    return "briefing"


def offline_answer(question: str, f: dict) -> str:
    intent = detect_intent(question)
    k, d = f["kpi"], f["kpi_delta"]
    if intent == "drop":
        drops = [a for a in f["anomalies"] if a["type"] == "drop"]
        out = [f"**Revenue {f['kpi_period']}: {fmt_uzs(k['revenue'])} ({pct(d['revenue'])} vs previous period).**", "", "Why:"]
        if drops:
            for a in drops[:3]:
                out.append(f"- {a['date']:%a %d %b} - **{a['branch']}** {pct(a['deviation'])} vs a normal {a['weekday']} "
                           f"({fmt_uzs(a['revenue'])} vs ~{fmt_uzs(a['expected'])}): {a['explanation']}.")
        else:
            out.append("- No unusual drop days in the last 45 days; changes are within normal weekly variation.")
        out += ["", "What to do:",
                "- Confirm the cause with the branch manager (power, kitchen equipment, staff absence) and log it.",
                "- If it was an outage: agree a backup generator / early-warning plan; notify delivery platforms when closing.",
                "- Recover lost guests with a targeted offer to regulars of that branch this week."]
        return "\n".join(out)
    if intent == "promote":
        pz = f["segments"].get("Puzzle", [])
        out = ["**Promote high-margin dishes that guests under-order, and push proven pairings.**", "",
               f"- Puzzles (high margin, low popularity): {', '.join(pz[:6]) or '-'} - move up the menu, add photos, waiter recommendation."]
        for c in f["combos"][:3]:
            out.append(f"- Combo: **{c['combo']}** for {c['combo_price']:,.0f} UZS (guest saves {c['guest_saves']:,.0f}; margin {c['combo_margin_pct']:.0%}).")
        for u in f["upsell"][:2]:
            out.append(f"- Staff script: {u['script']} - worth about {fmt_uzs(u['extra_cm_month'])} extra margin per month.")
        if f["upcoming_holidays"]:
            out.append(f"- Plan around upcoming holidays: {', '.join(f['upcoming_holidays'][:3])}.")
        return "\n".join(out)
    if intent == "price":
        out = ["**Price changes where demand data is reliable:**"]
        for p in f["price_actions"][:6]:
            out.append(f"- {p['item_name']}: {p['current_price']:,.0f} -> **{p['recommended_price']:,.0f} UZS** "
                       f"(elasticity {p['elasticity']:.2f}; about +{fmt_uzs(p['cm_uplift_month'])} margin/month).")
        if not f["price_actions"]:
            out.append("- No confident price changes right now.")
        out.append(f"\nRun 2-week price tests first for: {', '.join(f['price_tests'][:6])}.")
        out.append("Roll out in one branch, compare with the other branch, then decide.")
        return "\n".join(out)
    if intent == "staff" and "staffing" in f:
        s = f["staffing"]
        return "\n".join([
            f"**A demand-based schedule for the next 7 days saves {s['hours_saved_7d']} staff-hours "
            f"(~{fmt_uzs(s['cost_saved_7d'])}) compared with a fixed schedule.**", "",
            f"- Peak hours: " + ", ".join(f"{b} {h}:00" for b, h in s["peak_hour"].items()) + ".",
            f"- Max waiters needed at peak: " + ", ".join(f"{b} {w}" for b, w in s["max_waiters"].items()) + ".",
            f"- A fixed schedule would leave {s['understaffed_hours_fixed']} hours understaffed (slow service at peaks).",
            "- Use split shifts: extra waiter for lunch (Yunusabad) and dinner peaks (Chilanzar), fewer staff 15:00-17:00."])
    if intent == "purchase" and "purchase_top" in f:
        out = ["**Purchase plan for the next 7 days (forecast x recipes + 10% safety stock):**"]
        for p in f["purchase_top"][:8]:
            out.append(f"- {p['ingredient']}: {p['order_qty']:.0f} {p['unit']} ({fmt_uzs(p['order_cost'])})")
        out.append("Order meat, fish and greens daily; dry goods weekly.")
        return "\n".join(out)
    if intent == "waste" and "waste_reduction" in f:
        return (f"**Ordering perishables from the forecast cuts waste by about {pct(f['waste_reduction'], False)} "
                "compared with 'last week + 15%'.** See Operations -> Waste backtest for the weekly breakdown.")
    if intent == "upsell":
        out = ["**Best upsell scripts (based on what guests already buy together):**"]
        for u in f["upsell"][:5]:
            out.append(f"- {u['script']} - attach rate now {u['confidence']:.0%}, lift {u['lift']:.1f}x, "
                       f"~{fmt_uzs(u['extra_cm_month'])} extra margin/month if 10% of guests accept.")
        return "\n".join(out)
    if intent == "menu":
        seg = f["segments"]
        return "\n".join(["**Menu engineering (popularity x margin within each category):**",
                          f"- Stars (keep & feature): {', '.join(seg['Star'][:8])}",
                          f"- Plowhorses (popular, low margin - cut cost or small price rise): {', '.join(seg['Plowhorse'][:8])}",
                          f"- Puzzles (profitable, under-ordered - promote): {', '.join(seg['Puzzle'][:8])}",
                          f"- Dogs (replace or remove): {', '.join(seg['Dog'][:8]) or '-'}"])
    if intent == "forecast":
        out = ["**Revenue forecast for the next 7 days:**"]
        for b, v in f["forecast_7d"].items():
            last = f["last_7d_revenue"].get(b, 0)
            out.append(f"- {b}: {fmt_uzs(v)} ({pct(v / last - 1) if last else 'n/a'} vs last 7 days)")
        if "accuracy" in f:
            out.append(f"\nTypical error {pct(f['accuracy']['model_wape'], False)} per day "
                       f"(manager rule of thumb: {pct(f['accuracy']['best_baseline_wape'], False)}).")
        if f["upcoming_holidays"]:
            out.append(f"Holidays ahead: {', '.join(f['upcoming_holidays'][:3])}.")
        return "\n".join(out)
    return briefing_offline(f)


def briefing_offline(f: dict) -> str:
    k, d = f["kpi"], f["kpi_delta"]
    out = [f"**Manager briefing - {f['kpi_period']}**", "",
           f"- Revenue {fmt_uzs(k['revenue'])} ({pct(d['revenue'])}), guests {k['covers']:,} ({pct(d['covers'])}), "
           f"average check {fmt_uzs(k['avg_check'])} ({pct(d['avg_check'])}), food cost {pct(k['food_cost_pct'], False)}."]
    drops = [a for a in f["anomalies"] if a["type"] == "drop"][:2]
    for a in drops:
        out.append(f"- Alert: {a['date']:%a %d %b} {a['branch']} {pct(a['deviation'])} - {a['explanation']}.")
    out.append("- Next 7 days: " + ", ".join(f"{b} {fmt_uzs(v)}" for b, v in f["forecast_7d"].items()) + ".")
    out += ["", "**Top actions this week**"]
    if f["upsell"]:
        u = f["upsell"][0]
        out.append(f"1. Train staff: {u['script']} (+{fmt_uzs(u['extra_cm_month'])}/month).")
    if f["price_actions"]:
        p = f["price_actions"][0]
        out.append(f"2. Price: {p['item_name']} {p['current_price']:,.0f} -> {p['recommended_price']:,.0f} UZS in one branch first.")
    if f["segments"].get("Puzzle"):
        out.append(f"3. Promote: {', '.join(f['segments']['Puzzle'][:3])}.")
    if "staffing" in f:
        out.append(f"4. Switch to the demand-based schedule (saves {f['staffing']['hours_saved_7d']} staff-hours).")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------------------

class LLMError(RuntimeError):
    pass


def build_payload(system: str, contents: list[dict], model: str) -> dict:
    """Request body for Gemini. The model only explains facts we already computed, so "thinking"
    is switched off on Gemini 2.5 Flash / Flash-Lite: faster answers and fewer billed tokens."""
    config = {"temperature": 0.3, "maxOutputTokens": 4096}
    if model.startswith("gemini-2.5-flash"):
        config["thinkingConfig"] = {"thinkingBudget": 0}
    return {"system_instruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": config}


@dataclass
class GeminiClient:
    api_key: str
    model: str = DEFAULT_MODEL
    timeout: int = 45

    def _post(self, model: str, payload: dict):
        return requests.post(GEMINI_URL.format(model=model), json=payload, timeout=self.timeout,
                             headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})

    def generate(self, system: str, messages: list[dict]) -> tuple[str, str]:
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                    for m in messages]
        last_err = None
        for model in [self.model] + [m for m in FALLBACK_MODELS if m != self.model]:
            payload = build_payload(system, contents, model)
            try:
                r = self._post(model, payload)
                if r.status_code == 400 and "thinkingConfig" in payload["generationConfig"]:
                    # older/newer model that does not accept the thinking setting: retry without it
                    payload["generationConfig"].pop("thinkingConfig")
                    r = self._post(model, payload)
            except requests.RequestException as e:
                raise LLMError(f"Network error: {e.__class__.__name__}") from e
            if r.status_code == 200:
                data = r.json()
                parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                if text.strip():
                    return text.strip(), model
                last_err = "empty response"
                continue
            if r.status_code in (404, 429, 500, 503):   # model unavailable or quota: try the next model
                last_err = f"HTTP {r.status_code}"
                continue
            if r.status_code in (400, 401, 403):
                raise LLMError(f"Gemini rejected the request (HTTP {r.status_code}). Check GEMINI_API_KEY.")
            last_err = f"HTTP {r.status_code}"
        raise LLMError(f"Gemini unavailable ({last_err}).")


def get_api_key() -> str | None:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return None


class Assistant:
    def __init__(self, facts: dict, api_key: str | None = None, model: str | None = None):
        self.facts = facts
        self.context = context_text(facts)
        key = api_key or get_api_key()
        self.client = GeminiClient(key, model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)) if key else None

    @property
    def engine(self) -> str:
        return f"Gemini ({self.client.model})" if self.client else "Offline rules (no API key)"

    def ask(self, question: str, history: list[dict] | None = None) -> dict:
        history = history or []
        t0 = time.perf_counter()
        if self.client:
            try:
                msgs = history[-8:] + [{"role": "user", "content": question}]
                text, model = self.client.generate(SYSTEM_PROMPT + "\nCONTEXT:\n" + self.context, msgs)
                return {"text": text, "engine": f"Gemini ({model})", "error": None,
                        "seconds": time.perf_counter() - t0}
            except LLMError as e:
                return {"text": offline_answer(question, self.facts), "engine": "Offline rules (fallback)",
                        "error": str(e), "seconds": time.perf_counter() - t0}
        return {"text": offline_answer(question, self.facts), "engine": "Offline rules", "error": None,
                "seconds": time.perf_counter() - t0}

    def briefing(self) -> dict:
        q = ("Write this week's manager briefing: 3-line performance summary, alerts that need attention, "
             "and the top 5 actions ranked by money impact (with the expected UZS impact).")
        if self.client:
            res = self.ask(q)
            if res["error"] is None:
                return res
            return {"text": briefing_offline(self.facts), "engine": "Offline rules (fallback)", "error": res["error"],
                    "seconds": res.get("seconds")}
        t0 = time.perf_counter()
        return {"text": briefing_offline(self.facts), "engine": "Offline rules", "error": None,
                "seconds": time.perf_counter() - t0}
