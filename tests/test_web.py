"""Checks on the PalmYield web app files (no browser needed)."""
import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def test_manifest_is_installable():
    m = json.loads(read("manifest.webmanifest"))
    assert m["display"] == "standalone" and m["start_url"]
    sizes = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"} <= sizes
    for icon in m["icons"]:
        assert (WEB / icon["src"]).exists(), icon["src"]


def test_offline_cache_lists_files_that_exist():
    sw = read("sw.js")
    shell = re.search(r"const SHELL = \[(.*?)\];", sw, re.S).group(1)
    for path in re.findall(r'"([^"]+)"', shell):
        if path == "./":
            continue
        assert (WEB / path.split("?")[0]).exists(), path


def test_one_cache_version_everywhere():
    index, sw, app = read("index.html"), read("sw.js"), read("app.js")
    versions = set(re.findall(r"\?v=(\d+)", index + sw + app))
    assert len(versions) == 1, versions
    assert f'palmyield-v{versions.pop()}' in sw


def test_chat_history_can_be_managed():
    app = read("app.js")
    for name in ["deleteChats", "renameChat", "starChat", "askDelete", 'chats: () =>']:
        assert name in app, name
    assert "This can't be undone." in app  # deleting always asks first


def test_ai_never_cached_offline():
    assert "generateContent" in read("sw.js")


def test_chatbot_can_answer_soil_ph_and_rainfall():
    """The client asked about the best soil pH and rainfall vs yield; the app data must carry those results."""
    d = json.loads(read("data/app.json"))
    rel = {r["key"]: r for r in d["relations"]}
    for key in ("soil_ph", "rainfall_prior_90d_mm", "water_deficit_prior_90d_mm", "soil_moisture_pct", "flooding_days"):
        r = rel[key]
        assert r["bins"] and r["best"]["gap"] >= r["worst"]["gap"]
    assert len(d["rain_lags"]) == 4
    assert "soil_ph" in d["blocks"][0]["signals"]


def test_knowledge_base_is_loaded_and_sourced():
    index, sw, engine, kb = read("index.html"), read("sw.js"), read("engine.js"), read("knowledge.js")
    assert index.index("knowledge.js") < index.index("engine.js")  # engine uses window.PYK
    assert "knowledge.js" in sw
    assert "KNOWLEDGE" in engine and "rel_soil_ph" in engine
    for note in ("soil_ph", "rainfall", "rain_lag", "leaf_nutrients", "waterlogging"):
        assert f'id: "{note}"' in kb
    assert kb.count("sources: [") == kb.count('{ id: "')  # every note cites a source
