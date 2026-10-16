"""AI assistant: ask questions about the business in plain language (EN / RU / UZ)."""
import os

import streamlit as st

import ui
from horeca_dss.assistant import DEFAULT_MODEL, Assistant, get_api_key

ui.page("AI assistant", ":material/smart_toy:")
ds = ui.get_dataset()
ui.sidebar(ds, show_branch=False)

st.title("AI assistant")
st.caption("Ask about revenue, menu, prices, staff or purchasing. Answers are grounded in the numbers this "
           "platform calculated — the language model explains them, it does not invent them.")

with st.expander("Gemini settings", expanded=not bool(get_api_key() or st.session_state.get("session_api_key"))):
    if get_api_key():
        st.success("Gemini API key found in the environment / .env file.", icon=":material/key:")
    else:
        st.info("No API key found. The assistant answers with built-in rules. To enable Gemini, put "
                "`GEMINI_API_KEY=...` into the `.env` file (free key: aistudio.google.com) or paste it below "
                "for this session only.", icon=":material/info:")
        key = st.text_input("Gemini API key (kept only in this browser session)", type="password")
        if key:
            st.session_state["session_api_key"] = key.strip()
    model = st.text_input("Model", value=st.session_state.get("model", os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)))
    st.session_state["model"] = model

f = ui.facts(ds)
bot = Assistant(f, api_key=st.session_state.get("session_api_key"), model=st.session_state.get("model"))
st.caption(f"Engine: **{bot.engine}**")

chat = st.session_state.setdefault("chat", [])
QUICK = ["Why did revenue drop on Tuesday?", "What should we promote this weekend?",
         "Which prices should we change?", "How many waiters do we need next week?",
         "Что закупить на следующую неделю?"]
asked = None
rows = [QUICK[:3], QUICK[3:] + ["__briefing__"]]
for row in rows:
    cols = st.columns(3)
    for col, q in zip(cols, row):
        label = "Weekly manager briefing" if q == "__briefing__" else q
        if col.button(label, key=f"q_{q}", type="primary" if q == "__briefing__" else "secondary",
                      icon=":material/summarize:" if q == "__briefing__" else ":material/help:"):
            asked = q

for m in chat:
    with st.chat_message(m["role"], avatar=":material/person:" if m["role"] == "user" else ":material/smart_toy:"):
        st.markdown(m["content"])
        if m.get("engine"):
            st.caption(m["engine"] + (f" · {m['error']}" if m.get("error") else ""))

typed = st.chat_input("Ask in English, Russian or Uzbek…")
question = typed or asked
if question:
    label = "Write this week's manager briefing" if question == "__briefing__" else question
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(label)
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        with st.spinner("Thinking…"):
            history = [{"role": m["role"], "content": m["content"]} for m in chat]
            res = bot.briefing() if question == "__briefing__" else bot.ask(question, history)
        st.markdown(res["text"])
        st.caption(res["engine"] + (f" · {res['error']}" if res.get("error") else ""))
    chat += [{"role": "user", "content": label},
             {"role": "assistant", "content": res["text"], "engine": res["engine"], "error": res.get("error")}]

c1, c2 = st.columns([1, 5])
if c1.button("Clear chat", icon=":material/delete:"):
    st.session_state["chat"] = []
    st.rerun()
with st.expander("What the assistant knows (the facts sent to the model)"):
    st.code(bot.context, language="text")

ui.footer()
