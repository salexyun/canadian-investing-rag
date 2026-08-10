"""The RAG class — retrieval + prompt construction + LLM call.

Composition-based (a retriever passed into the constructor), not the
coursework's 3-level RAGBase/RAGVector/RAGPgVector subclass hierarchy —
a deliberate simplification (see TODO.md's "Decisions" section): we
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

from textwrap import dedent

from openai import OpenAI

DEFAULT_MODEL = "gpt-5.6-terra"  # placeholder until the LLM evaluation step picks terra vs sol

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

    Cite the source(s) you used by URL at the end of your answer.
""").strip()

PROMPT_TEMPLATE = dedent("""
    QUESTION: {question}

    CONTEXT:
    {context}
""").strip()


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

    def rag(self, query: str, top_k: int = 5) -> str:
        results = self.search(query, top_k=top_k)
        prompt = self.build_prompt(query, results)
        return self.llm(prompt)


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
        print(f"A: {rag.rag(q)}\n")
