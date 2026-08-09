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

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # needed for the CRA/CIRO/AMF fetch path — see below
```

## 2. Fetch the dataset

`ingestion/fetch.py` pulls every page listed in
[data/README.md](../data/README.md) and writes raw HTML to
`data/raw/<tier>/<id>.html` plus a `data/raw/manifest.jsonl` index
(one JSON record per page — url, tier, license, fetch timestamp, the
page's self-reported last-modified date where available).

It uses two fetch paths, chosen per source (see data/README.md for
why): a headless-browser path (Playwright) for CRA, CIRO, and AMF,
which block plain HTTP clients even though their `robots.txt` allows
crawling; and a plain, self-identifying HTTP client for everything
else (OSC/GetSmarterAboutMoney, FP Canada, MoneySense, RBC, TD,
Questrade).

```bash
python ingestion/fetch.py                       # fetch everything
python ingestion/fetch.py --tier primary         # just the primary tier
python ingestion/fetch.py --only cra_tfsa cra_fhsa   # just specific sources
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
