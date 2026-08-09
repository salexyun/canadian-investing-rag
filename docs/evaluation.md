# Evaluation

> Status: skeleton — fill in as experiments are run. This file exists
> up front so reviewers can find it (per the course's documentation
> recommendations).

## Retrieval evaluation

Question set: TODO — hand-build ~50-100 Q&A pairs grounded in the
ingested documents (can bootstrap with an LLM, then review by hand).

Approaches compared:

| Approach | Hit rate | MRR |
|---|---|---|
| Keyword only (BM25 / minsearch) | TODO | TODO |
| Vector only | TODO | TODO |
| Hybrid (keyword + vector) | TODO | TODO |
| Hybrid + reranking | TODO | TODO |

**Chosen approach:** TODO — justify based on the table above.

## LLM evaluation

Approaches compared:

| Approach | Method | Score |
|---|---|---|
| Prompt v1, model X | LLM-as-judge / RAGAS | TODO |
| Prompt v2, model X | LLM-as-judge / RAGAS | TODO |
| Prompt v2, model Y | LLM-as-judge / RAGAS | TODO |

**Chosen approach:** TODO.

## Best practices implemented

- [ ] Hybrid search — evaluated above
- [ ] Document reranking — evaluated above
- [ ] Query rewriting — TODO describe approach and impact

## Monitoring

- Feedback collection: TODO describe mechanism (thumbs up/down → Postgres)
- Dashboard: TODO list the 5+ charts and what each shows
