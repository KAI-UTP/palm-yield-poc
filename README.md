# Palm Yield Optimization POC

A working, AI-assisted proof of concept that takes plantation field data from basic reporting to block-level action:
**Observe → Understand → Predict → Recommend.** Built on the synthetic SOPB sample (3,200 rows: 640 blocks × 5 harvest cycles).
The data is synthetic, not real SOPB results.

## Two front ends

- **PalmYield web app (`web/`)** is the product: a management command centre (briefing, early warnings, action plan with
  work orders, block map, what-if simulator, AI assistant), built with React and ECharts. It is published on GitHub Pages
  at <https://kai-utp.github.io/palm-yield-poc/> by `.github/workflows/pages.yml` on every push.
  Run it locally: `python -m http.server 8600 --directory web`, then open <http://localhost:8600>.
  After the pipeline re-runs, refresh its data with `python web/build_data.py`.
  Option B's AI uses a Google Gemini key that each user enters in Settings; it stays in that browser.
- **Streamlit analytics app (`app.py`)** is the analyst workbench and the backup for demos.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

The sample data is bundled in `data/raw/`, and the prepared data and models are included, so the app opens straight away.
If they are missing, the app rebuilds them on first start (two to three minutes). To rebuild by hand:

```bash
python pipeline/prepare.py      # quality checks, cleaning, feature engineering
python pipeline/model.py        # five-model comparison, drivers, forecast, clustering, what-if, action plan
```

To run the whole POC on another file in the same format, use the **Run on your data** page, or
`python pipeline/prepare.py path/to/file.csv` and then `python pipeline/model.py`.

## Two proposal options in one app

A switch at the top of the sidebar shows either option live:

- **Option A · Lean, low cost:** all analytics, forecast, action plan and simulator, with built-in answers. No AI assistant, no login, data by file upload.
- **Option B · Enterprise:** everything in A, plus the AI assistant, company login, a SAP data link and an AI usage log for administrators.
  In this prototype the login (pick a demo user, no password) and the SAP link (uses the sample file) are **simulated** and say so on screen.

Set the default for a deployment with the environment variable `PALM_EDITION=A` or `B` (default B).

## Switch on the AI assistant (free)

The app works without any key: insight cards and the assistant's built-in answers come from the insight engine.
To add a real AI model for free-text questions:

1. Get a free key at [Google AI Studio](https://aistudio.google.com) ("Get API key").
2. Locally: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste the key.
   On Streamlit Cloud: **App settings → Secrets**, add `GEMINI_API_KEY = "your-key"`.
3. Never commit the key. The app limits each visitor to 20 AI questions per session, and falls back to the built-in answers
   if the free limit is reached or the service is down.

The AI layer is pluggable (`core/ai.py`): set `ANTHROPIC_API_KEY` and `AI_PROVIDER = "claude"` to use Claude instead
(add `anthropic` to `requirements.txt`). Every answer is grounded in a brief of computed results, and the model is told
not to invent numbers.

## REST API

```bash
pip install -r requirements-dev.txt
uvicorn api:app --port 8000          # interactive docs at http://localhost:8000/docs
```

| Endpoint | Returns |
|---|---|
| `GET /health` | Service status |
| `GET /summary?estate=...&price=...` | Headline numbers |
| `GET /insights` | Automated findings by topic |
| `GET /actions?estate=...&risk=high&limit=25` | Ranked action plan |
| `GET /forecast?risk=high` | Next-cycle forecast with 80% range |
| `GET /blocks/{block_id}` | One block: summary, history, first action |

## Tests, CI and Docker

```bash
pytest -q tests                       # pipeline outputs, insights, AI layer (mocked), API, every app page
docker build -t palm-yield .
docker run -p 8501:8501 -e GEMINI_API_KEY=... palm-yield
```

GitHub Actions (`.github/workflows/ci.yml`) runs the tests on every push.

## Share it online (free)

1. Put this folder in a GitHub repository (public, or private with access granted).
2. Go to [share.streamlit.io](https://share.streamlit.io), choose **Create app**, pick the repository and set the main file to `app.py`.
3. Add `GEMINI_API_KEY` under **Secrets** to switch on the AI assistant.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); the proposal deck has the same diagram.

| Layer | File | What it does |
|---|---|---|
| 1. Prepare | `pipeline/prepare.py` | 22 quality checks; unreadable values become blanks and rows without key fields are left out; cleaning; 20 engineered features |
| 2. Model | `pipeline/model.py` | Five algorithms compared for the forecast, best one used; driver importance and response curves; calibrated 80% range and risk; K-means groups; tests of the 8 embedded patterns; what-if gains; ranked action plan |
| 3. Data layer | `core/store.py` | Loads results once, filters them to a view; shared by the app, API, insights and tests |
| 4. Insights | `core/insights.py` | Plain-language findings computed from the results; the AI brief; offline answers |
| 5. AI | `core/ai.py` | Gemini (free tier) or Claude, grounded on the brief, with safe fallback |
| 6. App | `app.py` | 14 pages: Start here, AI assistant; Observe; Understand; Predict; Recommend (Action plan, Block profile, What-if simulator); Data and admin (POC summary, Run on your data, plus SAP data link and AI usage log in Option B) |
| 7. API | `api.py` | FastAPI REST endpoints for SAP Analytics Cloud, Power BI or other systems |

## Key methods

- **Annualised yield** = cycle yield × 365 ÷ harvest interval days. Raw cycle yield rises with longer rounds, so it is never compared directly.
- **Yield vs age peers** = block yield minus the median of its palm age band. This removes the age effect, which otherwise hides nutrient effects.
- **Validation**: every model is tested with 5-fold cross-validation grouped by block, so each score is on blocks the model never saw.
- **Forecast range**: split-conformal 80% range from held-out errors; checked coverage is about 80%.
- **What-if gains**: the driver model re-predicts each block with one controllable condition (or all) set to a good level. Overlapping issues are not double counted.
- **Design**: dark theme from a colour-blind-checked palette; one accent colour per chart; no dual axes; every chart has a table view.

## External references

- MPOB, *Overview of the Malaysian Oil Palm Industry 2025*: estate FFB yield Malaysia 17.77 t/ha and Sarawak 15.98 t/ha; FFB mill-gate price RM 930/t. https://bepi.mpob.gov.my/images/overview/Overview2025.pdf
- Leaf 17 critical levels (N 2.50%, P 0.15%, K 1.00%, Mg 0.24%): Ochs and Olvin (1977), as cited in Fairhurst and Mutert (1999), *Better Crops International* 13(1). Calibrate locally.
- Harvest interval of 7 to 10 days as good practice: e.g. https://hrmars.com/papers_submitted/23345/improving-palm-oil-productivity-through-harvesting-practices.pdf
