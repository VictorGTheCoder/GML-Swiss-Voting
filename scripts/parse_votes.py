"""Parse the raw OFS PX cube into a lossless long table (one row per location x vote).

The PX format is a text header of ``KEYWORD[lang]("dimension")=value;`` statements
followed by ``DATA=`` and whitespace-separated values in row-major order over the
STUB dimensions then the HEADING dimension. We parse it ourselves (instead of
pyaxis) so that rows are identified by OFS *codes*: some location labels are not
unique, and codes are what other OFS datasets use for joins.

This step only reshapes: no row is dropped and no value is changed. Missing-value
symbols (e.g. ``"..."``) become NaN and are counted in ``attrs["missing_symbols"]``.

Usage: python scripts/parse_votes.py  (reads data/raw, writes data/interim)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from votes_config import (
    DIM_LOCATION, DIM_LOCATION_FR, DIM_RESULT, DIM_VOTE, DIM_VOTE_FR,
    INTERIM_PATH, RAW_PX_PATH, RESULT_COLUMNS,
)


@dataclass
class PxFile:
    metadata: dict[str, list[str]]
    data_text: str  # the DATA section, kept as text until converted by data_cube()


def _split_statements(header: str) -> list[str]:
    """Split on ';' outside double quotes (the NOTE text itself contains ';')."""
    statements, current, in_quotes = [], [], False
    for char in header:
        if char == '"':
            in_quotes = not in_quotes
        if char == ";" and not in_quotes:
            statements.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if "".join(current).strip():
        raise ValueError("PX header ends with an unterminated statement")
    return [s for s in statements if s]


def parse_px_header(header: str) -> dict[str, list[str]]:
    metadata: dict[str, list[str]] = {}
    for statement in _split_statements(header.lstrip("\ufeff")):
        key, _, value = statement.partition("=")
        strings = re.findall(r'"([^"]*)"', value)
        metadata[key.strip()] = strings if strings else [value.strip()]
    return metadata


def parse_px_text(text: str) -> PxFile:
    # "DATA=" at a line start: the keyword itself never appears inside header strings.
    header, separator, data = text.partition("\nDATA=")
    if not separator:
        raise ValueError("Not a PX file: no DATA= section")
    return PxFile(metadata=parse_px_header(header), data_text=data.strip().rstrip(";"))


def read_px(path: Path) -> PxFile:
    # The header claims CODEPAGE="iso-8859-15", but the file OFS serves is UTF-8 with BOM.
    return parse_px_text(path.read_text(encoding="utf-8-sig"))


def read_px_metadata(path: Path) -> dict[str, list[str]]:
    """Header only (fast): skips the DATA section."""
    return parse_px_header(path.read_text(encoding="utf-8-sig").partition("\nDATA=")[0])


def missing_symbols(px: PxFile) -> dict[str, int]:
    return dict(Counter(re.findall(r'"[^"]*"', px.data_text)))


def data_cube(px: PxFile, dimensions: list[str]) -> np.ndarray:
    """Values as a float array shaped like the dimensions (quoted symbols such as "..." -> NaN)."""
    shape = [len(px.metadata[f'CODES("{d}")']) for d in dimensions]
    numeric_text = re.sub(r'"[^"]*"', "nan", px.data_text)
    if re.search(r"[^0-9eE.+\-nan\s]", numeric_text):
        raise ValueError("DATA contains unexpected unquoted non-numeric tokens")
    values = np.array(numeric_text.split(), dtype=float)
    if values.size != int(np.prod(shape)):
        raise ValueError(f"DATA has {values.size} values, expected {int(np.prod(shape))} for shape {shape}")
    return values.reshape(shape)


def map_categories(series: pd.Series, func) -> pd.Series:
    """Apply func once per category instead of once per row (the long table has 1.2M rows)."""
    categorical = series.astype("category")
    lookup = pd.Series([func(c) for c in categorical.cat.categories])
    codes = categorical.cat.codes.to_numpy()
    result = lookup.reindex(codes).set_axis(series.index)  # code -1 (missing) -> NaN
    return result


def clean_location_label(label: str) -> str:
    """Drop the hierarchy prefix ('- ', '>> ', '......') and padding spaces."""
    label = re.sub(r"\s+", " ", label.lstrip("-> .")).strip()
    return label.replace(" )", ")")


def location_hierarchy(codes: list[str], labels_de: list[str], labels_fr: list[str]) -> pd.DataFrame:
    """Derive level, canton and district from the ordered hierarchical location list.

    The list is ordered Switzerland, then each canton (2-letter code) followed by its
    districts (6-digit code, label prefix '>>') and their communes (4-digit BFS number,
    label prefix '......').
    """
    rows, canton, district_code, district_name = [], None, None, None
    for code, de, fr in zip(codes, labels_de, labels_fr):
        name_fr = clean_location_label(fr)
        if code == "CH":
            level = "country"
        elif re.fullmatch(r"[A-Z]{2}", code):
            level, canton, district_code, district_name = "canton", code, None, None
        elif re.fullmatch(r"\d{6}", code):
            level, district_code, district_name = "district", code, name_fr
        elif re.fullmatch(r"\d{4}", code):
            level = "commune"
        else:
            raise ValueError(f"Unexpected location code {code!r} ({de!r})")
        rows.append({
            "level": level, "location_code": code,
            "location_name_de": clean_location_label(de), "location_name_fr": name_fr,
            "canton": None if level == "country" else canton,
            "district_code": district_code if level == "commune" else None,
            "district_name": district_name if level == "commune" else None,
        })
    return pd.DataFrame(rows)


def px_to_long(px: PxFile) -> pd.DataFrame:
    meta = px.metadata
    stub = meta["STUB"]
    if stub != [DIM_LOCATION, DIM_VOTE] or meta["HEADING"] != [DIM_RESULT]:
        raise ValueError(f"Unexpected cube layout STUB={stub} HEADING={meta['HEADING']}")
    result_codes = meta[f'CODES("{DIM_RESULT}")']
    if set(result_codes) != set(RESULT_COLUMNS):
        raise ValueError(f"Unexpected result codes {result_codes}")

    cube = data_cube(px, [DIM_LOCATION, DIM_VOTE, DIM_RESULT])
    n_loc, n_vote, n_res = cube.shape
    locations = location_hierarchy(
        meta[f'CODES("{DIM_LOCATION}")'], meta[f'VALUES("{DIM_LOCATION}")'],
        meta[f'VALUES[fr]("{DIM_LOCATION_FR}")'],
    )
    votes = pd.DataFrame({
        "vote_id": meta[f'CODES("{DIM_VOTE}")'],
        "vote_label_de": meta[f'VALUES("{DIM_VOTE}")'],
        "vote_label_fr": meta[f'VALUES[fr]("{DIM_VOTE_FR}")'],
    })
    # Row-major order: location is the outer loop, vote the inner one. Build categoricals
    # from codes directly; materialising 1.2M strings per column would cost gigabytes.
    columns: dict[str, pd.Categorical] = {}
    for name, series in locations.items():
        cat = pd.Categorical(series)
        columns[name] = pd.Categorical.from_codes(np.repeat(cat.codes, n_vote), cat.categories)
    for name, series in votes.items():
        cat = pd.Categorical(series)
        columns[name] = pd.Categorical.from_codes(np.tile(cat.codes, n_loc), cat.categories)
    frame = pd.DataFrame(columns)
    flat = cube.reshape(n_loc * n_vote, n_res)
    for index, code in enumerate(result_codes):
        frame[RESULT_COLUMNS[code]] = flat[:, index]
    frame.attrs["missing_symbols"] = missing_symbols(px)
    return frame


def main() -> None:
    if not RAW_PX_PATH.exists():
        raise SystemExit(f"{RAW_PX_PATH} not found; run scripts/download_votes.py first")
    frame = px_to_long(read_px(RAW_PX_PATH))
    INTERIM_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(INTERIM_PATH, index=False)
    print(f"Wrote {len(frame):,} rows to {INTERIM_PATH}")


if __name__ == "__main__":
    main()
