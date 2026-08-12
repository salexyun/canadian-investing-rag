"""Streamlit interface for the Canadian Investing Assistant.

Single-question RAG chat (no multi-turn memory — each question is
answered independently, matching what rag/rag.py actually implements)
with citations shown as a distinct source list, and thumbs up/down
feedback wired to Langfuse.

Feedback scoring uses create_score(trace_id=...), not
score_current_trace() — Streamlit reruns the whole script on every
widget interaction, so by the time a feedback button is clicked there
is no "current trace" execution context left from when the answer was
generated. The trace_id has to be captured at generation time
(rag.rag() already returns it for exactly this reason) and carried in
st.session_state until the click.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rag"))

from langfuse import get_client  # noqa: E402
from rag import RAG  # noqa: E402
from retriever import Retriever  # noqa: E402

st.set_page_config(page_title="Canadian Investing Assistant", page_icon="🍁")


@st.cache_resource(show_spinner="Loading models (embedding, reranker, BM25 index)...")
def get_rag() -> RAG:
    # Expensive to build (local embedding + cross-encoder models, BM25
    # index) — cached across reruns, or Streamlit would reload all of
    # it on every single button click.
    return RAG(retriever=Retriever.build())


st.title("🍁 Canadian Investing Assistant")
st.caption(
    "Accounts (TFSA, RRSP, FHSA, RESP, RDSP, RRIF, LIRA/LRSP, PRPP), taxation, "
    "regulation, and how residency status changes the rules."
)
st.warning(
    "⚠️ **Not financial or tax advice.** This is an educational project. Answers are "
    "generated from public government and government-endorsed sources and may be "
    "incomplete or out of date. Consult a licensed advisor or the CRA before making "
    "financial decisions.",
    icon="⚠️",
)

if "history" not in st.session_state:
    st.session_state.history = []  # list of dicts: question, result, feedback (None/1/0)

rag = get_rag()

question = st.text_input(
    "Ask a question",
    placeholder="e.g. I just moved to Canada, can I put money in a tax-free account?",
)
ask = st.button("Ask", type="primary")

if ask and question.strip():
    with st.spinner("Thinking..."):
        result = rag.rag(question.strip())
    st.session_state.history.insert(0, {"question": question.strip(), "result": result, "feedback": None})

if st.session_state.history:
    current = st.session_state.history[0]
    st.markdown("---")
    st.markdown(f"**You:** {current['question']}")
    st.markdown(current["result"].answer)

    # Multiple retrieved chunks can come from the same page (different
    # sections) -- dedupe by URL for the citation list, since "here are
    # 5 sources" reading as the same link twice looks like a bug even
    # though each chunk genuinely contributed to the answer.
    seen_urls: set[str] = set()
    unique_sources = []
    for s in current["result"].sources:
        if s["url"] not in seen_urls:
            seen_urls.add(s["url"])
            unique_sources.append(s)

    with st.expander(f"Sources ({len(unique_sources)})"):
        for s in unique_sources:
            tier = s["tier"].upper()
            authority = s["source_authority"].upper()
            date_note = f" — as of {s['effective_date']}" if s.get("effective_date") else ""
            st.markdown(f"- **[{tier} · {authority}]**{date_note} [{s['url']}]({s['url']})")

    if current["result"].trace_id:
        col1, col2, _ = st.columns([1, 1, 6])
        feedback = current["feedback"]
        with col1:
            if st.button("👍" + (" ✓" if feedback == 1 else ""), key="up"):
                get_client().create_score(
                    trace_id=current["result"].trace_id, name="user_feedback", value=1.0, data_type="NUMERIC"
                )
                current["feedback"] = 1
                st.rerun()
        with col2:
            if st.button("👎" + (" ✓" if feedback == 0 else ""), key="down"):
                get_client().create_score(
                    trace_id=current["result"].trace_id, name="user_feedback", value=0.0, data_type="NUMERIC"
                )
                current["feedback"] = 0
                st.rerun()
        if feedback is not None:
            st.caption("Thanks for the feedback!")

    if len(st.session_state.history) > 1:
        st.markdown("---")
        st.caption("Earlier this session")
        for item in st.session_state.history[1:]:
            with st.expander(item["question"]):
                st.markdown(item["result"].answer)
