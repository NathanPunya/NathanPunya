#!/usr/bin/env python3
"""Fetch github-readme-stats cards and overlay the collage graph-paper grid."""

from __future__ import annotations

import json
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


def still_for_github(svg: str) -> str:
    """GitHub renders README SVGs statically, so fade-in keyframes would hide the stats."""
    svg = re.sub(r"\.stagger\s*\{[^}]*\}", ".stagger { opacity: 1; }", svg)
    svg = re.sub(r"animation:[^;]+;", "animation: none;", svg)
    rank = re.search(
        r'data-testid="level-rank-icon">\s*([^<]+)\s*</text>',
        svg,
    )
    if not rank:
        raise RuntimeError("could not find rank label")
    label = rank.group(1).strip()
    svg, n = re.subn(
        r'<g class="rank-text">[\s\S]*?</g>',
        (
            '<g class="rank-text" transform="translate(-10, 8)">'
            f'<text x="0" y="0" dy="0.35em" text-anchor="middle" '
            f'data-testid="level-rank-icon">{label}</text>'
            "</g>"
        ),
        svg,
        count=1,
    )
    if n != 1:
        raise RuntimeError("could not recenter rank label")
    dash = re.search(
        r"@keyframes rankAnimation.*?to \{\s*stroke-dashoffset:\s*([0-9.]+);",
        svg,
        re.S,
    )
    if dash:
        svg = svg.replace(
            "stroke-dasharray: 250;",
            f"stroke-dasharray: 250;\n      stroke-dashoffset: {dash.group(1)};",
            1,
        )
    return svg


def inject_grid(svg: str, stroke: str) -> str:
    svg = still_for_github(svg.strip())
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


def commits_including_private(token: str) -> int:
    payload = {
        "query": """
        query ($login: String!) {
          user(login: $login) {
            contributionsCollection {
              totalCommitContributions
              restrictedContributionsCount
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
    collection = body["data"]["user"]["contributionsCollection"]
    return (
        collection["totalCommitContributions"]
        + collection["restrictedContributionsCount"]
    )


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
    commits = commits_including_private(github_token())
    for card in CARDS:
        svg = patch_commits(inject_grid(fetch(card["url"]), card["grid"]), commits)
        card["out"].write_text(svg)
        print(f"wrote {card['out'].relative_to(ROOT)} commits={commits}")


if __name__ == "__main__":
    main()
