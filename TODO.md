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
- [x] Evaluate retrieval approaches — BM25 vs vector vs hybrid (RRF) against the 112-question set (`eval/evaluate_retrieval.py`) *(rubric: Retrieval evaluation)*. **Winner: hybrid** — overall hit_rate=0.714/mrr=0.581 vs vector 0.688/0.566 vs bm25 0.625/0.516. Confirmed the predicted split: bm25 beats vector on jargon queries (0.929 vs 0.893 hit_rate) but collapses on plain-language ones (0.321 hit_rate, no shared vocabulary). Nuance not smoothed over: on the plain-language slice hybrid ties vector's hit-rate but has slightly *lower* MRR (0.362 vs 0.374) — fusing in a weak BM25 signal can drag down top-1 ranking even when it doesn't hurt hit-rate. Hybrid wins overall, not on every slice.

## Next

- [ ] Reranking — real motivation now, not just a rubric checkbox: plain-language MRR (hybrid 0.362) still trails jargon MRR (0.801) by a lot even with hybrid winning overall; worth testing whether a reranker narrows that gap *(rubric best-practices bonus)*
- [ ] Set up Langfuse Cloud (free tier) + SDK integration — before the RAG flow is built, so tracing is in from day one
- [ ] Build RAG prompt construction + LLM call, tier/content_type-aware (`rag/`) — composition-based (a RAG class taking a retriever), Langfuse-instrumented *(rubric: Retrieval flow)*
- [ ] Add query rewriting, `gpt-5.6-luna` *(rubric best-practices bonus)*
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
  tasks (ground-truth generation, planned query rewriting) use
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
