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
- [ ] Build a retrieval evaluation question set (~50-100 Qs, all five pillars + residency angle)
- [ ] Evaluate retrieval approaches (keyword vs vector vs hybrid, +reranking) — pick the best *(rubric: Retrieval evaluation)*
- [ ] Build RAG prompt construction + LLM call, tier/content_type-aware (`rag/`) *(rubric: Retrieval flow)*
- [ ] Add query rewriting *(rubric best-practices bonus)*
- [ ] Evaluate >=2 LLM prompt/model approaches — pick the best *(rubric: LLM evaluation)*
- [ ] Build the Streamlit interface, with citations + disclaimer (`app/`) *(rubric: Interface)*
- [ ] Build monitoring — feedback capture + Grafana dashboard, 5+ charts (`monitoring/`) *(rubric: Monitoring)*
- [ ] Flesh out `docker-compose.yml` to run the whole system end-to-end *(rubric: Containerization)*
- [ ] Write up `docs/evaluation.md` and `docs/usage.md` with real results/screenshots
- [ ] (Optional) Cloud deployment *(rubric bonus)*

## Also tracked as gaps, not forgotten

- LIRA/LRSP has no clean primary (CRA) source — see [data/README.md](data/README.md#sources)
- Bank of Canada (`boc`) registered but not integrated — its Valet API is JSON, a different shape than this HTML pipeline
