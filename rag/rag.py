"""The RAG class — retrieval + prompt construction + LLM call.

Composition-based (a retriever passed into the constructor), not a
3-level RAGBase/RAGVector/RAGPgVector subclass hierarchy —
a deliberate simplification (see README.md's Architecture section): we
don't swap retrieval backends at runtime in production, the retrieval
eval already picked one winner (query rewrite -> hybrid RRF -> rerank,
rag/retriever.py), so there's nothing left to subclass for.

The prompt construction is the part that's actually specific to this
project, not boilerplate: it has to encode the trust-tiering
(primary/secondary) and content_type awareness the whole schema was
built for back in the ingestion pipeline — otherwise all that metadata
would just sit unused in the payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from textwrap import dedent

from langfuse import get_client, observe
from langfuse.openai import OpenAI  # drop-in wrapper -- traces every .responses.create/.parse call to Langfuse

DEFAULT_MODEL = "gpt-5.6-terra"  # eval/evaluate_llm.py: terra vs sol, judge=gpt-5.5 (not terra/sol,
# to avoid self-preference bias). sol scored marginally higher (0.950 vs 0.933) but the entire gap
# was one hard edge-case question out of 30 -- not a robust difference -- while terra costs ~2.5x
# less on both input and output. Chose terra: cost should decide it when performance doesn't.

INSTRUCTIONS = dedent("""
    You are an assistant that helps people understand investing in
    Canada — registered accounts (TFSA, RRSP, FHSA, RESP, RDSP, RRIF,
    LIRA/LRSP, PRPP), investment instruments, how investments are
    taxed, who regulates them and what protects your money, and how
    residency status changes the rules. Many users are newcomers to
    Canada or permanent residents who may not know Canadian financial
    terminology.

    You are not a financial or tax advisor. Never give a personalized
    recommendation (e.g. "you should open a TFSA") — explain the rules
    and let the user decide, and note that a licensed advisor or the
    CRA should be consulted for their specific situation.

    Ground every answer strictly in the provided context. Do not use
    outside knowledge about Canadian tax/investment rules — the rules
    change over time and the context is the verified, current source.
    If the context does not contain enough information to answer,
    say so plainly rather than guessing.

    Each context passage is labeled with a trust tier:
    - PRIMARY: government or government-mandated sources (CRA, CIRO,
      AMF, CIPF, CDIC, Service Canada/ESDC, OSC). Prefer these for
      rules and numbers.
    - SECONDARY: banks, media, and other private sources. Useful for
      practical framing, but if a fact comes ONLY from a secondary
      source, say so explicitly rather than presenting it with the
      same confidence as a primary source.

    Some passages carry an "as of" date — mention it when you use a
    number so the user knows when that figure currently applies (in
    case it has since changed).

    Do not append your own source list or URLs to your answer — the
    interface displays the actual retrieved sources separately,
    correctly tiered and dated, and a second self-generated list would
    be redundant and error-prone (you could transcribe a URL wrong, or
    omit one the interface would otherwise show correctly).
""").strip()

PROMPT_TEMPLATE = dedent("""
    QUESTION: {question}

    CONTEXT:
    {context}
""").strip()


@dataclass
class RAGResult:
    answer: str
    trace_id: str | None  # for scoring this exact answer later (e.g. user feedback) -- see app/main.py
    sources: list[dict] = field(default_factory=list)  # the retrieved chunks, for a UI citation list distinct from the inline citations already in `answer`


class RAG:
    def __init__(self, retriever, llm_client: OpenAI | None = None, model: str = DEFAULT_MODEL,
                 instructions: str = INSTRUCTIONS, prompt_template: str = PROMPT_TEMPLATE):
        self.retriever = retriever
        self.llm_client = llm_client or OpenAI()
        self.model = model
        self.instructions = instructions
        self.prompt_template = prompt_template

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        return self.retriever.search(query, top_k=top_k)

    def build_context(self, results: list[dict]) -> str:
        blocks = []
        for r in results:
            tier_label = r["tier"].upper()
            source = r["source_authority"].upper()
            date_note = f" (as of {r['effective_date']})" if r.get("effective_date") else ""
            blocks.append(
                f"[{tier_label} - {source}]{date_note}\n{r['text']}\nSource: {r['url']}"
            )
        return "\n\n".join(blocks)

    def build_prompt(self, query: str, results: list[dict]) -> str:
        context = self.build_context(results)
        return self.prompt_template.format(question=query, context=context)

    def llm(self, prompt: str) -> str:
        response = self.llm_client.responses.create(
            model=self.model,
            input=[
                {"role": "developer", "content": self.instructions},
                {"role": "user", "content": prompt},
            ],
        )
        return response.output_text

    @observe(name="rag-answer")
    def rag(self, query: str, top_k: int = 5) -> RAGResult:
        """Top-level entry point -- the @observe here is what groups the
        query-rewrite call (inside self.search -> Retriever.search),
        retrieval, and the generation call (self.llm) into one Langfuse
        trace per user question, instead of showing up as disconnected
        generations.

        Returns the trace_id alongside the answer specifically so a UI
        can score *this* answer later (thumbs up/down) -- Streamlit
        reruns the whole script on every interaction, so by the time a
        feedback button is clicked there's no "current trace" context
        left; the id has to be captured now and carried in session
        state until the button click, then used with create_score(),
        not score_current_trace()."""
        results = self.search(query, top_k=top_k)
        prompt = self.build_prompt(query, results)
        answer = self.llm(prompt)
        trace_id = get_client().get_current_trace_id()
        return RAGResult(answer=answer, trace_id=trace_id, sources=results)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    from retriever import Retriever

    rag = RAG(retriever=Retriever.build())
    for q in [
        "I just moved to Canada, can I put money in a tax-free account?",
        "who protects my money if my investment broker goes bankrupt",
    ]:
        print(f"Q: {q}")
        print(f"A: {rag.rag(q).answer}\n")
