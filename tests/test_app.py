"""Every app page renders without errors, and the assistant answers offline."""
import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT


@pytest.fixture(scope="module")
def app():
    mp = pytest.MonkeyPatch()
    mp.setenv("PALM_RENDER_ALL", "1")  # test hook: render every page in one run
    mp.delenv("GEMINI_API_KEY", raising=False)
    mp.delenv("ANTHROPIC_API_KEY", raising=False)
    yield AppTest.from_file(str(ROOT / "app.py"), default_timeout=240).run()
    mp.undo()


def test_home_page_with_real_navigation(monkeypatch):
    """The real start page, with page links (the render-all hook skips links), for every role."""
    monkeypatch.delenv("PALM_RENDER_ALL", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240)
    at.session_state["edition"], at.session_state["user"] = "B", "manager"  # Option B, signed in
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    for role in at.radio(key="role").options:
        at.radio(key="role").set_value(role).run()
        assert not at.exception, (role, [e.value for e in at.exception])


def test_all_pages_render(app):
    assert not app.exception, [e.value for e in app.exception]


def test_assistant_answers_offline(app):
    app.chat_input[0].set_value("Which blocks should we fix first?").run()
    last = app.session_state["chat"][-1]
    assert last["role"] == "assistant" and "EST005-D08-B01" in last["content"]
    assert not app.exception
