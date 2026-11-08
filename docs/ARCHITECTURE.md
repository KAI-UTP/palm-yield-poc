# Architecture

```
Data sources: SAP (daily, via SAP Datasphere) · database (PostgreSQL, MySQL, SQLite) · CSV or Excel file
        │   all added on the Analytics Workbench's Data sources page (core/connectors.py)
        ▼
1. Prepare  (pipeline/prepare.py)   schema check · 22 quality checks · cleaning · 20 features
        │
        ▼
2. Model    (pipeline/model.py)     5 algorithms compared on unseen blocks · drivers · forecast + 80% range
        │                           · block groups · pattern tests · what-if levers · ranked action plan
        ▼
3. Data layer (core/store.py)       Parquet + CSV/JSON results; one private folder per uploaded source
        │
        ├──► PalmYield web app (web/)        AI assistant, dashboard, early warnings, work orders;
        │      built from web/build_data.py  company sign-in, each role sees only its own pages
        ├──► Analytics Workbench (app.py)    for analysts only (password): data sources, quality,
        │                                    patterns, model checks
        ├──► AI service (core/ai.py)         Gemini or Claude, grounded on computed results only
        └──► REST API (api.py, FastAPI) ──► SAP Analytics Cloud · Power BI · other systems
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
| Access by role | Managers, agronomists, field supervisors and administrators each see only their work; the Workbench is for analysts |
| Validation by whole blocks | Scores reflect blocks the model never saw, as in real use |

## Moving to production

- **Data:** replace the CSV with a scheduled extract from the customer's SAP system (e.g. SAP Datasphere) into the same schema.
- **Storage:** move results from files to a database (e.g. PostgreSQL or SAP HANA Cloud); `core/store.py` is the only file to change.
- **Front end:** PalmYield for daily users (Next.js and TypeScript in production); the Workbench for analysts; SAP Analytics Cloud / Power BI from the REST API.
- **AI:** choose the model on accuracy, security and data residency; keep the grounding and the per-user limits.
- **Operations:** run the Docker image on the customer's cloud; schedule the pipeline after each harvest cycle; monitor with the `/health` endpoint.
