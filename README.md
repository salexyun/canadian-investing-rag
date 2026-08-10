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
- [Dataset](#dataset)
- [Architecture](#architecture)
- [Evaluation criteria checklist](#evaluation-criteria-checklist)
- [Setup](docs/setup.md)
- [Usage](docs/usage.md)
- [Evaluation](docs/evaluation.md)

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

## Dataset

Sourced from official government and government-endorsed publications
— see [data/README.md](data/README.md) for the full, vetted list
(legitimacy, appropriateness, and tested fetchability per source), the
primary/secondary trust-tier split, and the schema each page and
chunk is tagged with. In short:

- **Primary** (7 authorities, 87 pages): CRA, CIRO, AMF, Service
  Canada/ESDC, OSC/GetSmarterAboutMoney, CIPF, CDIC
- **Secondary** (5 authorities, 6 pages, supplementary only): FP
  Canada, MoneySense, RBC, TD, Questrade

See [docs/setup.md](docs/setup.md) for how the dataset is fetched.

## Architecture

```
CRA / CIRO / AMF / ESDC / OSC / CIPF / CDIC + secondary sources
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
 Streamlit UI ──── feedback (👍/👎) + traces ──► Langfuse Cloud (dashboard, LLM-as-judge eval)
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
- [ ] Monitoring (feedback + Langfuse dashboard, 5+ charts)
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
├── monitoring/    # Langfuse feedback wiring + dashboard config
├── data/          # sample raw + processed docs
└── docs/          # setup, usage, evaluation write-ups
```

## License

Code: MIT (see [LICENSE](LICENSE)). Source documents are Government
of Canada content used under the
[Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).
