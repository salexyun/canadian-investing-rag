# Canadian Registered Accounts & Investing Assistant

A RAG application that answers questions about Canadian registered
investment accounts (RRSP, TFSA, FHSA, RESP) and related tax rules,
with a focus on the eligibility and residency details that trip up
new Canadians and permanent residents.

> ⚠️ **Not financial or tax advice.** This project is for educational
> purposes only. Answers are generated from public government sources
> and may be incomplete or out of date. Consult a licensed advisor or
> the CRA directly before making financial decisions.

Built as the capstone project for the
[DataTalks.Club LLM Zoomcamp](https://github.com/DataTalksClub/llm-zoomcamp).

## Table of contents

- [Problem description](#problem-description)
- [Dataset](#dataset)
- [Architecture](#architecture)
- [Evaluation criteria checklist](#evaluation-criteria-checklist)
- [Setup](docs/setup.md)
- [Usage](docs/usage.md)
- [Evaluation](docs/evaluation.md)

## Problem description

Canada offers several tax-advantaged accounts (RRSP, TFSA, FHSA, RESP),
each with its own contribution limits, withdrawal rules, and —
critically — eligibility rules tied to residency and immigration
status. New Canadians and permanent residents in particular struggle
to find clear, consolidated answers: generic financial advice online
is often US-centric, and government pages are scattered across
canada.ca, CRA technical folios, and the FCAC site.

This project builds a RAG assistant over official Canadian government
sources so users can ask natural-language questions (e.g. *"I landed
as a PR eight months ago, can I open an FHSA?"*) and get a grounded,
cited answer instead of having to piece it together themselves.

## Dataset

Sourced from official, Crown-copyright (Open Government Licence –
Canada) publications:

- [canada.ca](https://www.canada.ca) — RRSP, TFSA, FHSA, RESP guide pages
- [CRA](https://www.canada.ca/en/revenue-agency.html) — technical
  folios on investment income, capital gains, attribution rules
- [FCAC](https://www.canada.ca/en/financial-consumer-agency.html) —
  consumer-facing investing/banking education

See [docs/setup.md](docs/setup.md) for how the dataset is fetched and
[data/README.md](data/README.md) for details on what's included.

## Architecture

```
canada.ca / CRA / FCAC docs
        │
        ▼
 dlt ingestion pipeline (fetch → parse → chunk → load)
        │
        ▼
 knowledge base (hybrid: keyword + vector search)
        │
        ▼
 retrieval (+ query rewriting, reranking)
        │
        ▼
 prompt construction → LLM → answer with citations
        │
        ▼
 Streamlit UI ──── feedback (👍/👎) ──► Postgres ──► Grafana dashboard
```

See [docs/usage.md](docs/usage.md) for how to run each component.

## Evaluation criteria checklist

Tracking against the LLM Zoomcamp project rubric:

- [ ] Problem description
- [ ] Retrieval flow (knowledge base + LLM)
- [ ] Retrieval evaluation (multiple approaches compared)
- [ ] LLM evaluation (multiple approaches compared)
- [ ] Interface (Streamlit)
- [ ] Ingestion pipeline (automated, dlt)
- [ ] Monitoring (feedback + Grafana dashboard, 5+ charts)
- [ ] Containerization (full docker-compose)
- [ ] Reproducibility (pinned deps, clear docs)
- [ ] Best practices: hybrid search
- [ ] Best practices: document reranking
- [ ] Best practices: query rewriting
- [ ] Bonus: cloud deployment

Details on methodology live in [docs/evaluation.md](docs/evaluation.md).

## Project structure

```
canadian-investing-rag/
├── ingestion/     # dlt pipeline: fetch + chunk + load into the knowledge base
├── rag/           # retrieval + prompt construction + LLM call
├── eval/          # retrieval eval and LLM eval scripts/notebooks
├── app/           # Streamlit UI
├── monitoring/    # feedback logging + Grafana dashboard config
├── data/          # sample raw + processed docs
└── docs/          # setup, usage, evaluation write-ups
```

## License

Code: MIT (see [LICENSE](LICENSE)). Source documents are Government
of Canada content used under the
[Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).
