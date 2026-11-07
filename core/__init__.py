"""Shared core: data layer, insight engine and AI assistant, used by the app, the API and the tests."""
import sys
from pathlib import Path

_PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))
