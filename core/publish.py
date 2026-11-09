"""Publish pipeline results to the PalmYield web app.

PalmYield is served from the repository's web/ folder (GitHub Pages). Publishing commits a new
web/data/app.json through the GitHub API; the Pages workflow then redeploys the site in about a minute,
and open PalmYield pages offer the new data.

Setup (Streamlit secrets): GITHUB_TOKEN = a fine-grained token with "Contents: read and write"
on this repository only. Optional: GITHUB_REPO (default below) and GITHUB_BRANCH (default "main").
"""
import base64
import json
import urllib.error
import urllib.request

DEFAULT_REPO = "KAI-UTP/palm-yield-poc"
DATA_PATH = "web/data/app.json"
SITE_URL = "https://kai-utp.github.io/palm-yield-poc/"


class PublishError(RuntimeError):
    pass


def _call(method, url, token, body=None, timeout=60):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "palmyield-workbench"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 404 and method == "GET":
            return None
        detail = e.read().decode(errors="replace")[:300]
        hint = {401: "The GitHub token is not valid.", 403: "The GitHub token may not write to this repository.",
                404: "The repository or branch was not found.", 409: "Someone published at the same moment; try again.",
                422: "GitHub refused the file."}.get(e.code, "")
        raise PublishError(f"GitHub answered {e.code}. {hint} {detail}".strip()) from None
    except urllib.error.URLError as e:
        raise PublishError(f"Could not reach GitHub: {e.reason}") from None


def publish(text, token, message, repo=DEFAULT_REPO, branch="main", path=DATA_PATH):
    """Commit `text` as `path`. Returns the commit's short sha and URL."""
    if not token:
        raise PublishError("No GitHub token is set.")
    api = f"https://api.github.com/repos/{repo}/contents/{path}"
    current = _call("GET", f"{api}?ref={branch}", token)
    body = {"message": message, "branch": branch, "content": base64.b64encode(text.encode("utf-8")).decode()}
    if current and current.get("sha"):
        body["sha"] = current["sha"]
    out = _call("PUT", api, token, body)
    commit = out.get("commit", {})
    return {"sha": commit.get("sha", "")[:7], "url": commit.get("html_url", "")}
