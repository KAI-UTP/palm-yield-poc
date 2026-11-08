"""The two proposal options, run from one code base.

Option A (Lean, low cost): all analytics, forecast, action plan and simulator, with built-in insight
answers; no AI assistant, no login, data by file upload.
Option B (Enterprise): everything in A, plus the AI assistant, company login, a SAP data link and an
AI usage log. In this prototype the login and the SAP link are simulated and say so on screen.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

EDITIONS = {
    "A": {"name": "Option A · Lean", "ai": False, "login": False, "sap": False},
    "B": {"name": "Option B · Enterprise", "ai": True, "login": True, "sap": True},
}

# Demo identities for the simulated company login (no passwords: the real system uses the client's
# single sign-on, such as Microsoft Entra ID or SAP Identity Authentication)
DEMO_USERS = {
    "manager": ("Demo estate manager", "Estate manager"),
    "agronomist": ("Demo agronomist", "Agronomist"),
    "admin": ("Demo administrator", "Administrator"),
}


def edition(code):
    return EDITIONS.get(str(code or "").upper(), EDITIONS["B"])


def log_ai_use(path, user, question, provider, ok):
    """Append one AI question to the usage log (who, when, which model, answered or not)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "user": user, "question": question[:300],
           "provider": provider, "answered": bool(ok)}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def read_log(path, last=200):
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-last:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out[::-1]
