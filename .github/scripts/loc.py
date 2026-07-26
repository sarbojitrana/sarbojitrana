"""Counts lines of code contributed across every owned + contributed-to repo.

Uses a persisted cache (cache/loc_cache.json) keyed by repo + last-seen commit
SHA so re-runs only walk *new* commits instead of re-cloning full history
every time. The very first run over an unseeded repo list is the expensive
one; every run after that is fast.
"""
import json
import os
import re
import subprocess
import tempfile

import requests

USERNAME = "sarbojitrana"
# Real git-commit emails this account has used, in addition to the GitHub
# username/noreply address — commits authored with these count too.
KNOWN_EMAILS = ["sarbojitrana47c@gmail.com"]
GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("ACCESS_TOKEN")
CACHE_PATH = os.path.join(os.path.dirname(__file__), "cache", "loc_cache.json")

_EMAIL_ALTS = "|".join(re.escape(e) for e in KNOWN_EMAILS)
AUTHOR_PATTERN = re.compile(
    rf"^({re.escape(USERNAME)}|.*\+{re.escape(USERNAME)}@users\.noreply\.github\.com|{_EMAIL_ALTS})$",
    re.IGNORECASE,
)


def _headers():
    h = {"Accept": "application/vnd.github+json"}
    if GH_TOKEN:
        h["Authorization"] = f"bearer {GH_TOKEN}"
    return h


def list_repos() -> list[dict]:
    """Owned (non-fork) repos, plus contributed-to repos when a token is set."""
    repos = {}
    page = 1
    while True:
        resp = requests.get(
            f"https://api.github.com/users/{USERNAME}/repos",
            params={"per_page": 100, "page": page},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for r in batch:
            if not r["fork"]:
                repos[r["full_name"]] = r["clone_url"]
        page += 1

    if GH_TOKEN:
        query = """
        query($login: String!, $after: String) {
          user(login: $login) {
            repositoriesContributedTo(first: 100, after: $after, includeUserRepositories: false,
                contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) {
              pageInfo { hasNextPage endCursor }
              nodes { nameWithOwner url isPrivate }
            }
          }
        }
        """
        after = None
        while True:
            resp = requests.post(
                "https://api.github.com/graphql",
                json={"query": query, "variables": {"login": USERNAME, "after": after}},
                headers=_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()["data"]["user"]["repositoriesContributedTo"]
            for node in data["nodes"]:
                if not node["isPrivate"]:
                    repos[node["nameWithOwner"]] = node["url"] + ".git"
            if not data["pageInfo"]["hasNextPage"]:
                break
            after = data["pageInfo"]["endCursor"]

    return [{"full_name": k, "clone_url": v} for k, v in repos.items()]


def _run(cmd: list[str], cwd: str) -> str:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def _sum_numstat(numstat_output: str) -> tuple[int, int]:
    additions = deletions = 0
    for line in numstat_output.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        add, dele, _ = parts
        if add.isdigit():
            additions += int(add)
        if dele.isdigit():
            deletions += int(dele)
    return additions, deletions


def count_repo(clone_url: str, cached_sha: str | None) -> tuple[int, int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        auth_url = clone_url
        if GH_TOKEN and clone_url.startswith("https://"):
            auth_url = clone_url.replace("https://", f"https://x-access-token:{GH_TOKEN}@")
        _run(["git", "clone", "--quiet", "--no-checkout", auth_url, tmp], cwd=".")
        head_sha = _run(["git", "rev-parse", "HEAD"], cwd=tmp).strip()

        rev_range = f"{cached_sha}..HEAD" if cached_sha else "HEAD"
        log = _run(
            [
                "git",
                "log",
                rev_range,
                "--no-merges",
                "--pretty=format:%H%x09%ae%x09%an",
                "--numstat",
            ],
            cwd=tmp,
        )

        additions = deletions = 0
        keep = False
        for line in log.splitlines():
            if "\t" in line and line.count("\t") == 2 and not line[0].isdigit():
                _, email, name = line.split("\t")
                keep = bool(AUTHOR_PATTERN.match(email) or AUTHOR_PATTERN.match(name))
                continue
            if keep:
                parts = line.split("\t")
                if len(parts) == 3 and parts[0].isdigit():
                    additions += int(parts[0])
                if len(parts) == 3 and parts[1].isdigit():
                    deletions += int(parts[1])

        return additions, deletions, head_sha


def get_loc() -> dict:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            cache = json.load(f)

    total_add = total_del = 0
    for repo in list_repos():
        entry = cache.get(repo["full_name"], {})
        try:
            add, dele, head_sha = count_repo(repo["clone_url"], entry.get("sha"))
        except subprocess.CalledProcessError:
            continue
        entry_add = entry.get("additions", 0) + add
        entry_del = entry.get("deletions", 0) + dele
        cache[repo["full_name"]] = {
            "sha": head_sha,
            "additions": entry_add,
            "deletions": entry_del,
        }
        total_add += entry_add
        total_del += entry_del

    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)

    return {"additions": total_add, "deletions": total_del, "net": total_add - total_del}


if __name__ == "__main__":
    print(json.dumps(get_loc(), indent=2))
