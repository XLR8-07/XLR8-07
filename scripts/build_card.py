"""Render the neofetch-style profile card as card/light.svg and card/dark.svg.

Static text comes from card/profile.toml, the portrait from card/avatar.json and
the numbers from the GitHub GraphQL API. Only totals are written, never repo names.

    GH_TOKEN=... python3 scripts/build_card.py
"""

import colorsys
import json
import os
import sys
import tomllib
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "card"

FONT_SIZE = 15
CHAR_W = FONT_SIZE * 0.62  # widest common monospace fallback (Menlo, DejaVu)
LINE_H = 20
PAD = 24
GAP = 3  # columns between portrait and text
ASCII_FONT = 9  # the portrait uses a smaller font so it can hold more detail
ASCII_LINE = 10.35
KEY_W = 17  # key plus dot leader, in characters

THEMES = {
    "light": {
        "bg": "#f6f8fa", "border": "#d0d7de", "text": "#24292f", "max_lightness": 0.6,
        "host": "#0969da", "key": "#953800", "value": "#0a3069", "dim": "#8c959f",
    },
    "dark": {
        "bg": "#161b22", "border": "#30363d", "text": "#c9d1d9", "min_lightness": 0.42,
        "host": "#58a6ff", "key": "#ffa657", "value": "#a5d6ff", "dim": "#6e7681",
    },
}

REPOS_QUERY = """
query($cursor: String) {
  viewer {
    login
    createdAt
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, after: $cursor) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 20) { edges { size node { name } } }
      }
    }
  }
}
"""


def portrait_colour(hex_, theme):
    """Keep the photo's colours but make sure they stand out from the card background."""
    r, g, b = (int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    s *= min(1, l / 0.3) ** 2  # near-black pixels have noisy hues; render them as grey
    l = max(l, theme.get("min_lightness", 0))
    l = min(l, theme.get("max_lightness", 1))
    r, g, b = colorsys.hls_to_rgb(h, l, min(1, s * 1.25))
    return "#" + "".join(f"{round(c * 255):02x}" for c in (r, g, b))


def graphql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {os.environ['GH_TOKEN']}"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_stats(ignore_languages):
    stars, languages, cursor = 0, {}, None
    while True:
        viewer = graphql(REPOS_QUERY, {"cursor": cursor})["viewer"]
        repos = viewer["repositories"]
        for repo in repos["nodes"]:
            stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                if name not in ignore_languages:
                    languages[name] = languages.get(name, 0) + edge["size"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    created = datetime.fromisoformat(viewer["createdAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    # contributionsCollection spans at most one year, so ask for each year in one query
    years = range(created.year, now.year + 1)
    fields = " ".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z")'
        " { contributionCalendar { totalContributions } }"
        for y in years
    )
    collections = graphql(f"query {{ viewer {{ {fields} }} }}")["viewer"]
    # the calendar total includes private and org work; commit counts hide most of it
    contributions = sum(c["contributionCalendar"]["totalContributions"] for c in collections.values())

    total = sum(languages.values()) or 1
    top = sorted(languages.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return {
        "uptime": uptime(created, now),
        "repos": repos["totalCount"],
        "stars": stars,
        "contributions": contributions,
        "followers": viewer["followers"]["totalCount"],
        "languages": [(name, round(100 * size / total)) for name, size in top],
    }


def uptime(start, now):
    months = (now.year - start.year) * 12 + now.month - start.month - (now.day < start.day)
    years, months = divmod(months, 12)
    plural = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"
    return f"{plural(years, 'year')}, {plural(months, 'month')} on GitHub"


def build_lines(profile, stats):
    """Each line is a list of (css class, text) spans."""

    def field(key, value):
        values = value if isinstance(value, list) else [value]
        dots = " " + "." * (KEY_W - len(key) - 2) + " "
        rows = [[("key", f"{key}:"), ("dim", dots), ("value", values[0].format(**stats))]]
        rows += [[("value", " " * (KEY_W + 1) + v.format(**stats))] for v in values[1:]]
        return rows

    def rule(title, width):
        if not title:
            return [[("dim", "—" * width)]]
        return [[("dim", "— "), ("host", title), ("dim", " " + "—" * (width - len(title) - 3))]]

    langs = " · ".join(f"{name} {pct}%" for name, pct in stats["languages"])
    gh = [
        ["Repos", f"{stats['repos']} · Stars {stats['stars']} · Followers {stats['followers']}"],
        ["Contributions", f"{stats['contributions']:,} (incl. private)"],
        ["Languages", langs],
    ]

    body = [kv for key, value in profile["about"] for kv in field(key, value)]
    width = max(sum(len(t) for _, t in row) for row in body)
    lines = [[("host", profile["host"])]] + rule("", width) + body + [[]]
    lines += rule("Contact", width) + [r for k, v in profile["contact"] for r in field(k, v)] + [[]]
    lines += rule("GitHub", width) + [r for k, v in gh for r in field(k, v)]
    return lines


def render(theme, portrait, lines):
    c = THEMES[theme]
    art_w = max(sum(len(t) for t, _ in row) for row in portrait) * ASCII_FONT * 0.62
    art_h = len(portrait) * ASCII_LINE
    text_w = max(sum(len(t) for _, t in row) for row in lines) * CHAR_W
    text_h = len(lines) * LINE_H
    width = round(2 * PAD + art_w + GAP * CHAR_W + text_w)
    height = round(2 * PAD + max(art_h, text_h))
    text_x = PAD + art_w + GAP * CHAR_W
    art_top = PAD + (height - 2 * PAD - art_h) / 2 + ASCII_FONT
    text_top = PAD + (height - 2 * PAD - text_h) / 2 + FONT_SIZE

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"'
        f' viewBox="0 0 {width} {height}" font-family="Consolas, Menlo, \'DejaVu Sans Mono\', \'Courier New\', monospace"'
        f' font-size="{FONT_SIZE}px">',
        "<style>"
        + "".join(f".{k}{{fill:{c[k]}}}" for k in ("text", "host", "key", "value", "dim"))
        + "</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12"'
        f' fill="{c["bg"]}" stroke="{c["border"]}"/>',
        f'<text font-size="{ASCII_FONT}px" font-weight="bold" xml:space="preserve">',
    ]
    for i, row in enumerate(portrait):
        spans = "".join(
            escape(t) if hex_ is None else f'<tspan fill="{portrait_colour(hex_, c)}">{escape(t)}</tspan>'
            for t, hex_ in row
        )
        out.append(f'<tspan x="{PAD}" y="{art_top + i * ASCII_LINE:.1f}">{spans}</tspan>')
    out.append("</text>")

    out.append('<text class="text" xml:space="preserve">')
    for i, row in enumerate(lines):
        spans = "".join(f'<tspan class="{cls}">{escape(t)}</tspan>' for cls, t in row)
        out.append(f'<tspan x="{text_x:.1f}" y="{text_top + i * LINE_H:.1f}">{spans}</tspan>')
    out.append("</text></svg>")
    return "\n".join(out) + "\n"


def main():
    profile = tomllib.loads((CARD / "profile.toml").read_text())
    if not os.environ.get("GH_TOKEN"):
        sys.exit("GH_TOKEN is empty: add a CARD_TOKEN repository secret (classic PAT, repo + read:user)")
    portrait = json.loads((CARD / "avatar.json").read_text())
    stats = fetch_stats(set(profile.get("ignore_languages", [])))
    lines = build_lines(profile, stats)
    for theme in THEMES:
        (CARD / f"{theme}.svg").write_text(render(theme, portrait, lines))
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
