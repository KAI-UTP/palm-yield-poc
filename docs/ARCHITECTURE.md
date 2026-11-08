# Architecture

```
Source data (CSV export, or SAP / BI extract)
        │
        ▼
1. Prepare  (pipeline/prepare.py)   schema check · 22 quality checks · cleaning · 20 features
        │
        ▼
2. Model    (pipeline/model.py)     5 algorithms compared on unseen blocks · drivers · forecast + 80% range
        │                           · block groups · pattern tests · what-if levers · ranked action plan
        ▼
3. Data layer (core/store.py)       Parquet + CSV/JSON results; one private folder per uploaded file
        │
        ├──► Insight engine (core/insights.py) ──► AI assistant (core/ai.py: Gemini or Claude, grounded)
        │                     │                                   │
        ▼                     ▼                                   ▼
   Streamlit app (app.py, 14 pages)  ◄─────────────────────────────┘
        │
   REST API (api.py, FastAPI) ──► SAP Analytics Cloud · Power BI · other systems
```

## Design decisions

| Decision | Why |
|---|---|
| One pipeline, run as scripts | The same steps run on the sample, an uploaded file, or a scheduled job on real data |
| Shared data layer | The app, API, insights and tests read the same results, so numbers always agree |
| Insights computed, not generated | Every finding comes from the data; the AI only explains computed facts |
| AI grounded on a results brief | The model sees a compact brief of computed results and is told not to invent numbers |
| Pluggable AI with fallback | Free Gemini for the POC; Claude or another model in production; offline answers if the service fails |
| Per-session private uploads | A visitor's data never mixes with another visitor's |
| Validation by whole blocks | Scores reflect blocks the model never saw, as in real use |

## Moving to production

- **Data:** replace the CSV with a scheduled extract from the customer's SAP system (e.g. SAP Datasphere) into the same schema.
- **Storage:** move results from files to a database (e.g. PostgreSQL or SAP HANA Cloud); `core/store.py` is the only file to change.
- **Front end:** keep Streamlit, or feed SAP Analytics Cloud / Power BI from the REST API.
- **AI:** choose the model on accuracy, security and data residency; keep the grounding and the per-user limits.
- **Operations:** run the Docker image on the customer's cloud; schedule the pipeline after each harvest cycle; monitor with the `/health` endpoint.
