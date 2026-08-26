#!/usr/bin/env python3
"""Fetch github-readme-stats cards and overlay the collage graph-paper grid."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

CARDS = (
    {
        "url": (
            "https://github-readme-stats.shion.dev/api?username=NathanPunya"
            "&show_icons=true&hide_border=false&border_color=D5CFC0&border_radius=3"
            "&bg_color=F4F0E6&title_color=2A2A2A&text_color=5A5548"
            "&icon_color=6B9B6E&ring_color=E6B84D"
        ),
        "grid": "#D8D2C3",
        "out": ASSETS / "stats.svg",
    },
    {
        "url": (
            "https://github-readme-stats.shion.dev/api?username=NathanPunya"
            "&show_icons=true&hide_border=false&border_color=4A463C&border_radius=3"
            "&bg_color=1E1C18&title_color=EDE6D8&text_color=C8C2B4"
            "&icon_color=7FB083&ring_color=E8C05A"
        ),
        "grid": "#3A372F",
        "out": ASSETS / "stats-dark.svg",
    },
)

DEFS = """<defs>
  <pattern id="collage-graph" width="20" height="20" patternUnits="userSpaceOnUse">
    <path d="M20 0H0V20" fill="none" stroke="{stroke}" stroke-width="0.55"/>
  </pattern>
  <clipPath id="collage-card">
    <rect x="0.5" y="0.5" rx="3" width="466" height="194"/>
  </clipPath>
</defs>"""

OVERLAY = (
    '<rect x="0.5" y="0.5" width="466" height="194" fill="url(#collage-graph)" '
    'opacity="0.65" clip-path="url(#collage-card)" pointer-events="none"/>'
)


def still_for_github(svg: str, rank: dict) -> str:
    """GitHub renders README SVGs statically, so fade-in keyframes would hide the stats."""
    svg = re.sub(r"\.stagger\s*\{[^}]*\}", ".stagger { opacity: 1; }", svg)
    svg = re.sub(r"animation:[^;]+;", "animation: none;", svg)
    svg, n = re.subn(
        r'<g class="rank-text">[\s\S]*?</g>',
        (
            '<g class="rank-text" transform="translate(-10, 8)">'
            f'<text x="0" y="0" dy="0.35em" text-anchor="middle" '
            f'data-testid="level-rank-icon">{rank["level"]}</text>'
            "</g>"
        ),
        svg,
        count=1,
    )
    if n != 1:
        raise RuntimeError("could not recenter rank label")
    svg = re.sub(
        r"(Rank:\s*)[A-Z][+-]?",
        rf"\g<1>{rank['level']}",
        svg,
        count=1,
    )
    dash = f"{rank['dashoffset']}"
    svg = svg.replace(
        "stroke-dasharray: 250;",
        f"stroke-dasharray: 250;\n      stroke-dashoffset: {dash};",
        1,
    )
    svg = re.sub(
        r"(@keyframes rankAnimation[\s\S]*?to \{\s*stroke-dashoffset:\s*)[0-9.]+",
        rf"\g<1>{dash}",
        svg,
        count=1,
    )
    return svg


def inject_grid(svg: str, stroke: str, rank: dict) -> str:
    svg = still_for_github(svg.strip(), rank)
    svg = re.sub(r"(<svg[^>]*>)", r"\1" + DEFS.format(stroke=stroke), svg, count=1)
    svg, n = re.subn(
        r'(<rect\s+data-testid="card-bg"[\s\S]*?/>)',
        lambda m: m.group(1) + OVERLAY,
        svg,
        count=1,
    )
    if n != 1:
        raise RuntimeError("could not find stats card background to overlay")
    return svg + "\n"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "NathanPunya-stats"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8")


def github_token() -> str:
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def parse_card_stat(svg: str, testid: str) -> int:
    match = re.search(rf'data-testid="{testid}"\s*>\s*([\d,]+)', svg)
    if not match:
        raise RuntimeError(f"could not parse {testid}")
    return int(match.group(1).replace(",", ""))


def exponential_cdf(x: float) -> float:
    return 1 - 2**-x


def log_normal_cdf(x: float) -> float:
    return x / (1 + x)


def calculate_rank(
    *,
    commits: int,
    prs: int,
    issues: int,
    reviews: int,
    stars: int,
    followers: int,
) -> dict:
    """Same formula as github-readme-stats src/calculateRank.js (last-year commits)."""
    total_weight = 2 + 3 + 1 + 1 + 4 + 1
    percentile = (
        1
        - (
            2 * exponential_cdf(commits / 250)
            + 3 * exponential_cdf(prs / 50)
            + 1 * exponential_cdf(issues / 25)
            + 1 * exponential_cdf(reviews / 2)
            + 4 * log_normal_cdf(stars / 50)
            + 1 * log_normal_cdf(followers / 10)
        )
        / total_weight
    ) * 100
    thresholds = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
    levels = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
    level = levels[next(i for i, top in enumerate(thresholds) if percentile <= top)]
    return {
        "level": level,
        "percentile": percentile,
        "dashoffset": 2 * math.pi * 40 * (percentile / 100),
    }


def github_profile_stats(token: str) -> dict:
    payload = {
        "query": """
        query ($login: String!) {
          user(login: $login) {
            followers { totalCount }
            contributionsCollection {
              totalCommitContributions
              restrictedContributionsCount
              totalPullRequestReviewContributions
            }
          }
        }
        """,
        "variables": {"login": "NathanPunya"},
    }
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "NathanPunya-stats",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        body = json.loads(res.read().decode())
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    user = body["data"]["user"]
    collection = user["contributionsCollection"]
    return {
        "commits": (
            collection["totalCommitContributions"]
            + collection["restrictedContributionsCount"]
        ),
        "reviews": collection["totalPullRequestReviewContributions"],
        "followers": user["followers"]["totalCount"],
    }


def patch_commits(svg: str, commits: int) -> str:
    value = f"{commits:,}"
    svg, n = re.subn(
        r'(data-testid="commits"\s*>)\s*[\d,]+',
        rf"\g<1>{value}",
        svg,
        count=1,
    )
    if n != 1:
        raise RuntimeError("could not patch last-year commit count")
    return re.sub(
        r"Total Commits\s+\(last year\)\s*:\s*[\d,]+",
        f"Total Commits  (last year) : {value}",
        svg,
        count=1,
    )


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    profile = github_profile_stats(github_token())
    for card in CARDS:
        raw = fetch(card["url"])
        rank = calculate_rank(
            commits=profile["commits"],
            prs=parse_card_stat(raw, "prs"),
            issues=parse_card_stat(raw, "issues"),
            reviews=profile["reviews"],
            stars=parse_card_stat(raw, "stars"),
            followers=profile["followers"],
        )
        svg = patch_commits(inject_grid(raw, card["grid"], rank), profile["commits"])
        card["out"].write_text(svg)
        print(
            f"wrote {card['out'].relative_to(ROOT)} "
            f"commits={profile['commits']} rank={rank['level']}"
        )


if __name__ == "__main__":
    main()
