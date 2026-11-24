"""Inventory candidate mean-YES expectations from reviewed SRG pages.

Candidates are for manual review only. No value is injected into the benchmark.
Do not infer a mean from the share expecting acceptance. Record source errors.
"""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

from scripts.modeling.collect_poll_features import fetch, sha
from scripts.modeling.expectations_v101 import POLL_SOURCE


class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = None
        self.text = []
        self.heading = ""
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        if tag in {"h2", "h3", "h4", "p"} and self.active is None:
            self.active = tag
            self.text = []

    def handle_data(self, data):
        if self.active:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag != self.active:
            return
        content = " ".join(" ".join(self.text).split())
        if tag.startswith("h"):
            self.heading = content
        elif content:
            self.blocks.append((self.heading, content))
        self.active = None


def inspect(record):
    try:
        body, _ = fetch(record["source_url"])
        parser = Paragraphs()
        parser.feed(body.decode("utf-8"))
        candidates = []
        for section, content in parser.blocks:
            if not re.search(r"erwart|schätz|schatz", content, re.I):
                continue
            if not re.search(r"ja[-– ]?(?:stimmen)?anteil", content, re.I):
                continue
            if not re.search(r"mittel|durchschnitt|geschätzt|erwartet", content, re.I):
                continue
            for sentence in re.split(r"(?<!\d)(?<=[.!?])\s+(?=[A-ZÄÖÜ])", content):
                if re.search(r"ja[-– ]?(?:stimmen)?anteil", sentence, re.I) and re.search(
                    r"mittel|durchschnitt|geschätzt|erwartet", sentence, re.I
                ):
                    # Keep numeric evidence and short contextual sentence for review.
                    candidates.append({"section": section, "excerpt": " ".join(sentence.split()[:24]),
                                       "numbers": re.findall(r"\d+(?:[.,]\d+)?\s*(?:%|Prozent)", sentence)})
        return {**record, "sha256": sha(body), "candidates": candidates}
    except Exception as e:
        return {**record, "error": str(e)[:500]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    national = pd.read_csv(POLL_SOURCE, dtype={"vote_key": str})
    records = national[national.vote_date.between("2016-01-01", "2022-12-31")][
        ["vote_date", "wave", "source_url", "published_at"]
    ].drop_duplicates().to_dict("records")
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(inspect, records))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in result:
        print("SOURCE", json.dumps(r, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
