"""Collect public PRE-VOTE SRG/gfs.bern polls; never read referendum outcomes.

The historical date printed on a page is an announced publication date, not
proof of the exact historical version. All records therefore remain explicitly
retrospective/unverified. Discovery is restricted to the official pre-vote
cockpit URL families and the requested years; outcomes are not a data input.

Run from the repository: .venv/bin/python scripts/modeling/collect_poll_features.py
Use --offline to reproduce CSV and audit from the saved source evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/external/polls"
SITEMAP = "https://cockpit.gfsbern.ch/de/wp-sitemap-posts-cpt_cockpit-1.xml"
MONTHS = {
    v: i + 1
    for i, v in enumerate("januar februar märz april mai juni juli august september oktober november dezember".split())
}
MONTHS["maerz"] = 3
MONTH_RE = "|".join(MONTHS)
DATE_RE = rf"(\d{{1,2}})\.\s*({MONTH_RE})\s+(20\d{{2}})"
FIELDS = ["yes_certain", "yes_lean", "undecided", "no_lean", "no_certain"]
CSV_COLUMNS = [
    "vote_key",
    "vote_date",
    "swissvotes_title",
    "poll_object_title",
    "wave",
    "survey_start",
    "survey_end",
    "survey_midpoint",
    "published_at",
    *FIELDS,
    "yes_total",
    "no_total",
    "source_url",
    "chart_url",
    "chart_title",
    "page_sha256",
    "extraction_sha256",
    "chart_created_at",
    "chart_updated_at",
    "chart_updated_on_or_after_vote_date",
    "captured_before_vote",
    "retrieved_at",
    "institute",
    "commissioner",
    "mapping_status",
    "historical_version_verified",
    "strict_forecast_ready",
    "availability_status",
]
# Individually inspected first sheet: nationwide marriage-for-all poll, whose
# national row labels contain the date only (later sheets are demographic slices).
NATIONAL_BARE_DATE_CHARTS = {"https://e.infogram.com/_/eCd6aL2E33xzPwu7UELU?src=embed"}


def norm(value):
    return re.sub(
        r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    )


def sha(value):
    return hashlib.sha256(value).hexdigest()


def date_de(value):
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    match = re.search(DATE_RE, value, re.I)
    if not match:
        numeric = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b", value)
        if numeric:
            d, m, y = map(int, numeric.groups())
            return date(y, m, d).isoformat()
        return None
    d, m, y = match.groups()
    return date(int(y), MONTHS[m.lower()], int(d)).isoformat()


def date_span(value):
    value = value.strip().replace("\xa0", " ")
    matches = list(re.finditer(DATE_RE, value, re.I))
    if not matches:
        return None, None
    end = date_de(matches[-1].group())
    if len(matches) == 2:
        return date_de(matches[0].group()), end
    # "31. August – 7. September 2022" or "11. – 24. Januar 2021".
    before = value[: matches[-1].start()]
    start = re.search(rf"(\d{{1,2}})\.\s*({MONTH_RE})?\s*[–−-]", before, re.I)
    if start:
        day, month = start.groups()
        end_dt = date.fromisoformat(end)
        month_n = MONTHS[month.lower()] if month else end_dt.month
        year = end_dt.year - int(month_n > end_dt.month)
        return date(year, month_n, int(day)).isoformat(), end
    return None, end


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.heading_tag = None
        self.heading_text = []
        self.h1 = ""
        self.section = ""
        self.embeds = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in {"h1", "h2"}:
            self.heading_tag, self.heading_text = tag, []
        chart_id, chart_title, chart_url, provider = None, "", None, None
        if tag == "script" and a.get("id", "").startswith("infogram_0_"):
            chart_id = a["id"][len("infogram_0_") :]
            chart_title, provider = a.get("title", ""), "infogram"
        elif tag == "div" and "infogram-embed" in a.get("class", ""):
            chart_id = a.get("data-id")
            chart_title, provider = a.get("data-title", ""), "infogram"
        elif tag == "iframe" and a.get("src", "").startswith("https://datawrapper.dwcdn.net/"):
            chart_url, chart_title, provider = a["src"], a.get("title", ""), "datawrapper"
        if chart_id:
            chart_url = f"https://e.infogram.com/{chart_id}?src=embed"
        if chart_url:
            self.embeds.append(
                {"chart_url": chart_url, "chart_title": chart_title, "section": self.section, "provider": provider}
            )

    def handle_data(self, data):
        if self.heading_tag:
            self.heading_text.append(data)

    def handle_endtag(self, tag):
        if tag == self.heading_tag:
            value = " ".join("".join(self.heading_text).split())
            if tag == "h1":
                self.h1 = value
            else:
                self.section = value
            self.heading_tag = None


def fetch(url):
    response = requests.get(url, timeout=25, headers={"User-Agent": "GML-Swiss-Voting-poll-audit/1.0"})
    response.raise_for_status()
    return response.content, dict(response.headers)


def page_info(url):
    body, headers = fetch(url)
    raw = body.decode("utf-8")
    parser = PageParser()
    parser.feed(raw)
    if not re.search(r"^[12]\..*SRG-Trendumfrage", parser.h1):
        raise ValueError(f"Not a pre-vote SRG poll heading: {parser.h1}")
    clean = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    clean = " ".join(clean.split())

    def technical(label, stop):
        match = re.search(re.escape(label) + r"\s*(.*?)" + stop, clean, re.I)
        return match.group(1).strip() if match else None

    span = technical("Befragungszeitraum:", "mittlerer Befragungstag:")
    midpoint = technical("mittlerer Befragungstag:", "Stichprobengr[öo]sse:")
    pub = technical("Publikation:", "gfs.bern")
    survey_start, survey_end = date_span(span or "")
    publication_date = date_de(pub or "")
    publication_time = re.search(r"\b(\d{1,2})(?:h|:)(\d{2})\b", pub or "")
    published_at = None
    if publication_date and publication_time:
        h, m = map(int, publication_time.groups())
        published_at = (
            datetime.combine(date.fromisoformat(publication_date), datetime.min.time())
            .replace(hour=h, minute=m, tzinfo=ZoneInfo("Europe/Zurich"))
            .isoformat()
        )
    chart_candidates = []
    for chart in parser.embeds:
        title = norm(chart["chart_title"])
        if any(x in title for x in ["argument", "teilnahme", "ubersicht", "argumente", "_arg"]):
            continue
        if re.search(r"(?:^|_)arg(?:_|$)", chart["chart_title"], re.I):
            continue
        if title.endswith("arg"):
            continue
        chart_candidates.append(chart)
    return {
        "source_url": url,
        "page_sha256": sha(body),
        "http_last_modified": headers.get("Last-Modified"),
        "page_title": parser.h1,
        "vote_date": date_de(parser.h1),
        "wave": int(parser.h1[0]),
        "survey_span_announced": span,
        "survey_start": survey_start,
        "survey_end": survey_end,
        "survey_midpoint": date_de(midpoint or ""),
        "publication_announced": pub,
        "published_date": publication_date,
        "published_at": published_at,
        "historical_version_verified": False,
        "charts": chart_candidates,
    }


def find_tables(value, path=""):
    if isinstance(value, dict):
        if isinstance(value.get("data"), list):
            for i, sheet in enumerate(value["data"]):
                if isinstance(sheet, list) and sheet and isinstance(sheet[0], list):
                    yield path + f"/data/{i}", sheet
        for key, item in value.items():
            yield from find_tables(item, path + "/" + str(key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from find_tables(item, path + "/" + str(i))


def label_field(value):
    label = norm(value)
    return {
        "bestimmtdafur": "yes_certain",
        "eherdafur": "yes_lean",
        "weissnichtkeineantwort": "undecided",
        "weissnicht": "undecided",
        "weissnichtkeineangabe": "undecided",
        "keineantwort": "undecided",
        "eherdagegen": "no_lean",
        "bestimmtdagegen": "no_certain",
    }.get(label)


def extract_chart(chart):
    url = chart["chart_url"]
    evidence = dict(chart)
    if chart["provider"] == "infogram":
        body, _ = fetch(url)
        raw = body.decode("utf-8")
        marker = "window.infographicData="
        if marker not in raw:
            raise ValueError("Infogram embedded JSON not present")
        payload, _ = json.JSONDecoder().raw_decode(raw.split(marker, 1)[1])
        tables = list(find_tables(payload))
        evidence["chart_created_at"] = payload.get("createdAt")
        evidence["chart_updated_at"] = payload.get("updatedAt")
    else:
        data_url = url.rstrip("/") + "/data.csv"
        body, _ = fetch(data_url)
        raw = body.decode("utf-8-sig")
        dialect = csv.Sniffer().sniff(raw[:2000], delimiters=",;\t")
        tables = [("/data.csv", list(csv.reader(io.StringIO(raw), dialect)))]
        evidence["data_url"] = data_url
    evidence["chart_response_sha256"] = sha(body)
    evidence["national_rows"] = extract_national_rows(
        tables, chart["provider"], allow_bare_dates=url in NATIONAL_BARE_DATE_CHARTS
    )
    evidence["extractor_version"] = 2
    return evidence


def extract_national_rows(tables, provider, allow_bare_dates=False):
    extracted = []
    for path, sheet in tables:
        header = sheet[0]
        mapping = {i: label_field(v) for i, v in enumerate(header) if label_field(v)}
        if set(mapping.values()) == set(FIELDS):
            for row in sheet[1:]:
                label = str(row[0]) if row else ""
                # Only the nationwide likely-voter marginal; no regional/party slices.
                if (
                    norm(label).startswith("gesamteschweiz")
                    or (
                        provider == "datawrapper"
                        and date_de(label)
                        and norm(header[0]) in {"welle", "rowlabels", "datum"}
                    )
                    or (allow_bare_dates and path.endswith("/data/0") and re.fullmatch(DATE_RE, label.strip(), re.I))
                ):
                    values = {name: float(str(row[i]).replace(",", ".")) for i, name in mapping.items()}
                    extracted.append(
                        {"path": path, "header": header, "row": row, "survey_midpoint": date_de(label), **values}
                    )
        # Datawrapper pie/trend charts: one row per response, one column per wave.
        for col in range(1, len(header)):
            midpoint = date_de(str(header[col]))
            if len(header) > 2 and midpoint is None:
                continue  # Ambiguous multi-wave column: never silently take wave1.
            vertical = {}
            for row in sheet:
                if len(row) > col and label_field(row[0]):
                    vertical[label_field(row[0])] = float(str(row[col]).replace(",", "."))
            if set(vertical) == set(FIELDS):
                extracted.append(
                    {"path": path, "header": header, "row": sheet, "survey_midpoint": midpoint, **vertical}
                )
    return extracted


def upgrade_cached_chart(chart):
    """Re-extract older evidence from its exact saved numeric source rows."""
    if chart.get("extractor_version") == 2:
        return chart
    tables = {}
    for r in chart.get("national_rows", []):
        if r["row"] and isinstance(r["row"][0], list):
            tables[r["path"]] = r["row"]
        else:
            tables.setdefault(r["path"], [r["header"]]).append(r["row"])
    if tables:
        chart["national_rows"] = extract_national_rows(
            list(tables.items()), chart["provider"], allow_bare_dates=chart["chart_url"] in NATIONAL_BARE_DATE_CHARTS
        )
        chart["extractor_version"] = 2
    return chart


def run(args):
    OUT.mkdir(parents=True, exist_ok=True)
    evidence_path = OUT / "source_evidence.json"
    if args.offline:
        evidence = json.loads(evidence_path.read_text())
    else:
        sitemap, _ = fetch(SITEMAP)
        urls = re.findall(r"<loc>(.*?)</loc>", sitemap.decode())
        extra_dates = [date.fromisoformat(d).strftime("%d%m%Y") for d in args.include_vote_date]
        urls = [
            u
            for u in urls
            if re.search(r"/+(?:srg_trend_|trend_w[12]_)", u)
            and (
                any(str(y) in u for y in range(args.start_year, args.end_year + 1)) or any(d in u for d in extra_dates)
            )
        ]
        evidence = {
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "sitemap_url": SITEMAP,
            "sitemap_sha256": sha(sitemap),
            "pages": [],
            "errors": [],
        }
        cached = {}
        if args.reuse_sources and evidence_path.exists():
            previous = json.loads(evidence_path.read_text())
            cached = {p["source_url"]: p for p in previous["pages"]}

        def safe_page(url):
            try:
                return cached.get(url) or page_info(url)
            except Exception as exc:
                return {"source_url": url, "error": str(exc)}

        with ThreadPoolExecutor(max_workers=5) as pool:
            for page in pool.map(safe_page, urls):
                if "error" in page:
                    evidence["errors"].append(page)
                else:
                    evidence["pages"].append(page)
        print(
            json.dumps(
                {
                    "pages_discovered": len(urls),
                    "pages_parsed": len(evidence["pages"]),
                    "charts": sum(len(p["charts"]) for p in evidence["pages"]),
                    "errors": evidence["errors"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        jobs = [(p, c) for p in evidence["pages"] for c in p["charts"]]

        def safe_chart(job):
            page, chart = job
            try:
                chart = upgrade_cached_chart(chart)
                reuse = chart.get("chart_response_sha256") and (
                    chart.get("national_rows")
                    or (chart["provider"] != "datawrapper" and chart["chart_url"] not in NATIONAL_BARE_DATE_CHARTS)
                )
                return page, chart, chart if reuse else extract_chart(chart)
            except Exception as exc:
                return page, chart, {**chart, "error": str(exc)}

        with ThreadPoolExecutor(max_workers=5) as pool:
            for page, chart, result in pool.map(safe_chart, jobs):
                chart.update(result)
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    # Read only object identifiers, dates, and titles, including on held-out years.
    swiss = pd.read_parquet(
        ROOT / "data/processed/swissvotes/swissvotes_clean.parquet",
        columns=["vote_key", "vote_date", "titel_kurz_d", "titel_off_d"],
    )
    swiss["vote_date"] = swiss["vote_date"].dt.strftime("%Y-%m-%d")
    mapping_path = OUT / "reviewed_mappings.json"
    mappings = json.loads(mapping_path.read_text()) if mapping_path.exists() else []
    mapping_lookup = {(m["vote_date"], m["chart_title"]): m for m in mappings}
    rows, rejects = [], []
    for page in evidence["pages"]:
        in_range = f"{args.start_year}-01-01" <= page["vote_date"] <= f"{args.end_year}-12-31"
        if not in_range and page["vote_date"] not in args.include_vote_date:
            continue
        for chart in page["charts"]:
            national = chart.get("national_rows", [])
            # A multi-wave graph is only used for its current, explicitly dated wave.
            candidates = [r for r in national if r["survey_midpoint"] == page["survey_midpoint"]]
            if not candidates and len(national) == 1 and national[0]["survey_midpoint"] is None:
                candidates = national
            if len(candidates) != 1:
                rejects.append(
                    {
                        "source_url": page["source_url"],
                        "chart_title": chart["chart_title"],
                        "reason": chart.get("error", "No unique national row for current survey midpoint"),
                        "national_rows": len(national),
                    }
                )
                continue
            values = {f: candidates[0][f] for f in FIELDS}
            if not all(0 <= x <= 100 for x in values.values()) or abs(sum(values.values()) - 100) > 1.01:
                rejects.append({"chart_url": chart["chart_url"], "reason": "Invalid percentage range or sum"})
                continue
            if not (
                page["survey_start"]
                and page["survey_end"]
                and page["published_at"]
                and page["survey_start"] <= page["survey_end"] <= page["published_date"] < page["vote_date"]
                and datetime.fromisoformat(page["published_at"]) <= datetime.fromisoformat(evidence["retrieved_at"])
            ):
                rejects.append({"source_url": page["source_url"], "reason": "Missing or inconsistent pre-vote dates"})
                continue
            mapping = mapping_lookup.get((page["vote_date"], chart["chart_title"]))
            vote_key, title = None, None
            if mapping:
                matches = swiss[(swiss.vote_key == str(mapping["vote_key"])) & (swiss.vote_date == page["vote_date"])]
                if len(matches) != 1 or matches.iloc[0].titel_kurz_d != mapping["swissvotes_title"]:
                    raise ValueError(f"Reviewed mapping no longer matches Swissvotes: {mapping}")
                vote_key, title = str(mapping["vote_key"]), mapping["swissvotes_title"]
            row = {
                "vote_key": vote_key,
                "vote_date": page["vote_date"],
                "swissvotes_title": title,
                "poll_object_title": chart["section"],
                "wave": page["wave"],
                "survey_start": page["survey_start"],
                "survey_end": page["survey_end"],
                "survey_midpoint": page["survey_midpoint"],
                "published_at": page["published_at"],
                **values,
                "yes_total": values["yes_certain"] + values["yes_lean"],
                "no_total": values["no_certain"] + values["no_lean"],
                "source_url": page["source_url"],
                "chart_url": chart["chart_url"],
                "chart_title": chart["chart_title"],
                "page_sha256": page["page_sha256"],
                "extraction_sha256": chart["chart_response_sha256"],
                "chart_created_at": chart.get("chart_created_at"),
                "chart_updated_at": chart.get("chart_updated_at"),
                "chart_updated_on_or_after_vote_date": (
                    chart["chart_updated_at"][:10] >= page["vote_date"] if chart.get("chart_updated_at") else None
                ),
                "captured_before_vote": evidence["retrieved_at"][:10] < page["vote_date"],
                "retrieved_at": evidence["retrieved_at"],
                "institute": "gfs.bern",
                "commissioner": "SRG SSR",
                "mapping_status": "reviewed_date_and_title" if mapping else "unmapped_excluded",
                "historical_version_verified": False,
                "strict_forecast_ready": False,
                "availability_status": "announced_pre_vote_date_current_source_unverified",
            }
            rows.append(row)
    frame = pd.DataFrame(rows, columns=CSV_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(["vote_date", "vote_key", "wave", "chart_title"], na_position="last")
        mapped = frame[frame.vote_key.notna()]
        if mapped.duplicated(["vote_key", "wave"]).any():
            raise ValueError("Duplicate mapped vote_key/wave; review competing charts before using data")
    else:
        mapped = frame
    # Always replace the CSV, including an empty selection; never leave stale rows.
    frame.to_csv(OUT / "srg_gfs_polls.csv", index=False)
    denominator = swiss[
        swiss.vote_date.between(f"{args.start_year}-01-01", f"{args.end_year}-12-31")
        | swiss.vote_date.isin(args.include_vote_date)
    ]
    coverage = []
    for year, group in denominator.groupby(denominator.vote_date.str[:4]):
        year_rows = mapped[mapped.vote_date.str.startswith(year)] if not mapped.empty else mapped
        coverage.append(
            {
                "year": int(year),
                "swissvotes_objects": len(group),
                "mapped_poll_objects": int(year_rows.vote_key.nunique()) if not year_rows.empty else 0,
                "mapped_waves": len(year_rows),
            }
        )
    provenance = {
        "schema_version": 1,
        "purpose": "Pre-vote national opinion features, no referendum outcomes read",
        "percentage_unit": "percentage points (0..100), five response categories",
        "historical_version_verified": False,
        "strict_forecast_ready": False,
        "availability_warning": "Dates are announced on currently retrieved pages. No historical archived version has been verified.",
        "mapping_policy": "Exact date and individually reviewed chart-title/object-key mappings; unreviewed rows excluded",
        "retrieved_at": evidence["retrieved_at"],
        "poll_rows": len(frame),
        "mapped_rows": len(mapped),
        "requested_scope": {
            "start_year": args.start_year,
            "end_year": args.end_year,
            "additional_vote_dates": args.include_vote_date,
        },
        "coverage": coverage,
        "rejected_charts": rejects,
        "source_errors": evidence["errors"],
        "source_evidence_file": "source_evidence.json",
        "reviewed_mapping_file": "reviewed_mappings.json",
        "source_evidence_sha256": sha(evidence_path.read_bytes()),
        "reviewed_mappings_sha256": sha(mapping_path.read_bytes()) if mapping_path.exists() else None,
        "poll_csv_sha256": sha((OUT / "srg_gfs_polls.csv").read_bytes()),
        "swissvotes_identifier_title_projection_sha256": sha(swiss.to_csv(index=False).encode()),
        "collector_sha256": sha(Path(__file__).read_bytes()),
        "early_archive_limitation": "Cockpit pre-vote sitemap starts in 2021. 2012-2020 are not filled or inferred.",
        "forecast_cutoff_rule": "Use only published_at <= forecast cutoff; do not expose wave2 at a wave1 forecast horizon.",
        "population_rule": "Do not select evaluation objects according to poll availability; missing polls require a fitted fallback.",
    }
    (OUT / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "poll_rows": len(frame),
                "mapped_rows": len(mapped),
                "coverage": coverage,
                "rejected_charts": len(rejects),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2012)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--reuse-sources", action="store_true", help="Reuse saved source evidence, fetch only missing pages/charts"
    )
    parser.add_argument(
        "--include-vote-date", action="append", default=[], help="Additionally collect one explicit ISO vote date"
    )
    run(parser.parse_args())
