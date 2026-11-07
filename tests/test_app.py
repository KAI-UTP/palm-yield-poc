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


def test_all_pages_render(app):
    assert not app.exception, [e.value for e in app.exception]


def test_assistant_answers_offline(app):
    app.chat_input[0].set_value("Which blocks should we fix first?").run()
    last = app.session_state["chat"][-1]
    assert last["role"] == "assistant" and "EST005-D08-B01" in last["content"]
    assert not app.exception
