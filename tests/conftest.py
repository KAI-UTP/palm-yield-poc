import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.store import load_results, make_view  # noqa: E402


@pytest.fixture(scope="session")
def results():
    return load_results()


@pytest.fixture(scope="session")
def view(results):
    return make_view(results)
