"""Stream the complete STATPOP PX into the same annual extracts as the API.

Only one age row is tokenized at a time. Existing API extracts are compared cell
by cell before reuse; no missing value is converted to zero.
"""

from __future__ import annotations

from itertools import product
from pathlib import Path

import pandas as pd

from scripts.common.communes import ROOT, record_provenance, write_atomic
from scripts.ofs_votes.parse_ofs_votes import read_px_metadata


def data_rows(handle, width):
    pending = []
    for line in handle:
        pending.extend(line.strip().removesuffix(";").split())
        while len(pending) >= width:
            yield pending[:width]
            pending = pending[width:]
    if pending:
        raise ValueError("Truncated STATPOP age row")


def extract_years(px_path: Path, *, force: bool = False) -> None:
    from scripts.statpop.download_statpop import (
        DIM_AGE,
        DIM_NATIONALITY,
        DIM_PLACE,
        DIM_POPTYPE,
        DIM_SEX,
        DIM_YEAR,
        PERMANENT_POPULATION,
        STATPOP_DOWNLOAD_URL,
        STATPOP_RAW_DIR,
        TOTAL_CODE,
    )

    metadata = read_px_metadata(px_path)
    dimensions = [DIM_YEAR, DIM_PLACE, DIM_POPTYPE, DIM_NATIONALITY, DIM_SEX]
    if metadata["STUB"] != dimensions or metadata["HEADING"] != [DIM_AGE]:
        raise ValueError("STATPOP PX dimension order changed")
    codes = {dim: metadata[f'CODES("{dim}")'] for dim in dimensions + [DIM_AGE]}
    names = metadata["STUB[fr]"]
    labels = {dim: metadata[f'VALUES[fr]("{name}")'] for dim, name in zip(dimensions, names, strict=True)}
    age_labels = metadata[f'VALUES[fr]("{metadata["HEADING[fr]"][0]}")']
    if codes[DIM_AGE] != [TOTAL_CODE] + [str(i) for i in range(101)]:
        raise ValueError("STATPOP age definitions changed")
    with px_path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.startswith("DATA="):
                break
        rows = data_rows(handle, len(age_labels))
        for year in codes[DIM_YEAR]:
            records = []
            for place, pop, nat, sex in product(*(range(len(codes[d])) for d in dimensions[1:])):
                values = next(rows)
                if (not labels[DIM_PLACE][place].startswith("......")
                        or codes[DIM_POPTYPE][pop] != PERMANENT_POPULATION
                        or codes[DIM_SEX][sex] != TOTAL_CODE):
                    continue
                records.append([year, labels[DIM_PLACE][place], labels[DIM_POPTYPE][pop],
                                labels[DIM_NATIONALITY][nat], labels[DIM_SEX][sex], *values])
            frame = pd.DataFrame(records, columns=names + age_labels, dtype="string")
            path = STATPOP_RAW_DIR / f"statpop_{year}.csv"
            if path.exists() and not force:
                existing = pd.read_csv(path, dtype="string")
                pd.testing.assert_frame_equal(existing, frame, check_dtype=False)
                print(f"Verified API/PX equivalence: {year}, {len(frame):,} rows")
            else:
                write_atomic(path, frame.to_csv(index=False).encode("utf-8"))
                record_provenance(path.stem, path, STATPOP_DOWNLOAD_URL, year=year,
                                  derived_from=px_path.relative_to(ROOT).as_posix(),
                                  px_last_updated=metadata.get("LAST-UPDATED"),
                                  filters="communes, permanent residents, sex total, all nationalities and ages")
                print(f"Extracted {path.relative_to(ROOT)} ({len(frame):,} rows)")
        if next(rows, None) is not None:
            raise ValueError("Unexpected trailing STATPOP data")
