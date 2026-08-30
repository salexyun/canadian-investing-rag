# Canadian Investing Assistant

A RAG application that answers questions about investing in Canada —
accounts, instruments, taxation, regulation/investor protection, and
the residency-specific rules that trip up new Canadians and permanent
residents.

> ⚠️ **Not financial or tax advice.** This project is for educational
> purposes only. Answers are generated from public government sources
> and may be incomplete or out of date. Consult a licensed advisor or
> the CRA directly before making financial decisions.

Built as the capstone project for the
[DataTalks.Club LLM Zoomcamp](https://github.com/DataTalksClub/llm-zoomcamp).

## Table of contents

- [Problem description](#problem-description)
- [Scope](#scope)
- [Architecture](#architecture)
- [Dataset](#dataset)
- [Setup](#setup)
- [Usage](#usage)
- [Evaluation](#evaluation)
- [Monitoring](#monitoring)
- [Evaluation criteria checklist](#evaluation-criteria-checklist)
- [Project structure](#project-structure)
- [License](#license)

## Problem description

Investing in Canada is scattered across sources with no single place
to ask a plain-language question: the accounts you can hold (TFSA,
RRSP, FHSA, RESP, RDSP, RRIF, LIRA/LRSP), the instruments inside them,
how they're taxed, who regulates them and what protects your money if
a dealer or bank fails, and — the part generic financial advice
usually misses — how residency and immigration status change the
answer. New Canadians and permanent residents in particular struggle
to find clear, consolidated answers: generic advice online is often
US-centric, and government pages are scattered across canada.ca, CIRO,
the provincial securities regulators, CIPF, and CDIC.

This project builds a RAG assistant over official and government-
endorsed Canadian sources so users can ask natural-language questions
(e.g. *"I landed as a PR eight months ago, can I open an FHSA?"* or
*"what happens to my TFSA if I move abroad?"*) and get a grounded,
cited answer instead of having to piece it together themselves.

## Scope

Five pillars, all specifically about **investing** in Canada — not
general personal finance:

1. **Accounts** — TFSA, RRSP, RRIF, FHSA, RESP, RDSP, LIRA/LRSP, PRPP, non-registered
2. **Instruments** — stocks, ETFs, mutual funds, bonds, GICs, REITs, options, crypto, and how they trade in Canada specifically
3. **Taxation** — capital gains/losses, dividend tax credit, attribution/superficial-loss rules, foreign tax credit, foreign property reporting (T1135), US withholding tax inside registered accounts
4. **Regulation & investor protection** — CIRO, provincial regulators (AMF for Quebec), CIPF (brokerage insolvency), CDIC (deposit/GIC insurance)
5. **Residency & newcomer-specific rules** — the differentiator: foreign property reporting, first-year tax residency, departure tax, CPP/OAS as they interact with investing decisions

**Explicitly out of scope** — different domains, not just unhandled
edge cases: budgeting, debt/credit, general insurance (life/auto/
home), real estate/mortgages as an asset class (FHSA stays in as a
savings vehicle; rental-property investing doesn't), business/
corporate tax and incorporation, estate law beyond account-death
rules, and personalized investment advice or recommendations.

## Architecture

```
CRA / CIRO / AMF / ESDC / OSC / CIPF / CDIC / FSRA / Retraite Québec + secondary sources
        │
        ▼
 Kestra-orchestrated ingestion pipeline (fetch → chunk → embed → load)
        │
        ▼
 knowledge base (Qdrant vector search + BM25 keyword search)
        │
        ▼
 retrieval: query rewrite → hybrid RRF fusion → cross-encoder rerank
        │
        ▼
 prompt construction (trust-tier + freshness aware) → LLM → answer with citations
        │
        ▼
 Streamlit UI ──── feedback (👍/👎) + traces ──► Langfuse Cloud (dashboard, LLM-as-judge eval)
```

Every stage past "knowledge base" is a real, evaluated decision, not
the obvious default — see [Evaluation](#evaluation) for the numbers
that justify hybrid search, reranking, and query rewriting, and why
retrieval and generation each landed on the model/approach they did.

## Dataset

Sourced from official government and government-endorsed publications
— see [data/README.md](data/README.md) for the full, vetted list
(legitimacy, appropriateness, and tested fetchability per source), the
primary/secondary trust-tier split, and the schema each page and
chunk is tagged with. In short:

- **Primary** (9 authorities): CRA, CIRO, AMF, Service Canada/ESDC,
  OSC/GetSmarterAboutMoney, CIPF, CDIC, FSRA (Ontario pensions/LIRAs),
  Retraite Québec (Quebec pensions/LRSPs)
- **Secondary** (7 authorities, supplementary only — never used to
  answer a rules or numbers question on their own): TD, FP Canada,
  MoneySense, RBC, Questrade, Wealthsimple, Qtrade

**98 pages → 1,098 chunks** (1,015 primary / 83 secondary). Full
per-authority breakdown, the content-quality audit that found and
fixed the "CRA hub page" problem, and the chunking bugs it took to get
a clean corpus all live in [data/README.md](data/README.md).

## Setup

### Prerequisites

- Docker & Docker Compose
- [uv](https://docs.astral.sh/uv/) (for local dev outside containers — not pip/conda)
- An OpenAI API key
- A [Langfuse Cloud](https://cloud.langfuse.com) account (free tier) for tracing/monitoring

### 1. Clone and configure

```bash
git clone https://github.com/<your-username>/canadian-investing-rag.git
cd canadian-investing-rag
cat > .env << 'EOF'
OPENAI_API_KEY=
QDRANT_URL=http://localhost:6333
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://cloud.langfuse.com
EOF
# then edit .env with your actual keys
```

`QDRANT_URL` is `localhost` here for local (non-Docker) dev — running
everything through `docker compose` overrides it to Qdrant's
in-network hostname automatically (see `docker-compose.yml`), so you
don't need to change this value yourself either way.

```bash
uv sync
uv run playwright install chromium   # needed for the CRA/ESDC/CIRO/AMF/FSRA/Retraite Québec fetch path — see below
```

### 2. Run everything via Docker Compose

```bash
docker compose up -d vector-db
docker compose up -d --build app
```

- App: http://localhost:8501
- Qdrant: http://localhost:6333

This starts the app against the already-fetched, already-embedded
corpus (Qdrant's data persists in a named Docker volume). You only
need the steps below if you want to re-fetch the dataset yourself or
inspect/re-run the ingestion pipeline.

### 3. (Optional) Re-run ingestion yourself

The dataset is fetched, chunked, and loaded by three scripts, which
can be run directly:

```bash
uv run python ingestion/fetch.py            # data/raw/manifest.jsonl
uv run python ingestion/pipeline.py         # data/processed/chunks.jsonl
uv run python ingestion/load_vector_store.py   # embeds + upserts into Qdrant
```

Each also takes `--only <source_ids>` to scope to specific pages
(`fetch.py` additionally takes `--tier primary|secondary`) — useful
for testing a single new source without re-running the full ~93-page
fetch (which takes over an hour: several sources sit behind bot
protection and need a real headless-browser session, not just a plain
HTTP request — see [data/README.md](data/README.md#fetchability-summary)).

**Or run them orchestrated, via Kestra** (`flows/ingestion.yml`) —
this is how the rubric's "automated ingestion with a special tool"
criterion is met, not just documentation of intent:

```bash
docker compose build ingestion         # image with the Playwright/Chromium binary
docker compose up -d kestra
```

Open http://localhost:8080, create the local admin account through
Kestra's own first-run wizard (one-time, local-only — this isn't
exposed outside your machine), then sync the flow definition in:

```bash
docker compose exec kestra sh /app/kestra flow namespace update \
  canadian-investing-rag /app/flows \
  --server http://localhost:8080 --user '<your-admin-email>:<your-password>'
```

Trigger a run from the Kestra UI (or `POST
/api/v1/main/executions/canadian-investing-rag/canadian_investing_ingestion`),
optionally passing `only_ids` to scope it. The flow runs the same
three scripts above, unchanged, as sibling containers on the compose
network.

### 4. Run evaluations

```bash
uv run python eval/build_ground_truth.py     # generates the retrieval eval question set
uv run python eval/evaluate_retrieval.py     # eval/retrieval_eval_results.json
uv run python eval/evaluate_llm.py           # eval/llm_eval_results.json
uv run python monitoring/build_dashboard.py  # builds the Langfuse dashboard (one-time)
```

## Usage

Open the Streamlit app and ask a question, e.g.:

- *"I became a permanent resident 8 months ago — can I open an FHSA?"*
- *"What's the difference between TFSA and RRSP contribution room?"*
- *"I just moved to Canada, can I open a TFSA right away?"*

Each answer includes:

- A direct, grounded response — never the LLM's outside knowledge, only what the retrieved context actually says
- A **Sources** panel: every retrieved chunk's URL, shown tier-first (PRIMARY sources listed before SECONDARY, ties broken by relevance) with an "as of" date when the chunk carries a real `effective_date`
- 👍 / 👎 feedback buttons, wired to a Langfuse score on that exact answer's trace

## Evaluation

### Retrieval evaluation

112 questions (56 stratified-sampled chunks × jargon-exact and
newcomer-plain-language phrasings, generated with `gpt-5.6-luna`, see
[eval/build_ground_truth.py](eval/build_ground_truth.py)), measured
via hit-rate and MRR (`eval/evaluate_retrieval.py`):

| Approach | Hit rate | MRR |
|---|---|---|
| BM25 only | 0.625 | 0.516 |
| Vector only | 0.688 | 0.566 |
| Hybrid (BM25 + vector, RRF) | 0.714 | 0.581 |
| Vector + rerank | 0.723 | 0.646 |
| Hybrid + rerank | 0.768 | 0.659 |
| **Hybrid + rerank + query rewrite** | **0.875** | **0.729** |

**Chosen approach: query rewrite → hybrid RRF → cross-encoder rerank**
(`rag/retriever.py`). Reranking and query rewriting were each added to
target a specific, measured weakness rather than by default — hybrid
alone tied vector's hit-rate on plain-language queries but with
*lower* MRR (a weak BM25 signal was dragging down top-1 ranking
there); reranking fixed that. Query rewriting was the biggest single
jump in the whole investigation, closing most of the remaining
plain-language and numeric-fact gap: plain-language hit-rate
0.571→0.804, numeric-fact 0.741→0.897. One honest tradeoff: jargon
queries get slightly *worse* with rewriting (0.964→0.946) — rewriting
an already-precise query adds a small chance of drift — but the net
gain elsewhere heavily outweighs it.

### LLM evaluation

Two models compared on the main RAG generation step
(`eval/evaluate_llm.py`), judged by `gpt-5.5` (deliberately not one of
the candidates, to avoid self-preference bias), n=30, both retrieving
identical context:

| Model | Relevant | Partly relevant | Non-relevant | Avg score |
|---|---|---|---|---|
| `gpt-5.6-terra` | 26 | 4 | 0 | 0.933 |
| `gpt-5.6-sol` | 27 | 3 | 0 | 0.950 |

**Chosen: `gpt-5.6-terra`.** `sol` scored marginally higher, but the
entire gap traced back to one hard edge-case question out of 30, not
a broad quality difference — not a robust signal at this sample size.
`terra` costs ~2.5x less on both input and output tokens; cost decides
it when performance is statistically indistinguishable.

### Best practices implemented

- **Hybrid search** — Reciprocal Rank Fusion of BM25 + vector search (`rag/hybrid_search.py`)
- **Document reranking** — cross-encoder (`BAAI/bge-reranker-base`, `rag/reranker.py`)
- **Query rewriting** — LLM rewrite before retrieval (`gpt-5.6-luna`, `rag/query_rewrite.py`)

All three were added and kept because the eval numbers above justified
them, in the order the retrieval-evaluation table shows — not applied
reflexively as a checklist.

## Monitoring

- **Feedback**: every 👍/👎 in the Streamlit app scores the exact
  Langfuse trace that produced that answer (`create_score`, not
  `score_current_trace()` — Streamlit reruns the whole script on every
  click, so the trace context has to be captured at generation time
  and carried in session state).
- **Dashboard** (`monitoring/build_dashboard.py`, built as code): 6
  charts — total LLM calls, cost over time, latency (p50) over time,
  token usage over time, calls by model, average user feedback score.

## Evaluation criteria checklist

Tracking against the LLM Zoomcamp project rubric:

- [x] Problem description
- [x] Retrieval flow (knowledge base + LLM)
- [x] Retrieval evaluation (6 approaches compared)
- [x] LLM evaluation (2 approaches compared)
- [x] Interface (Streamlit)
- [x] Ingestion pipeline (automated, Kestra)
- [x] Monitoring (feedback + Langfuse dashboard, 6 charts)
- [x] Containerization (full docker-compose)
- [x] Reproducibility (pinned deps via `uv.lock`, clear docs)
- [x] Best practices: hybrid search
- [x] Best practices: document reranking
- [x] Best practices: query rewriting
- [ ] Bonus: cloud deployment

## Project structure

```
canadian-investing-rag/
├── ingestion/     # fetch + chunk + load into the knowledge base
├── flows/         # Kestra flow definition orchestrating ingestion/
├── rag/           # retrieval + prompt construction + LLM call
├── eval/          # retrieval eval and LLM eval scripts
├── app/           # Streamlit UI
├── monitoring/    # Langfuse feedback wiring + dashboard config
├── data/          # sourcing/schema reference + fetched/processed docs (gitignored)
└── data/README.md # dataset sourcing methodology and schema — see Dataset above
```

## License

Code: MIT (see [LICENSE](LICENSE)). Source documents are Government
of Canada content used under the
[Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).
