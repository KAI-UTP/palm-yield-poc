"""AI layer: provider choice, request shape and safe failure, with the web service mocked."""
import pytest

from core import ai


class Resp:
    def __init__(self, code, payload=None):
        self.status_code, self.payload = code, payload or {}

    def json(self):
        return self.payload


class FakeHTTP:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return self.responses.pop(0)


def ok():
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": "Answer."}]}}]})


def test_no_key_means_offline(monkeypatch):
    for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "AI_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    assert ai.get_provider({}) is None
    assert ai.get_provider({"GEMINI_API_KEY": "k", "AI_PROVIDER": "none"}) is None


def test_gemini_request_is_grounded():
    p = ai.get_provider({"GEMINI_API_KEY": "k"})
    assert isinstance(p, ai.GeminiProvider)
    p.http = FakeHTTP(ok())
    assert p.ask("Q?", "FACTS", [{"role": "assistant", "content": "hi"}]) == "Answer."
    url, kw = p.http.calls[0]
    assert kw["headers"]["x-goog-api-key"] == "k" and "key=" not in url  # key goes in a header, never the URL
    assert kw["json"]["system_instruction"]["parts"][0]["text"].endswith("FACTS")
    assert [c["role"] for c in kw["json"]["contents"]] == ["model", "user"]


def test_gemini_tries_next_model_when_one_is_retired():
    p = ai.GeminiProvider("k", session=FakeHTTP(Resp(404), ok()))
    assert p.ask("Q?", "") == "Answer." and p.model == ai.GEMINI_FALLBACK_MODELS[1]


@pytest.mark.parametrize("code", [400, 403, 429, 500])
def test_gemini_errors_raise_aierror(code):
    with pytest.raises(ai.AIError):  # a 400 is retried once without the thinking setting
        ai.GeminiProvider("k", session=FakeHTTP(Resp(code), Resp(code))).ask("Q?", "")


def test_asks_for_brief_thinking_and_retries_without_it():
    http = FakeHTTP(Resp(400), ok())
    assert ai.GeminiProvider("k", session=http).ask("Q?", "") == "Answer."
    first, second = (kw["json"]["generationConfig"] for _, kw in http.calls)
    assert first["thinkingConfig"] == {"thinkingLevel": "low"} and "thinkingConfig" not in second


def test_slow_model_falls_through_to_next():
    class SlowThenOK(FakeHTTP):
        def post(self, url, **kw):
            if not self.calls:
                self.calls.append((url, kw))
                raise ai.requests.Timeout()
            return super().post(url, **kw)

    p = ai.GeminiProvider("k", session=SlowThenOK(ok()))
    assert p.ask("Q?", "") == "Answer." and p.model == ai.GEMINI_FALLBACK_MODELS[1]


def test_empty_answer_raises():
    with pytest.raises(ai.AIError):
        ai.GeminiProvider("k", session=FakeHTTP(Resp(200, {"candidates": []}))).ask("Q?", "")


def test_claude_provider_with_fake_client():
    class Block:
        type, text = "text", "Claude answer."

    class Msg:
        stop_reason, content = "end_turn", [Block()]

    class Messages:
        @staticmethod
        def create(**kw):
            assert kw["system"].endswith("FACTS") and kw["fallbacks"] == "default"
            return Msg()

    class Client:
        class beta:
            messages = Messages

    assert ai.ClaudeProvider("k", client=Client()).ask("Q?", "FACTS") == "Claude answer."
