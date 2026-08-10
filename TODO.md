# Roadmap

Step-by-step build plan, tracked against the LLM Zoomcamp rubric (see
[README.md](README.md#evaluation-criteria-checklist)). Update this
file as steps complete — it's the durable, cross-session version of
the todo list; a live version also exists in-session via the task
tool while a session is active.

## Done

- [x] Scaffold project repo — structure, docker-compose, README, docs skeleton
- [x] Vet and tier data sources — 12 authorities, primary/secondary split, five-pillar scope
- [x] Design ingestion schema — Page + Chunk layers, Facets, enforced vocabularies (`ingestion/schema.py`)
- [x] Build fetch pipeline and fetch full corpus — 93 pages, 0 errors (`ingestion/fetch.py`)
- [x] Content-quality audit — fixed the CRA hub-page problem, dropped unfetchable sources
- [x] Build chunking pipeline — 1,052 chunks, content_type/effective_date tagging, dedup (`ingestion/pipeline.py`)
- [x] Migrate to uv for env/package management — `pyproject.toml` + `uv.lock`, replaced pip + manually-created venv
- [x] Embed chunks and load into Qdrant — `BAAI/bge-small-en-v1.5`, 1,052 points, verified against real queries (`ingestion/load_vector_store.py`)
- [x] Set up BM25 keyword index — `rank-bm25` over the same chunk text (`rag/bm25_search.py`); found concrete divergence evidence against vector search (see below)
- [x] Build retrieval evaluation question set — 112 questions from 56 stratified-sampled chunks, jargon-exact + newcomer-plain-language pairs, `gpt-5.6-luna`, $0.03 (`eval/build_ground_truth.py`)
- [x] Drop `.env.example` — vars now documented inline in `docs/setup.md`
- [x] Evaluate retrieval approaches — BM25 vs vector vs hybrid (RRF) against the 112-question set (`eval/evaluate_retrieval.py`) *(rubric: Retrieval evaluation)*. Hybrid won overall (hit_rate=0.714/mrr=0.581) but had a nuance: on the plain-language slice it tied vector's hit-rate with slightly *lower* MRR (0.362 vs 0.374) — fusing in a weak bm25 signal dragged down top-1 ranking there. Not the final answer — see reranking below, which fixed this.
- [x] Add cross-encoder reranking (`BAAI/bge-reranker-base`, `rag/reranker.py`) *(rubric best-practices bonus)* — tested on top of both vector and hybrid candidates specifically to target the plain-language MRR gap just found, not added reflexively. Winner at that point: hybrid_rerank, best on every slice tested — overall hit_rate=0.768/mrr=0.659, jargon 0.964/0.858, plain_language 0.571/0.461, numeric_fact 0.741/0.672. Superseded by query rewriting below.
- [x] Extract retrieval into shared `rag/` modules (`vector_search.py`, `hybrid_search.py`, `retriever.py`) — the production RAG flow and the eval script now use the literal same retrieval code, not two implementations that could drift. Verified: re-ran the eval after refactoring, byte-for-byte identical numbers.
- [x] Add query rewriting (`gpt-5.6-luna`, `rag/query_rewrite.py`) *(rubric best-practices bonus)* — tested against the ground-truth set, not assumed. **Biggest single jump in the whole retrieval investigation**: new winner `hybrid_rerank_rewrite`, overall hit_rate=0.875/mrr=0.729. Plain-language slice (the gap chased since the first retrieval eval): hit_rate 0.571→**0.804**, mrr 0.461→**0.651**. numeric_fact: 0.741→0.897 / 0.672→0.805. One honest tradeoff: jargon queries are slightly *worse* with rewriting (hit_rate 0.964→0.946, mrr 0.858→0.807) — rewriting an already-precise query adds a small chance of drift. Net gain heavily outweighs it. **This (query-rewrite → hybrid RRF → rerank) is the final retriever, `rag/retriever.py`.**
- [x] Build the RAG class (`rag/rag.py`) *(rubric: Retrieval flow)* — composition-based (retriever injected), prompt construction is tier-aware (PRIMARY preferred, SECONDARY flagged explicitly) and content_type-aware (effective_date surfaced as "as of" when present). Verified with real questions, not just "it ran": both test answers correct, well-grounded, appropriately hedged, correctly distinguished CIPF/CIRO/CDIC's different roles, real working citation URLs. Model: `gpt-5.6-terra` as a placeholder — LLM evaluation (below) decides terra vs sol for real.

## Next

- [ ] Set up Langfuse Cloud (free tier) + SDK integration — instrumenting the now-working RAG flow, not building blind
- [ ] Evaluate >=2 LLM approaches for main RAG generation (`gpt-5.6-terra` vs `gpt-5.6-sol`) via Langfuse's LLM-as-judge (`gpt-5.6-terra` as judge) — pick the best *(rubric: LLM evaluation)*
- [ ] Build the Streamlit interface, with citations + disclaimer (`app/`) *(rubric: Interface)*
- [ ] Wire user feedback (thumbs up/down) to Langfuse's scores API + confirm/extend its dashboard to 5+ charts (`monitoring/`) *(rubric: Monitoring)*
- [ ] Flesh out `docker-compose.yml` to run end-to-end — app + Qdrant only; no self-hosted Postgres/Grafana, Langfuse Cloud is external *(rubric: Containerization)*
- [ ] Write up `docs/evaluation.md` and `docs/usage.md` with real results/screenshots
- [ ] (Optional) Cloud deployment *(rubric bonus)*

## Decisions made along the way (and why)

- **Monitoring/eval: Langfuse Cloud, not Grafana+Postgres (the course's approach) or self-hosted Langfuse.**
  Self-hosted Langfuse is a 6-service stack (Postgres + ClickHouse + Redis +
  MinIO + web + worker, ~4 cores/16GB recommended) — too heavy for this
  project's traffic scale alongside Qdrant + our own app. Cloud free tier
  gets the same SDK/tracing/eval/dashboard features without managing any
  database ourselves — same reasoning as calling the OpenAI API instead of
  self-hosting an LLM.
- **Not Arize Phoenix** — also a strong fit (retrieval-eval templates,
  embedding visualization), but chosen against in favour of learning
  Langfuse specifically; a deliberate choice, not an oversight.
- **`rag/`'s RAG class is composition-based** (a retriever passed into one
  class), not the course's 3-level `RAGBase`/`RAGVector`/`RAGPgVector`
  subclass hierarchy — we don't swap retrieval backends at runtime in
  production, just compare 3 approaches once and pick a winner; less
  structure is genuinely enough here.
- **Different LLM per task, not one model everywhere.** Checked current
  OpenAI pricing directly against the API (`client.models.list()`), not
  an aggregator estimate — `gpt-5.6` (luna/terra/sol) is the current
  generation, one past the coursework's `gpt-5.4-mini`. Bulk/simple
  tasks (ground-truth generation, query rewriting) use
  `gpt-5.6-luna` (cheapest current tier, $0.20/$1.20 per 1M tokens) —
  no reasoning depth needed for either. Main RAG generation and the
  LLM-judge deliberately *don't* have a model picked yet — task
  "Evaluate >=2 LLM approaches" is where that gets decided empirically
  (comparing `gpt-5.6-terra` vs `gpt-5.6-sol`), not guessed ahead of it.
- **BM25 vs vector: real divergence found, not just the theoretical
  case.** Same 3 test queries run against both: on a jargon-exact query
  both landed the correct chunk top-1; on a fully-paraphrased query
  ("what happens to my investments if I leave Canada" — zero shared
  vocabulary with "non-resident"), BM25's top 3 were all irrelevant
  while vector search's top 3 were all correct. Confirms hybrid is
  worth the eval effort, not just plausible in theory.

## Also tracked as gaps, not forgotten

- LIRA/LRSP has no clean primary (CRA) source — see [data/README.md](data/README.md#sources)
- Bank of Canada (`boc`) registered but not integrated — its Valet API is JSON, a different shape than this HTML pipeline
- Ingestion pipeline is fully automated but still plain Python scripts, not wrapped in a named orchestration tool (Kestra/dlt/Airflow/Prefect) — the rubric's own wording draws the 1-vs-2-point line at the tool, not the automation level, so this is genuinely ambiguous scoring risk, not just polish. Wrapping fetch+chunk+load as dlt resources would close it.
