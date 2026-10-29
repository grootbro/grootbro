"""Render a small public-contributions card using GitHub's search API."""
import collections
import datetime as dt
import html
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

owner = os.environ["GITHUB_REPOSITORY_OWNER"]
query = f"author:{owner} is:pr is:merged is:public -user:{owner}"
headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": f"{owner}-profile-showcase",
}
items = []
page = 1
while True:
    params = urllib.parse.urlencode({
        "q": query, "sort": "updated", "order": "desc",
        "per_page": 100, "page": page,
    })
    request = urllib.request.Request(
        f"https://api.github.com/search/issues?{params}", headers=headers
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("incomplete_results"):
        raise RuntimeError("GitHub returned incomplete search results; keep the last good card.")
    total = payload["total_count"]
    if total > 1000:
        raise RuntimeError("Search exceeds GitHub’s 1000-result limit; split the query before publishing.")
    items.extend(payload["items"])
    if len(items) >= total or not payload["items"]:
        break
    page += 1

if len({item["id"] for item in items}) != total:
    raise RuntimeError("Search returned missing or duplicate PRs; keep the last good card.")

groups = collections.defaultdict(list)
for item in items:
    if not item.get("pull_request", {}).get("merged_at"):
        continue
    repo = item["repository_url"].split("/repos/", 1)[1]
    groups[repo].append(item)
for prs in groups.values():
    prs.sort(key=lambda pr: pr["pull_request"]["merged_at"], reverse=True)
featured = sorted(
    groups.items(),
    key=lambda group: (group[1][0]["pull_request"]["merged_at"], group[0]),
    reverse=True,
)
if not featured:
    raise RuntimeError("No merged public contributions returned; keep the last good card.")

updated = dt.datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%d %b %Y")
root = Path("assets")
root.mkdir(exist_ok=True)

def escape(value):
    return html.escape(str(value), quote=True)

def clipped(value, limit=86):
    return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"

recent = sorted(
    (pr for _, prs in featured for pr in prs),
    key=lambda pr: (pr["pull_request"]["merged_at"], pr["id"]),
    reverse=True,
)[:5]
recent_rows = [(pr["repository_url"].split("/repos/", 1)[1], [pr]) for pr in recent]
for variant, rows in (("recent", recent_rows), ("projects", featured)):
    height = 132 + len(rows) * 82
    for theme, colors in {
        "dark": ("#0d1117", "#30363d", "#e6edf3", "#8b949e", "#58a6ff", "#bc8cff", "#161b22"),
        "light": ("#ffffff", "#d0d7de", "#1f2328", "#59636e", "#0969da", "#8250df", "#f6f8fa"),
    }.items():
        bg, border, fg, muted, blue, purple, pill = colors
        heading = "Latest contributions" if variant == "recent" else "Open-source contributions"
        description = "Latest five merged pull requests." if variant == "recent" else "Latest merged contribution and total merged pull requests for every project."
        summary = f"{sum(len(prs) for _, prs in featured)} merged pull requests across {len(featured)} projects"
        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="840" height="{height}" viewBox="0 0 840 {height}" role="img" aria-labelledby="title desc">',
            '<title id="title">Open-source contributions by ' + escape(owner) + '</title>',
            f'<desc id="desc">{description}</desc>',
            f'<rect x=".5" y=".5" width="839" height="{height-1}" rx="12" fill="{bg}" stroke="{border}"/>',
            f'<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" fill="{fg}">',
            f'<text x="26" y="39" font-size="21" font-weight="600">{heading}</text>',
            f'<text x="26" y="66" font-size="14" fill="{muted}">{escape(summary)}</text>',
        ]
        for index, (repo, prs) in enumerate(rows):
            latest = prs[0]
            badge = "merged" if variant == "recent" else f"{len(prs)} merged"
            y = 108 + index * 82
            merged = dt.datetime.fromisoformat(
                latest["pull_request"]["merged_at"].replace("Z", "+00:00")
            ).strftime("%d %b %Y")
            if index:
                svg.append(f'<path d="M26 {y-23}H814" stroke="{border}"/>')
            svg.extend([
                f'<g transform="translate(28 {y-12})" fill="none" stroke="{purple}" stroke-width="2">',
                '<circle cx="3" cy="3" r="2.5"/><circle cx="15" cy="3" r="2.5"/><circle cx="3" cy="17" r="2.5"/><path d="M3 5.5v9M12.5 3H10a7 7 0 0 0-7 7"/></g>',
                f'<text x="60" y="{y+2}" font-size="16" font-weight="600" fill="{blue}">{escape(repo)}</text>',
                f'<rect x="716" y="{y-16}" width="98" height="24" rx="12" fill="{pill}"/>',
                f'<text x="765" y="{y}" text-anchor="middle" font-size="12" fill="{muted}">{badge}</text>',
                f'<text x="60" y="{y+26}" font-size="14">{escape(clipped(latest["title"]))}</text>',
                f'<text x="60" y="{y+47}" font-size="12" fill="{muted}">#{latest["number"]} · merged {merged}</text>',
            ])
        svg.extend([
            f'<text x="26" y="{height-21}" font-size="12" fill="{muted}">{"Latest 5 merges" if variant == "recent" else "All projects · latest merge per project"} · updated {updated}</text>',
            '</g></svg>',
        ])
        (root / f"open-source-{'recent-' if variant == 'recent' else ''}{theme}.svg").write_text("\n".join(svg) + "\n", encoding="utf-8")
print(f"Rendered {total} merged public PRs, featuring {len(featured)} projects.")

# Native Markdown keeps every PR clickable when GitHub embeds the SVG as an image.
readme = Path("readme.md")
start = "<!-- merged-prs:start -->"
end = "<!-- merged-prs:end -->"
source = readme.read_text(encoding="utf-8")
if source.count(start) != 1 or source.count(end) != 1:
    raise RuntimeError("Expected one merged-PR section in readme.md.")
lines = [start, "", "<details>", f"<summary><b>Explore all {len(featured)} projects</b></summary>", "",
    '<picture>',
    f'  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/{owner}/{owner}/main/assets/open-source-dark.svg">',
    f'  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/{owner}/{owner}/main/assets/open-source-light.svg">',
    f'  <img alt="All contribution projects" src="https://raw.githubusercontent.com/{owner}/{owner}/main/assets/open-source-light.svg" width="840">',
    '</picture>', "", "</details>", "", "<details>",
    f"<summary><b>Browse all {total} merged pull requests</b></summary>", ""]
for repo, prs in featured:
    lines.extend([f"**[{repo}](https://github.com/{repo})** · {len(prs)} merged", ""])
    for pr in prs:
        title = html.escape(pr["title"])
        title = "".join("\\" + char if char in "\\`*{}_[]<>|" else char for char in title)
        date = pr["pull_request"]["merged_at"][:10]
        lines.append(f'- [{title} (#{pr["number"]})]({pr["html_url"]}) · {date}')
    lines.append("")
lines.extend(["</details>", "", end])
readme.write_text(source.split(start)[0] + "\n".join(lines) + source.split(end)[1], encoding="utf-8")
