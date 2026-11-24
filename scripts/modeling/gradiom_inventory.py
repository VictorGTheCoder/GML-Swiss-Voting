"""Inspect publicly displayed Gradiom forecast maps and official result schema.

No assumptions about the data endpoint, IDs, or map bin midpoints.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE = "https://www.gradiom.ch"
USER_AGENT = "GML-Research/1.0 (academic public aggregate forecast benchmark)"
PAGES = [
    "/en/swiss-popular-votes",
    "/en/swiss-popular-votes/2024-11-24",
    "/en/swiss-popular-votes/6770/commune",
    "/en/swiss-popular-votes/6770/canton",
    "/en/swiss-popular-votes/2025-09-28",
    "/en/swiss-popular-votes/2025-11-30",
    "/en/swiss-popular-votes/2026-03-08",
    "/en/swiss-popular-votes/2026-06-14",
    "/en/swiss-popular-votes/2026-09-27",
]


def main():
    out = Path("reports/generated/gradiom_inventory")
    out.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    robots = s.get(BASE + "/robots.txt", timeout=20)
    if robots.status_code == 200:
        parser = RobotFileParser()
        parser.parse(robots.text.splitlines())
        if not all(parser.can_fetch(USER_AGENT, BASE + p) for p in PAGES):
            raise ValueError("Site robots policy disallows archive collection")
    else:
        print("ROBOTS_STATUS", robots.status_code, flush=True)
    inventory = []
    for i, path in enumerate(PAGES):
        try:
            r = s.get(BASE + path, timeout=25)
            r.raise_for_status()
            if urlparse(r.url).hostname not in ("www.gradiom.ch", "gradiom.ch"):
                raise ValueError("Unexpected origin")
            soup = BeautifulSoup(r.content, "html.parser")
            (out / f"page_{i}.html").write_bytes(r.content)
            item = {
                "path": path,
                "url": r.url,
                "sha256": hashlib.sha256(r.content).hexdigest(),
                "bytes": len(r.content),
                "scripts": [
                    {"src": urljoin(r.url, x.get("src")) if x.get("src") else None,
                     "type": x.get("type"), "inline_excerpt": x.get_text()[:3000] if not x.get("src") else ""}
                    for x in soup.find_all("script")
                ],
                "frames": [dict(x.attrs) for x in soup.find_all("iframe")],
                "links": sorted(set(urljoin(r.url, a.get("href")) for a in soup.find_all("a", href=True)
                                    if "swiss-popular-votes" in a.get("href", ""))),
                "headings": [x.get_text(" ", strip=True) for x in soup.find_all(["h2", "h3", "h4", "h5"])],
                "map_tags": [],
            }
            for tag in soup.find_all(True):
                attrs = dict(tag.attrs)
                joined = str(attrs)
                if re.search(r"(map|geojson|topojson|chart|highcharts|leaflet|data-url|data-source|data-json|vote-id)", joined, re.I):
                    item["map_tags"].append({"tag": tag.name, "attributes": str(attrs)[:1500]})
                if len(item["map_tags"]) >= 60:
                    break
            inventory.append(item)
            print("PAGE", json.dumps(item, ensure_ascii=False), flush=True)
        except (requests.RequestException, ValueError) as e:
            inventory.append({"path": path, "error": str(e)})
            print("PAGE_ERROR", path, str(e), flush=True)
    result_url = "https://ogd-static.voteinfo-app.ch/v1/ogd/sd-t-17-02-20250209-eidgAbstimmung.json"
    r = s.get(result_url, timeout=30)
    r.raise_for_status()
    (out / "official_example.json").write_bytes(r.content)
    payload = r.json()
    def schema(x, depth=0):
        if depth > 5:
            return type(x).__name__
        if isinstance(x, dict):
            return {k: schema(v, depth + 1) for k, v in x.items()}
        if isinstance(x, list):
            return {"length": len(x), "example": schema(x[0], depth + 1) if x else None}
        return x
    print("OFFICIAL_SCHEMA", json.dumps(schema(payload), ensure_ascii=False)[:15000], flush=True)
    (out / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
