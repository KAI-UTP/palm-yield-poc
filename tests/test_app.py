"""Every workbench page renders without errors."""
import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT


@pytest.fixture(scope="module")
def app():
    mp = pytest.MonkeyPatch()
    mp.setenv("PALM_RENDER_ALL", "1")  # test hook: render every page in one run
    mp.delenv("WORKBENCH_PASSWORD", raising=False)
    yield AppTest.from_file(str(ROOT / "app.py"), default_timeout=240).run()
    mp.undo()


def test_home_page_with_real_navigation(monkeypatch):
    """The real start page, with page links (the render-all hook skips links)."""
    monkeypatch.delenv("PALM_RENDER_ALL", raising=False)
    monkeypatch.delenv("WORKBENCH_PASSWORD", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240).run()
    assert not at.exception, [e.value for e in at.exception]


def test_all_pages_render(app):
    assert not app.exception, [e.value for e in app.exception]
