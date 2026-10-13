"""Exact OFS/Swissvotes question identifiers; never match on date or title alone.

Swissvotes `anr` is the BFS vote number (Swissvotes codebook, p. 3).
The OFS PX encodes it multiplied by ten: 687 -> 6870, 682.1 -> 6821.
Decimal arithmetic preserves initiative / counter-proposal / tie-break suffixes.
"""

import re
from decimal import Decimal

import pandas as pd


def swissvotes_key(value: str) -> str:
    value = str(value).strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        raise ValueError(f"Invalid Swissvotes identifier: {value!r}")
    scaled = Decimal(value) * 10
    if scaled <= 0 or scaled != scaled.to_integral_value():
        raise ValueError(f"Swissvotes identifier cannot map exactly to OFS: {value!r}")
    return str(int(scaled))


def ofs_keys(values: pd.Series) -> pd.Series:
    keys = values.astype("string").str.strip()
    if not keys.str.fullmatch(r"[1-9][0-9]*", na=False).all():
        raise ValueError("OFS vote identifiers must be non-empty positive integers")
    return keys
