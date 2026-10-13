"""Parse the raw OFS PX cube into a lossless long table (one row per location x vote).

The PX format is a text header of ``KEYWORD[lang]("dimension")=value;`` statements
followed by ``DATA=`` and whitespace-separated values in row-major order over the
STUB dimensions then the HEADING dimension. We parse it ourselves (instead of
pyaxis) so that rows are identified by OFS *codes*: some location labels are not
unique, and codes are what other OFS datasets use for joins.

This step only reshapes: no row is dropped and no value is changed. Missing-value
symbols (e.g. ``"..."``) become NaN and are counted in ``attrs["missing_symbols"]``.

Usage: python -m scripts.ofs_votes.parse_ofs_votes  (reads data/raw, writes data/interim)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import (
    DIM_LOCATION,
    DIM_LOCATION_FR,
    DIM_RESULT,
    DIM_VOTE,
    DIM_VOTE_FR,
    INTERIM_PATH,
    RAW_PX_PATH,
    RESULT_COLUMNS,
)


@dataclass
class PxFile:
    metadata: dict[str, list[str]]
    data_tokens: list[str]


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
    for statement in _split_statements(header.lstrip("﻿")):
        key, _, value = statement.partition("=")
        strings = re.findall(r'"([^"]*)"', value)
        metadata[key.strip()] = strings if strings else [value.strip()]
    return metadata


def parse_px_text(text: str) -> PxFile:
    # "DATA=" at a line start: the keyword itself never appears inside header strings.
    header, separator, data = text.partition("\nDATA=")
    if not separator:
        raise ValueError("Not a PX file: no DATA= section")
    return PxFile(metadata=parse_px_header(header), data_tokens=data.strip().rstrip(";").split())


def read_px(path: Path) -> PxFile:
    # The header claims CODEPAGE="iso-8859-15", but the file OFS serves is UTF-8 with BOM.
    return parse_px_text(path.read_text(encoding="utf-8-sig"))


def read_px_metadata(path: Path) -> dict[str, list[str]]:
    """Header only (fast): skips tokenising the DATA section."""
    lines = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.startswith("DATA="):
                return parse_px_header("".join(lines))
            lines.append(line)
    raise ValueError("Not a PX file: no DATA= section")


def data_cube(px: PxFile, dimensions: list[str]) -> np.ndarray:
    """Values as a float array shaped like the dimensions (quoted symbols -> NaN)."""
    shape = [len(px.metadata[f'CODES("{d}")']) for d in dimensions]
    if len(px.data_tokens) != int(np.prod(shape)):
        raise ValueError(f"DATA has {len(px.data_tokens)} values, expected {int(np.prod(shape))} for shape {shape}")
    tokens = pd.Series(px.data_tokens)
    quoted = tokens.str.startswith('"')
    values = pd.to_numeric(tokens.where(~quoted), errors="raise")
    return values.to_numpy(dtype=float).reshape(shape)


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
    for code, de, fr in zip(codes, labels_de, labels_fr, strict=True):
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
    # Row-major order: location is the outer loop, vote the inner one.
    frame = pd.concat(
        [locations.loc[locations.index.repeat(n_vote)].reset_index(drop=True),
         pd.concat([votes] * n_loc, ignore_index=True)],
        axis=1,
    )
    values = pd.DataFrame(cube.reshape(n_loc * n_vote, n_res),
                          columns=[RESULT_COLUMNS[c] for c in result_codes])
    frame = pd.concat([frame, values], axis=1)
    for column in ["level", "canton", "district_code", "district_name", "location_code",
                   "location_name_de", "location_name_fr", "vote_id", "vote_label_de", "vote_label_fr"]:
        frame[column] = frame[column].astype("category")
    frame.attrs["missing_symbols"] = dict(Counter(t for t in px.data_tokens if t.startswith('"')))
    return frame


def main() -> None:
    if not RAW_PX_PATH.exists():
        raise SystemExit(f"{RAW_PX_PATH} not found; run python -m scripts.ofs_votes.download_ofs_votes first")
    frame = px_to_long(read_px(RAW_PX_PATH))
    INTERIM_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(INTERIM_PATH, index=False)
    print(f"Wrote {len(frame):,} rows to {INTERIM_PATH}")


if __name__ == "__main__":
    main()
