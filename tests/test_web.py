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


def test_every_action_has_a_malay_translation():
    data = json.loads(read("data/app.json"))
    app = read("app.js")
    for action in {b["action"] for b in data["blocks"]}:
        assert json.dumps(action) + ":" in app, action


def test_ai_never_cached_offline():
    assert "generateContent" in read("sw.js")
