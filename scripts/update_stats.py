"""Extend the profile card with the owner's explicitly selected organization projects.

Base card and rank formula: https://github.com/stats-organization/github-stats-extended
The rank adjustment changes only the stars component (weight 4 of 12).
"""

import json
import math
import os
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
USERNAME = "suhaisheng"
PROJECTS = (
    "manifoldai-research/WorldScape-Policy",
    "worldbench/awesome-vla-for-ad",
    "XPolicyLab/XPolicyLab",
)
CARD_URL = "https://github-stats-extended.vercel.app/api?" + urlencode({
    "username": USERNAME,
    "show_icons": "true",
    "theme": "material-palenight",
    "hide_border": "true",
    "include_all_commits": "true",
    "number_format": "long",
    "custom_title": "Haisheng Su's GitHub Stats",
})


def fetch(url):
    headers = {"User-Agent": "suhaisheng-profile-stats"}
    # Never send the GitHub token to the third-party card service.
    if url.startswith("https://api.github.com/"):
        headers["Accept"] = "application/vnd.github+json"
        if token := os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=40) as response:
                return response.read().decode("utf-8")
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def replace_once(pattern, replacement, text):
    result, count = re.subn(pattern, replacement, text, flags=re.S)
    if count != 1:
        raise ValueError(f"Expected exactly one card field for {pattern!r}, got {count}")
    return result


def main():
    svg = fetch(CARD_URL)
    root = ET.fromstring(svg)
    stars_node = root.find(".//*[@data-testid='stars']")
    if stars_node is None:
        raise ValueError("Card service did not return a valid statistics card")
    personal_stars = int(stars_node.text.strip().replace(",", ""))
    projects = {}
    for name in PROJECTS:
        repo = json.loads(fetch(f"https://api.github.com/repos/{name}"))
        if repo["private"] or repo["full_name"].lower() != name.lower():
            raise ValueError(f"Repository identity or visibility changed: {name}")
        if repo["owner"]["login"].lower() == USERNAME.lower():
            raise ValueError(f"Would double count a personal repository: {name}")
        count = repo["stargazers_count"]
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"Invalid star count: {name}")
        projects[repo["id"]] = {"repository": repo["full_name"], "stars": count}
    total = personal_stars + sum(item["stars"] for item in projects.values())

    # Preserve the upstream rank's other components; recompute with merged stars.
    animation = re.search(
        r"@keyframes rankAnimation\s*\{\s*from\s*\{\s*stroke-dashoffset:\s*([\d.]+);\s*\}\s*to\s*\{\s*stroke-dashoffset:\s*([\d.]+);\s*\}\s*\}", svg
    )
    if not animation:
        raise ValueError("Upstream rank structure changed; keep the last valid card")
    circumference, offset = map(float, animation.groups())
    if not math.isclose(circumference, 2 * math.pi * 40, rel_tol=1e-6):
        raise ValueError("Upstream rank circle dimensions changed")
    percentile = offset / circumference * 100
    percentile -= 100 * (4 / 12) * (
        total / (total + 50) - personal_stars / (personal_stars + 50)
    )
    percentile = max(0, min(100, percentile))
    level = next(level for threshold, level in zip(
        (1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100),
        ("S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"),
    ) if percentile <= threshold)
    svg = svg[:animation.start()] + animation.group().replace(
        animation.group(2), str(circumference * percentile / 100)
    ) + svg[animation.end():]
    svg = replace_once(r'(data-testid="stars"\s*>)[\d,]+(</text>)',
                       lambda m: m[1] + f"{total:,}" + m[2], svg)
    svg = replace_once(r"Total Stars Earned: [\d,]+", f"Total Stars Earned: {total}", svg)
    svg = replace_once(r'(data-testid="level-rank-icon"[^>]*>)\s*[^<]+(</text>)',
                       lambda m: m[1] + level + m[2], svg)
    svg = replace_once(r"Rank: [^<]+(?=</title>)", f"Rank: {level}", svg)
    scope = "Stars include personal repositories plus " + ", ".join(PROJECTS) + "."
    svg = replace_once(r"</desc>", " " + scope + "</desc>", svg)
    # Make the saved card immediately readable even in non-animated SVG viewers.
    override = (f".stagger {{ opacity: 1; animation: none; }} "
                f".header {{ animation: none; }} "
                f".rank-text {{ animation: none; transform: translate(-5px, 5px); }} "
                f".rank-circle {{ animation: none; stroke-dashoffset: {circumference * percentile / 100}; }}")
    svg = replace_once(r"</style>", override + "</style>", svg)
    svg = "\n".join(line.rstrip() for line in svg.strip().splitlines()) + "\n"
    verified = ET.fromstring(svg)
    assert int(verified.find(".//*[@data-testid='stars']").text.replace(",", "")) == total
    summary = {"personal_repository_stars": personal_stars,
               "organization_projects": list(projects.values()),
               "total_stars_earned": total, "rank": level}
    # Write only after every upstream response and the final SVG are validated.
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "github-stats.svg").write_text(svg, encoding="utf-8")
    (assets / "star-counts.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
