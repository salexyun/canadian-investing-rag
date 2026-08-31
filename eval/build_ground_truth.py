"""Build the retrieval evaluation ground-truth set.

Generates synthetic questions per chunk via LLM structured output — a
standard retrieval-eval technique (per-document ground truth, not
hand-written), extended one step for this project: two questions per
sampled chunk, deliberately different styles:

- jargon_question: as someone who already knows Canadian investing
  terminology would ask it
- plain_language_question: as a newcomer who doesn't know the jargon
  would ask it, describing the situation without the technical terms

Tagging each record with its phrasing_style is the actual point — it lets
the retrieval eval (next step) measure whether BM25 specifically
underperforms on the plain-language half, rather than reporting one
blended score that would hide exactly the effect this whole BM25-vs-
vector-vs-hybrid investigation is about.

Sampling is stratified, not exhaustive or purely random — generating off
all 1,052 chunks would give ~2,000 questions, past the useful range and
redundant. Instead: guaranteed coverage of every account_type, an
oversample of numeric_fact chunks (only 62 exist corpus-wide, and it's
the highest-stakes content_type — see the TFSA/FHSA collision-risk
finding in data/README.md), an oversample of special_situations chunks
(this project's actual differentiator), and a few secondary-tier chunks
mixed in.

Model: gpt-5.6-luna — cheapest current-generation tier ($0.20/$1.20 per
1M tokens, confirmed via OpenAI's own pricing docs, not an aggregator
estimate). Chosen deliberately for this task specifically: simple
structured-output paraphrasing, ~50 one-off calls, no deep reasoning
needed. Other LLM calls in this project (main RAG generation, LLM-judge
eval) use different, more capable models chosen for what those tasks
actually need — see README.md's LLM evaluation section.

Usage:
    python eval/build_ground_truth.py
"""

from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from tqdm import tqdm

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
CHUNKS_PATH = REPO_ROOT / "data" / "processed" / "chunks.jsonl"
OUTPUT_PATH = Path(__file__).resolve().parent / "retrieval_ground_truth.jsonl"

MODEL = "gpt-5.6-luna"
INPUT_PRICE_PER_M = 0.20
OUTPUT_PRICE_PER_M = 1.20
RANDOM_SEED = 42

INSTRUCTIONS = """
You are generating evaluation questions for a Canadian investing RAG
system, to test whether retrieval fetches this exact passage in response
to a real user's question.

Given a passage from an official or government-endorsed Canadian source,
write two DIFFERENT questions a real user could ask that this passage
directly and fully answers:

1. jargon_question: written by someone who already knows Canadian
   investing terminology — uses precise terms (account type names, tax
   terms) exactly as they'd naturally ask it.
2. plain_language_question: written by a newcomer to Canada who does NOT
   know Canadian financial jargon — describe their situation or need in
   plain language, avoiding the specific account-type name/acronym or
   technical terms the passage uses.

Rules:
- Both questions must be fully answerable using ONLY the given passage.
- Do not quote or closely paraphrase a sentence from the passage —
  write a natural question a person would actually type, not a
  restatement of the passage's wording.
- Keep each question under 25 words.
""".strip()


class GroundTruthQuestions(BaseModel):
    jargon_question: str
    plain_language_question: str


def sample_chunks(chunks: list[dict], rng: random.Random) -> list[dict]:
    sampled: dict[str, dict] = {}

    # 1. Every account_type covered — up to 3 chunks each, preferring
    # numeric_fact / special_situations chunks within that type when available.
    by_account_type: dict[str, list[dict]] = {}
    for c in chunks:
        by_account_type.setdefault(c["facets"]["account_type"], []).append(c)
    for group in by_account_type.values():
        ranked = sorted(
            group,
            key=lambda c: (
                c["content_type"] != "numeric_fact",
                not c["facets"]["special_situations"],
            ),
        )
        for c in ranked[:3]:
            sampled[c["chunk_id"]] = c

    # 2. Oversample numeric_fact chunks specifically.
    numeric_facts = [c for c in chunks if c["content_type"] == "numeric_fact"]
    rng.shuffle(numeric_facts)
    for c in numeric_facts[:15]:
        sampled[c["chunk_id"]] = c

    # 3. Oversample special_situations chunks specifically.
    special = [c for c in chunks if c["facets"]["special_situations"]]
    rng.shuffle(special)
    for c in special[:10]:
        sampled[c["chunk_id"]] = c

    # 4. A few secondary-tier chunks mixed in.
    secondary = [c for c in chunks if c["tier"] == "secondary"]
    rng.shuffle(secondary)
    for c in secondary[:5]:
        sampled[c["chunk_id"]] = c

    return list(sampled.values())


def _shares_long_run(a: str, b: str, min_words: int = 5) -> bool:
    """True if a run of >= min_words consecutive words from `a` appears
    verbatim in `b` — catches the LLM just lifting a sentence instead of
    writing a natural question, which would make that record trivially
    easy for BM25 and not a real test of anything."""
    words_a = a.lower().split()
    b_lower = b.lower()
    for i in range(len(words_a) - min_words + 1):
        run = " ".join(words_a[i : i + min_words])
        if run in b_lower:
            return True
    return False


def generate_for_chunk(client: OpenAI, chunk: dict) -> tuple[list[dict], dict]:
    """Returns (ground_truth_records, usage_dict)."""
    user_prompt = f"PASSAGE:\n{chunk['text']}"
    total_usage = {"input_tokens": 0, "output_tokens": 0}

    result = None
    for attempt in range(2):  # one retry if a verbatim lift is caught
        response = client.responses.parse(
            model=MODEL,
            input=[
                {"role": "developer", "content": INSTRUCTIONS},
                {"role": "user", "content": user_prompt},
            ],
            text_format=GroundTruthQuestions,
        )
        total_usage["input_tokens"] += response.usage.input_tokens
        total_usage["output_tokens"] += response.usage.output_tokens
        result = response.output_parsed

        verbatim = _shares_long_run(result.jargon_question, chunk["text"]) or _shares_long_run(
            result.plain_language_question, chunk["text"]
        )
        if not verbatim:
            break
        if attempt == 0:
            user_prompt += "\n\n(Your previous attempt quoted the passage too closely — write it in your own words.)"

    flagged = _shares_long_run(result.jargon_question, chunk["text"]) or _shares_long_run(
        result.plain_language_question, chunk["text"]
    )

    records = [
        {
            "question": result.jargon_question,
            "chunk_id": chunk["chunk_id"],
            "phrasing_style": "jargon",
            "account_type": chunk["facets"]["account_type"],
            "content_type": chunk["content_type"],
            "tier": chunk["tier"],
            "flagged_verbatim": flagged,
        },
        {
            "question": result.plain_language_question,
            "chunk_id": chunk["chunk_id"],
            "phrasing_style": "plain_language",
            "account_type": chunk["facets"]["account_type"],
            "content_type": chunk["content_type"],
            "tier": chunk["tier"],
            "flagged_verbatim": flagged,
        },
    ]
    return records, total_usage


def main() -> int:
    chunks = [json.loads(line) for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    rng = random.Random(RANDOM_SEED)
    sampled = sample_chunks(chunks, rng)
    print(f"Sampled {len(sampled)} chunks from {len(chunks)} total -> generating {len(sampled) * 2} questions")

    client = OpenAI()
    all_records: list[dict] = []
    total_usage = {"input_tokens": 0, "output_tokens": 0}

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(generate_for_chunk, client, c) for c in sampled]
        for future in tqdm(futures):
            records, usage = future.result()
            all_records.extend(records)
            total_usage["input_tokens"] += usage["input_tokens"]
            total_usage["output_tokens"] += usage["output_tokens"]

    n_flagged = sum(1 for r in all_records if r["flagged_verbatim"])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cost = (
        total_usage["input_tokens"] / 1_000_000 * INPUT_PRICE_PER_M
        + total_usage["output_tokens"] / 1_000_000 * OUTPUT_PRICE_PER_M
    )
    print(f"\n{len(all_records)} questions written to {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"{n_flagged} still flagged as verbatim-ish after retry (kept, marked for review)")
    print(f"Cost: ${cost:.4f} ({total_usage['input_tokens']} input / {total_usage['output_tokens']} output tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
