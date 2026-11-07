"""AI assistant: answers questions about the results, grounded in the computed facts only.

Pluggable: Google Gemini (free tier) by default, or Anthropic Claude. With no key, or when the
service fails or hits its free limit, the app falls back to the offline answers in insights.py.

Keys are read from Streamlit secrets or environment variables, never from code:
    GEMINI_API_KEY       Google AI Studio key (free tier)
    GEMINI_MODEL         optional; by default Google's current Flash-Lite, then Flash, aliases are tried
    ANTHROPIC_API_KEY    optional, to use Claude instead
    CLAUDE_MODEL         optional, default "claude-opus-5-5"
    AI_PROVIDER          optional, "gemini", "claude" or "none" to force a choice
"""
import os

import requests

SYSTEM = """You are the analytics assistant inside a palm oil yield optimisation proof of concept.
Answer the user's question using ONLY the facts in the RESULTS brief below. Rules:
- Never invent numbers, blocks, estates or causes. If the brief does not contain the answer, say so plainly and suggest which app page to check.
- Quote numbers exactly as in the brief, with units (t/ha/yr, t FFB a year, RM).
- Keep answers short: 2 to 6 sentences or a few bullets. Plain business English for plantation managers.
- When recommending actions, name the block or estate and the first action from the brief.
- The data is synthetic sample data; findings show association, not proven cause, and gains are before costs. Mention this when it matters.
- App pages you can point to: Overview, Data quality, Yield drivers, Pattern check, Agronomy, Block groups, Forecast and risk, Action plan, What-if simulator, Block profile.

RESULTS brief:
"""

# Google's aliases for the current fast models first (Flash-Lite is quickest and has the highest free limits)
GEMINI_FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash"]


class AIError(Exception):
    """The AI service could not answer (no key, limit reached, network, or refusal)."""


def _cfg(secrets, name, default=None):
    try:
        if secrets is not None and name in secrets:
            return str(secrets[name])
    except Exception:  # noqa: BLE001  (st.secrets raises when no secrets file exists)
        pass
    return os.environ.get(name, default)


def _reason(res):
    """Google's short error reason (e.g. API_KEY_INVALID), never the key itself."""
    try:
        err = res.json().get("error", {})
        details = [d.get("reason") for d in err.get("details", []) if d.get("reason")]
        return f" ({details[0] if details else err.get('status', '')})" if (details or err.get("status")) else ""
    except Exception:  # noqa: BLE001
        return ""


class GeminiProvider:
    name = "Google Gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, key, model=None, session=None):
        self.key, self.http = key, session or requests
        self.models = [model] if model else list(GEMINI_FALLBACK_MODELS)
        self.model = self.models[0]

    def _post(self, model, body):
        return self.http.post(self.URL.format(model=model), json=body, timeout=(10, 45),
                              headers={"x-goog-api-key": self.key, "Content-Type": "application/json"})

    def ask(self, question, context, history=()):
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in history]
        contents.append({"role": "user", "parts": [{"text": question}]})
        # Room for the model's own reasoning plus the answer
        plain = {"system_instruction": {"parts": [{"text": SYSTEM + context}]}, "contents": contents,
                 "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096}}
        # Explaining computed results needs little reasoning; brief thinking keeps answers fast
        fast = {**plain, "generationConfig": {**plain["generationConfig"], "thinkingConfig": {"thinkingLevel": "low"}}}
        last = None
        for model in self.models:  # next model if one is retired (404) or too slow
            res = None
            for body in (fast, plain):  # some models reject the thinking setting (400): retry without it
                try:
                    res = self._post(model, body)
                except requests.Timeout:
                    res, last = None, f"{model} took too long"
                    break
                except requests.RequestException as e:
                    raise AIError(f"Could not reach Gemini: {e.__class__.__name__}") from e
                if not (res.status_code == 400 and body is fast):
                    break
            if res is None:
                continue
            if res.status_code == 404:
                last = f"model {model} not found"
                continue
            if res.status_code == 429:
                raise AIError("The free Gemini limit is reached for now. Try again in a minute.")
            if res.status_code >= 300:
                raise AIError(f"Gemini returned error {res.status_code}{_reason(res)}. "
                              + ("Check that the API key is valid and has access to the Gemini API." if res.status_code in (400, 401, 403) else ""))
            data = res.json()
            cands = data.get("candidates") or []
            text = "".join(p.get("text", "") for c in cands[:1] for p in c.get("content", {}).get("parts", []))
            if not text.strip():
                raise AIError("Gemini returned no answer (it may have been blocked by its safety filter).")
            self.model = model
            return text.strip()
        raise AIError(f"Gemini did not answer ({last}). Try again, or set GEMINI_MODEL to a current model name.")


class ClaudeProvider:
    name = "Anthropic Claude"

    def __init__(self, key, model=None, client=None):
        self.model = model or "claude-opus-5-5"
        if client is None:
            try:
                import anthropic
            except ImportError as e:
                raise AIError("The anthropic package is not installed.") from e
            client = anthropic.Anthropic(api_key=key)
        self.client = client

    def ask(self, question, context, history=()):
        messages = [{"role": m["role"], "content": m["content"]} for m in history] + [{"role": "user", "content": question}]
        try:
            res = self.client.beta.messages.create(
                model=self.model, max_tokens=2048, system=SYSTEM + context, messages=messages,
                output_config={"effort": "low"},  # short, factual answers
                betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        except Exception as e:  # noqa: BLE001
            raise AIError(f"Claude could not answer: {e.__class__.__name__}") from e
        if res.stop_reason == "refusal":
            raise AIError("Claude declined this question.")
        text = "".join(b.text for b in res.content if b.type == "text").strip()
        if not text:
            raise AIError("Claude returned no answer.")
        return text


def get_provider(secrets=None):
    """The configured AI provider, or None when no key is set (the app then answers offline)."""
    choice = (_cfg(secrets, "AI_PROVIDER") or "").lower()
    if choice == "none":
        return None
    gkey, ckey = _cfg(secrets, "GEMINI_API_KEY"), _cfg(secrets, "ANTHROPIC_API_KEY")
    try:
        if ckey and (choice == "claude" or not gkey):
            return ClaudeProvider(ckey, _cfg(secrets, "CLAUDE_MODEL"))
        if gkey and choice in ("", "gemini"):
            return GeminiProvider(gkey, _cfg(secrets, "GEMINI_MODEL"))
    except AIError:
        return None
    return None
