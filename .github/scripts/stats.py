"""Pulls profile stats from the GitHub GraphQL + REST APIs.

Needs a token in the GH_TOKEN env var for full numbers (contributed-repo
count, total commit count across account history, private contributions).
Without a token it still returns best-effort public numbers via the
unauthenticated REST API so local runs / previews don't hard-fail.
"""
import datetime
import os

import requests

USERNAME = "sarbojitrana"
GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("ACCESS_TOKEN")
GRAPHQL_URL = "https://api.github.com/graphql"


def _graphql(query: str, variables: dict | None = None) -> dict:
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"bearer {GH_TOKEN}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


_BASE_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    repositories(ownerAffiliations: [OWNER], first: 100, isFork: false) {
      totalCount
      nodes { stargazerCount }
    }
    repositoriesContributedTo(
      first: 1
      includeUserRepositories: false
      contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]
    ) {
      totalCount
    }
  }
}
"""

_YEAR_COMMITS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""


def _total_commits(created_at: str) -> int:
    start = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)
    total = 0
    year_start = start
    while year_start < now:
        year_end = min(year_start + datetime.timedelta(days=365), now)
        data = _graphql(
            _YEAR_COMMITS_QUERY,
            {
                "login": USERNAME,
                "from": year_start.isoformat(),
                "to": year_end.isoformat(),
            },
        )
        cc = data["user"]["contributionsCollection"]
        total += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        year_start = year_end
    return total


def _rest_fallback() -> dict:
    repos = []
    page = 1
    while True:
        resp = requests.get(
            f"https://api.github.com/users/{USERNAME}/repos",
            params={"per_page": 100, "page": page, "type": "owner"},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        repos.extend(batch)
        page += 1

    user = requests.get(f"https://api.github.com/users/{USERNAME}", timeout=30).json()
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    return {
        "repos": len(repos),
        "contributed": None,
        "stars": stars,
        "commits": None,
        "followers": user.get("followers", 0),
    }


def get_stats() -> dict:
    if not GH_TOKEN:
        return _rest_fallback()

    data = _graphql(_BASE_QUERY, {"login": USERNAME})
    user = data["user"]
    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])
    commits = _total_commits(user["createdAt"])

    return {
        "repos": user["repositories"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "stars": stars,
        "commits": commits,
        "followers": user["followers"]["totalCount"],
    }


if __name__ == "__main__":
    import json

    print(json.dumps(get_stats(), indent=2))
