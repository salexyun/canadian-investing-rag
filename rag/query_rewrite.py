"""Query rewriting — the third best-practices item, alongside hybrid
search and reranking.

A lightweight LLM call that runs before retrieval, rewriting the user's
raw question into a clearer, retrieval-optimized query: fixing typos,
tightening multi-part questions, and — the one specific to this
project — surfacing the likely Canadian account-type term (TFSA, RRSP,
etc.) when a plain-language question implies one without naming it,
since that's exactly the lexical gap BM25 can't cross on its own.

Model: gpt-5.6-luna, same choice as ground-truth generation — simple
transformation task, and this one runs on every single query, so
keeping it cheap matters more here than anywhere else in the project.

Its actual value isn't assumed — see eval/evaluate_retrieval.py's
query-rewrite variant, tested against the same ground-truth set rather
than added as an unverified best-practices checkbox.
"""

from __future__ import annotations

import os

from langfuse.openai import OpenAI  # drop-in wrapper -- traces every .responses.create/.parse call to Langfuse

MODEL = "gpt-5.6-luna"

INSTRUCTIONS = """
Rewrite the user's question into a single, clear, standalone search
query for retrieving passages from a knowledge base about investing in
Canada (registered accounts like TFSA/RRSP/FHSA/RESP/RDSP/RRIF/LIRA-LRSP,
investment taxation, regulation and investor protection, and how
residency status affects the rules).

- Fix typos and grammar.
- If the question is in plain/casual language and clearly implies a
  specific Canadian account type or regulatory body without naming it,
  add that term explicitly (e.g. a question about "a tax-free account"
  should mention "TFSA"; a question about "who protects my money if my
  broker fails" should mention "CIPF").
- Keep it concise — one sentence, no preamble.
- Do not answer the question — only rewrite it.

Return ONLY the rewritten query, nothing else.
""".strip()


def rewrite_query(query: str, client: OpenAI | None = None) -> str:
    client = client or OpenAI()
    response = client.responses.create(
        model=MODEL,
        input=[
            {"role": "developer", "content": INSTRUCTIONS},
            {"role": "user", "content": query},
        ],
    )
    rewritten = response.output_text.strip()
    return rewritten if rewritten else query  # never return empty — fall back to the original


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    for q in [
        "I just moved to Canada, can I put money in a tax-free account?",
        "what happens to my investments if I leave Canada",
        "whos protects my $ if my broker goes under???",
    ]:
        print(f"{q!r}\n  -> {rewrite_query(q)!r}\n")
