#!/usr/bin/env python3
"""
Generate self-hosted GitHub stat cards as animated SVG.

Why this exists: the shared github-readme-stats.vercel.app instance is
rate-limited and times out, so the `stats` and `top-langs` cards on the
profile intermittently fail to render. This script bakes the same numbers
into local SVGs that match the drawing-sheet design system in ./assets,
so they render every time with zero third-party runtime dependency.

Refreshed on a schedule by .github/workflows/refresh-stats.yml.

Usage:
    GH_TOKEN=<token> python generate_stats.py [--out assets]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

USERNAME = "Osamaali313"

# --- design system (mirrors ./assets/*.svg) --------------------------------
BG = "#0B0E14"
PANEL = "#11151F"
STROKE = "#232A3A"
INDIGO = "#6E8BFA"
GREEN = "#46C28E"
AMBER = "#E8A33D"
INK = "#F3F5FA"
MUTED = "#8B93A7"
FAINT = "#5A6379"
MONO = "'JetBrains Mono','Fira Code',Consolas,monospace"
SANS = "Segoe UI,Inter,Helvetica,Arial,sans-serif"

# Languages that swamp the chart without saying much about what is built.
LANG_EXCLUDE = {"Jupyter Notebook"}
TOP_N_LANGS = 6

GRAPHQL = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
    }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(
      contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]
    ) { totalCount }
  }
}
"""


def fetch(token: str) -> dict:
    body = json.dumps({"query": GRAPHQL, "variables": {"login": USERNAME}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{USERNAME}-profile-stats",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def aggregate(user: dict) -> dict:
    repos = user["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)

    lang_bytes: dict[str, float] = {}
    lang_color: dict[str, str] = {}
    for r in repos:
        for edge in r["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in LANG_EXCLUDE:
                continue
            lang_bytes[name] = lang_bytes.get(name, 0) + edge["size"]
            lang_color[name] = edge["node"]["color"] or MUTED

    ranked = sorted(lang_bytes.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N_LANGS]
    total = sum(v for _, v in ranked) or 1
    langs = [
        {"name": n, "pct": v / total * 100, "color": lang_color[n]}
        for n, v in ranked
    ]

    return {
        "stars": stars,
        "commits": user["contributionsCollection"]["totalCommitContributions"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "contrib": user["repositoriesContributedTo"]["totalCount"],
        "langs": langs,
    }


def fmt(n: int) -> str:
    return f"{n:,}"


# --- SVG builders ----------------------------------------------------------
def stats_svg(d: dict) -> str:
    W, H = 495, 195
    rows = [
        ("★", "Total Stars Earned", fmt(d["stars"]), AMBER),
        ("↑", "Commits (last year)", fmt(d["commits"]), GREEN),
        ("⇄", "Total Pull Requests", fmt(d["prs"]), INDIGO),
        ("◎", "Total Issues", fmt(d["issues"]), AMBER),
        ("☷", "Contributed to (last yr)", fmt(d["contrib"]), GREEN),
    ]
    parts = [
        f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="GitHub statistics for {USERNAME}">',
        "<defs>",
        f'<linearGradient id="sAcc" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{INDIGO}"/>'
        f'<stop offset="100%" stop-color="{GREEN}"/></linearGradient>',
        f'<linearGradient id="sShimmer" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="{INDIGO}" stop-opacity="0"/>'
        f'<stop offset="50%" stop-color="{INDIGO}" stop-opacity=".9"/>'
        f'<stop offset="100%" stop-color="{INDIGO}" stop-opacity="0"/></linearGradient>',
        f'<clipPath id="sFrame"><rect width="{W}" height="{H}" rx="12"/></clipPath>',
        "</defs>",
        f'<g clip-path="url(#sFrame)" font-family="{MONO}">',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        f'<rect x="0" y="0" width="6" height="{H}" fill="url(#sAcc)"/>',
        # header
        f'<text x="30" y="42" font-size="19" font-weight="700" letter-spacing="1.5" '
        f'fill="{INK}" font-family="{SANS}">GitHub Stats</text>',
        f'<text x="30" y="62" font-size="11" letter-spacing="2" fill="{FAINT}">'
        f'@{USERNAME.upper()} · SELF-HOSTED</text>',
        # shimmer rule under header
        f'<line x1="30" y1="76" x2="465" y2="76" stroke="{STROKE}" stroke-width="1.5"/>',
        f'<rect x="30" y="75" width="120" height="2.5" fill="url(#sShimmer)">'
        f'<animate attributeName="x" values="30;345" dur="4.5s" repeatCount="indefinite"/></rect>',
    ]
    # Rows are always visible (robust for non-SMIL renderers); the icon
    # gets a gentle looping pulse for life, matching the header shimmer.
    y = 104
    for i, (icon, label, value, color) in enumerate(rows):
        begin = f"{i * 0.4:.2f}s"
        parts += [
            "<g>",
            f'<text x="30" y="{y}" font-size="14" fill="{color}">{icon}'
            f'<animate attributeName="opacity" values="1;0.35;1" dur="3s" '
            f'begin="{begin}" repeatCount="indefinite"/></text>',
            f'<text x="52" y="{y}" font-size="13.5" fill="{MUTED}">{label}</text>',
            f'<text x="465" y="{y}" font-size="14" font-weight="700" '
            f'fill="{INK}" text-anchor="end">{value}</text>',
            "</g>",
        ]
        y += 20
    parts += [
        f'<rect x="0" y="0" width="{W}" height="{H}" rx="12" stroke="{STROKE}" fill="none"/>',
        "</g></svg>",
    ]
    return "\n".join(parts)


def top_langs_svg(d: dict) -> str:
    W = 495
    langs = d["langs"]
    H = 92 + len(langs) * 26
    bar_y = 74
    bar_x = 30
    bar_w = W - 60
    parts = [
        f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Most used languages by {USERNAME}">',
        "<defs>",
        f'<linearGradient id="lAcc" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{GREEN}"/>'
        f'<stop offset="100%" stop-color="{INDIGO}"/></linearGradient>',
        f'<clipPath id="lFrame"><rect width="{W}" height="{H}" rx="12"/></clipPath>',
        f'<clipPath id="lBar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" '
        f'height="11" rx="5.5"/></clipPath>',
        "</defs>",
        f'<g clip-path="url(#lFrame)" font-family="{MONO}">',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        f'<rect x="0" y="0" width="6" height="{H}" fill="url(#lAcc)"/>',
        f'<text x="30" y="42" font-size="19" font-weight="700" letter-spacing="1.5" '
        f'fill="{INK}" font-family="{SANS}">Most Used Languages</text>',
        f'<text x="30" y="62" font-size="11" letter-spacing="2" fill="{FAINT}">'
        f'BY CODE SIZE · EXCL. NOTEBOOKS</text>',
        # stacked bar track
        f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="11" rx="5.5" fill="{PANEL}"/>',
        # shimmer gradient reused for the bar sweep
        f'<linearGradient id="lShimmer" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="#FFFFFF" stop-opacity="0"/>'
        f'<stop offset="50%" stop-color="#FFFFFF" stop-opacity=".35"/>'
        f'<stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>',
        f'<g clip-path="url(#lBar)">',
    ]
    # Segments rendered at full width (visible without SMIL); a light sweep
    # runs across the whole bar on a loop for motion.
    offset = 0.0
    for lang in langs:
        seg_w = bar_w * lang["pct"] / 100
        parts.append(
            f'<rect x="{bar_x + offset:.2f}" y="{bar_y}" width="{seg_w:.2f}" '
            f'height="11" fill="{lang["color"]}"/>'
        )
        offset += seg_w
    parts.append(
        f'<rect x="{bar_x}" y="{bar_y}" width="90" height="11" fill="url(#lShimmer)">'
        f'<animate attributeName="x" values="{bar_x};{bar_x + bar_w}" dur="4.5s" '
        f'repeatCount="indefinite"/></rect>'
    )
    parts.append("</g>")
    # legend (two columns)
    col_x = [30, 265]
    row_y = bar_y + 34
    per_col = (len(langs) + 1) // 2
    for i, lang in enumerate(langs):
        cx = col_x[i // per_col]
        cy = row_y + (i % per_col) * 26
        begin = f"{i * 0.4:.2f}s"
        parts += [
            "<g>",
            f'<circle cx="{cx + 6}" cy="{cy - 4}" r="6" fill="{lang["color"]}">'
            f'<animate attributeName="opacity" values="1;0.4;1" dur="3s" '
            f'begin="{begin}" repeatCount="indefinite"/></circle>',
            f'<text x="{cx + 20}" y="{cy}" font-size="13" fill="{MUTED}">{lang["name"]}</text>',
            f'<text x="{cx + 195}" y="{cy}" font-size="13" font-weight="700" '
            f'fill="{INK}" text-anchor="end">{lang["pct"]:.1f}%</text>',
            "</g>",
        ]
    parts += [
        f'<rect x="0" y="0" width="{W}" height="{H}" rx="12" stroke="{STROKE}" fill="none"/>',
        "</g></svg>",
    ]
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="assets")
    args = ap.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("error: set GH_TOKEN or GITHUB_TOKEN", file=sys.stderr)
        return 1

    data = aggregate(fetch(token))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stats.svg").write_text(stats_svg(data), encoding="utf-8")
    (out / "top-langs.svg").write_text(top_langs_svg(data), encoding="utf-8")
    print("wrote", out / "stats.svg", "and", out / "top-langs.svg")
    print("data:", json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
