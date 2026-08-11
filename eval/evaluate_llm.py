"""Evaluate LLM approaches for the main RAG answer generation.

Compares gpt-5.6-terra vs gpt-5.6-sol as the generation model, using the
LLM-as-judge pattern from the coursework's judge.py: structured output,
a 3-way relevance verdict (RELEVANT/PARTLY_RELEVANT/NON_RELEVANT) plus
an explanation.

Standalone, not dependent on Langfuse being set up — same reasoning as
building the retrieval eval harness independently: this decision needs
to happen now, with real data, not wait on an external account-creation
step. Langfuse gets wired in afterward, for ongoing observability of
whichever model wins here, not as a precondition for deciding.

Judge model: gpt-5.5, deliberately NOT one of the two candidates being
compared. Using `terra` as both a candidate and the judge would risk
self-preference bias (a model rating its own outputs more favourably) —
caught before running this, not after.

Retrieval runs once per question, sequentially, and both candidate
models are shown the identical retrieved context — otherwise the two
models could be compared on slightly different context (query rewriting
is itself an LLM call, not perfectly deterministic), which would
confound "which model generates better" with "which model got luckier
retrieval." Generation + judging (pure API calls, safe to parallelize)
run concurrently; the retriever's local models (embedder, cross-encoder)
are not thread-safe to call concurrently — an earlier version of this
script shared one Retriever across a thread pool for the whole
search+generate+judge pipeline and crashed with a segfault.

Usage:
    python eval/evaluate_llm.py
"""

from __future__ import annotations

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from tqdm import tqdm

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "rag"))

from rag import RAG  # noqa: E402
from retriever import Retriever  # noqa: E402

GROUND_TRUTH_PATH = Path(__file__).resolve().parent / "retrieval_ground_truth.jsonl"
RESULTS_PATH = Path(__file__).resolve().parent / "llm_eval_results.json"

CANDIDATE_MODELS = ["gpt-5.6-terra", "gpt-5.6-sol"]
JUDGE_MODEL = "gpt-5.5"
SAMPLE_SIZE = 30  # unique questions sampled for this eval — LLM generation+judging is
                   # more expensive per-call than retrieval eval, so a smaller sample
RANDOM_SEED = 42

JUDGE_INSTRUCTIONS = """
You are an expert evaluator for a RAG system that answers questions
about investing in Canada. Analyze the relevance and quality of the
generated answer to the given question.

Classify the answer as:
- RELEVANT: the answer directly and correctly addresses the question
- PARTLY_RELEVANT: the answer partially addresses the question, or is
  correct but incomplete, or hedges more than the context warrants
- NON_RELEVANT: the answer does not address the question, is
  incorrect, or contradicts the given context
""".strip()

JUDGE_PROMPT = """
Question: {question}
Generated Answer: {answer}
""".strip()


class RelevanceVerdict(BaseModel):
    relevance: Literal["RELEVANT", "PARTLY_RELEVANT", "NON_RELEVANT"]
    explanation: str


def judge_answer(client: OpenAI, question: str, answer: str) -> RelevanceVerdict:
    response = client.responses.parse(
        model=JUDGE_MODEL,
        input=[
            {"role": "developer", "content": JUDGE_INSTRUCTIONS},
            {"role": "user", "content": JUDGE_PROMPT.format(question=question, answer=answer)},
        ],
        text_format=RelevanceVerdict,
    )
    return response.output_parsed


def generate_and_judge(question: dict, prompt: str, model: str, client: OpenAI) -> dict:
    """Pure-API step: generate with `model`, then judge. Safe to run
    concurrently — no local model state touched here."""
    response = client.responses.create(
        model=model,
        input=[{"role": "developer", "content": _rag_instructions()}, {"role": "user", "content": prompt}],
    )
    answer = response.output_text
    verdict = judge_answer(client, question["question"], answer)
    return {
        "question": question["question"],
        "chunk_id": question["chunk_id"],
        "phrasing_style": question["phrasing_style"],
        "model": model,
        "answer": answer,
        "relevance": verdict.relevance,
        "explanation": verdict.explanation,
    }


def _rag_instructions() -> str:
    # Reuse the exact same system instructions the production RAG class
    # uses, rather than a second copy that could drift from it.
    from rag import INSTRUCTIONS
    return INSTRUCTIONS


def main() -> int:
    all_questions = [json.loads(line) for line in GROUND_TRUTH_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    rng = random.Random(RANDOM_SEED)
    sample = rng.sample(all_questions, SAMPLE_SIZE)
    print(f"Sampled {len(sample)} questions, comparing {CANDIDATE_MODELS} (judge: {JUDGE_MODEL})")

    print("Building retriever...")
    retriever = Retriever.build()
    client = OpenAI()
    rag_for_prompts = RAG(retriever=retriever, llm_client=client)  # only used for build_prompt(), not generation

    print("Retrieving context for each question (sequential — local models aren't thread-safe)...")
    prompts_by_question: list[tuple[dict, str]] = []
    for q in tqdm(sample):
        results = retriever.search(q["question"], top_k=5)
        prompt = rag_for_prompts.build_prompt(q["question"], results)
        prompts_by_question.append((q, prompt))

    print("Generating + judging (parallel, API-only)...")
    jobs = [(q, prompt, model) for q, prompt in prompts_by_question for model in CANDIDATE_MODELS]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(generate_and_judge, q, prompt, model, client) for q, prompt, model in jobs]
        for future in tqdm(futures):
            results.append(future.result())

    print("\n=== Results by model ===")
    score_map = {"RELEVANT": 1.0, "PARTLY_RELEVANT": 0.5, "NON_RELEVANT": 0.0}
    summary = {}
    for model in CANDIDATE_MODELS:
        model_results = [r for r in results if r["model"] == model]
        n = len(model_results)
        relevant = sum(1 for r in model_results if r["relevance"] == "RELEVANT")
        partly = sum(1 for r in model_results if r["relevance"] == "PARTLY_RELEVANT")
        non = sum(1 for r in model_results if r["relevance"] == "NON_RELEVANT")
        avg_score = sum(score_map[r["relevance"]] for r in model_results) / n
        summary[model] = {"n": n, "relevant": relevant, "partly_relevant": partly,
                           "non_relevant": non, "avg_score": avg_score}
        print(f"  {model:16} RELEVANT={relevant:2}  PARTLY={partly:2}  NON={non:2}  avg_score={avg_score:.3f}  (n={n})")

    winner = max(summary, key=lambda m: summary[m]["avg_score"])
    print(f"\nBest overall (by avg_score): {winner}")

    RESULTS_PATH.write_text(json.dumps({"summary": summary, "winner": winner, "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Full results written to {RESULTS_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
