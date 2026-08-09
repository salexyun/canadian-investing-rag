# Setup

> Status: skeleton — fill in as each piece is built.

## Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local dev outside containers)
- An OpenAI API key (or swap in another provider — see `rag/`)

## 1. Clone and configure

```bash
git clone https://github.com/<your-username>/canadian-investing-rag.git
cd canadian-investing-rag
cp .env.example .env
# edit .env with your API key and any overrides
```

## 2. Fetch the dataset

Two fetch paths are needed — see [data/README.md](../data/README.md)
for the full source list and why:

```bash
python ingestion/fetch.py   # TODO: implement
# - headless-browser path (Playwright) for CRA, CIRO, AMF (bot-protected)
# - plain HTTP path for OSC/GetSmarterAboutMoney, Bank of Canada,
#   open.canada.ca, FP Canada, MoneySense, RBC, TD, Questrade
```

## 3. Run the ingestion pipeline (dlt)

```bash
python ingestion/pipeline.py   # TODO: implement — chunk + load into the knowledge base
```

## 4. Start everything

```bash
docker compose up --build
```

- App: http://localhost:8501
- Grafana: http://localhost:3000
- Qdrant: http://localhost:6333

## 5. Run evaluations

```bash
python eval/retrieval_eval.py   # TODO
python eval/llm_eval.py         # TODO
```
