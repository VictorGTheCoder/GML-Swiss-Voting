"""Parallel target-blind source inventory for V10.8 and V10.9."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests

from scripts.common.config import ROOT

URL = "https://www.estv.admin.ch/de/statistiken-zur-direkten-bundessteuer"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.urls.append(urljoin(URL, href))


def income_inventory(output):
    """Acquire only official aggregate annual statistical key figures."""
    page = requests.get(URL, timeout=50)
    page.raise_for_status()
    links = Links()
    links.feed(page.text)
    urls = {}
    for link in links.urls:
        match = re.search(r"statistik-dbst-np-kennzahlen-ohne-(20\d{2})-de\.xlsx", link)
        if match and urlparse(link).hostname == "www.estv.admin.ch":
            year = int(match.group(1))
            if 2003 <= year <= 2018:
                urls.setdefault(year, set()).add(link)
    if len(urls) < 10 or any(len(v) != 1 for v in urls.values()):
        raise ValueError(f"Unexpected official income links: {urls}")
    inventory = []
    for year, candidates in sorted(urls.items()):
        url = next(iter(candidates))
        try:
            res = requests.get(url, timeout=45)
            res.raise_for_status()
            data = res.content
            if not data.startswith(b"PK"):
                raise ValueError("Not XLSX")
            path = output / f"income_{year}.xlsx"
            path.write_bytes(data)
            xl = pd.ExcelFile(io.BytesIO(data), engine="openpyxl")
            sheets = []
            for sheet in xl.sheet_names:
                frame = pd.read_excel(xl, sheet_name=sheet, header=None, nrows=15)
                sheets.append({"sheet": sheet, "head": frame.fillna("").astype(str).values.tolist()})
            item = {"year": year, "url": url, "sha256": hashlib.sha256(data).hexdigest(),
                    "sheets": sheets}
            inventory.append(item)
            print("INCOME_SCHEMA", json.dumps(item, ensure_ascii=False), flush=True)
        except Exception as exc:
            inventory.append({"year": year, "url": url, "error": str(exc)[:500]})
    (output/"income_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2))
    print("INCOME_COVERAGE", len([r for r in inventory if "sha256" in r]), flush=True)


def brochure_inventory(output):
    base = ROOT/"data/processed/federal_explanations"
    section = pd.read_parquet(base/"sections.parquet")
    source = pd.read_parquet(base/"sources.parquet")
    pages = pd.read_parquet(base/"pages.parquet")
    objects = pd.read_parquet(base/"objects.parquet")
    links = pd.read_parquet(base/"section_links.parquet")
    print("SCHEMAS", json.dumps({k: list(v.columns) for k,v in
          {"section":section,"source":source,"pages":pages,"objects":objects,"links":links}.items()}), flush=True)
    sv = pd.read_parquet(ROOT/"data/processed/swissvotes/swissvotes_clean.parquet",
                         columns=["vote_key","vote_date","titel_kurz_f","titel_off_f"])
    sv["vote_key"] = sv.vote_key.astype(str)
    sv["vote_date"] = pd.to_datetime(sv.vote_date)
    roster = pd.read_csv(ROOT/"data/processed/municipal_v3/object_features.csv",
                         usecols=["vote_id","vote_key","vote_date"], dtype={"vote_id":str,"vote_key":str})
    roster["vote_date"] = pd.to_datetime(roster.vote_date)
    roster = roster[roster.vote_date.between("1990-01-01","2022-12-31")].merge(sv,on=["vote_key","vote_date"],validate="one_to_one")
    source["vote_date"] = pd.to_datetime(source.vote_date)
    source = source[source.vote_date.between("1990-01-01","2022-12-31") & source.language.eq("fr")]
    for day, src in source.groupby("vote_date"):
        s = section[section.source_id.isin(src.source_id)]
        row = {"date":str(day.date()), "sources":src.source_id.tolist(),
               "titles":roster.loc[roster.vote_date.eq(day),["vote_id","titel_off_f","titel_kurz_f"]].fillna("").values.tolist(),
               "sections":[{"id":str(x.object_id),"title":str(x.title),"summary_len":len(str(x.summary_official)),
                            "body_len":len(str(x.full_text)), "body_start":str(x.full_text)[:350]}
                           for x in s.itertuples()]}
        if day.year>=2016:
            print("BROCHURE_DATE",json.dumps(row,ensure_ascii=False),flush=True)
    inventory = {"roster":len(roster),"sources":len(source),"sections":len(section[section.source_id.isin(source.source_id)]),
                 "hashes":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in base.glob("*.parquet")}}
    (output/"brochure_inventory.json").write_text(json.dumps(inventory,indent=2))
    print("BROCHURE_COVERAGE",json.dumps(inventory),flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite", choices=["brochures","income"], required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    if a.suite == "brochures":
        brochure_inventory(a.output)
    else:
        income_inventory(a.output)


if __name__ == "__main__":
    main()
