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

## Next

- [ ] Embed chunks and load into a vector store (Qdrant)
- [ ] Set up a keyword/BM25 index for hybrid search
- [ ] Set up Langfuse Cloud (free tier) + SDK integration — before the RAG flow is built, so tracing is in from day one
- [ ] Build a retrieval evaluation question set (~50-100 Qs, all five pillars + residency angle) — per-chunk LLM ground-truth generation (Module 4 pattern), both jargon-exact and newcomer-plain-language phrasings
- [ ] Evaluate retrieval approaches (keyword vs vector vs hybrid via RRF, +reranking) — pick the best *(rubric: Retrieval evaluation)*
- [ ] Build RAG prompt construction + LLM call, tier/content_type-aware (`rag/`) — composition-based (a RAG class taking a retriever), Langfuse-instrumented *(rubric: Retrieval flow)*
- [ ] Add query rewriting *(rubric best-practices bonus)*
- [ ] Evaluate >=2 LLM prompt/model approaches via Langfuse's LLM-as-judge evaluators — pick the best *(rubric: LLM evaluation)*
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

## Also tracked as gaps, not forgotten

- LIRA/LRSP has no clean primary (CRA) source — see [data/README.md](data/README.md#sources)
- Bank of Canada (`boc`) registered but not integrated — its Valet API is JSON, a different shape than this HTML pipeline
