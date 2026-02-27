from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from typing import Optional, Union

import pandas as pd

DATE_COLS = [
    "Дата рождения",
    "Дата архива",
    "Дата начала тек.лакт",
    "Дата осеменения",
    "Дата успешного осеменения",
    "Дата запуска тек.лакт",
    "Дата ожидаемого запуска",
    "Дата ожидаемого отела",
]

NUM_COLS = [
    "Номер животного",
    "Лактация",
    "Дни в доении",
    "Дни стельности",
]

def _read_csv_with_fallbacks(buf: Union[str, io.BytesIO]) -> pd.DataFrame:
    # Russian CSV often uses ; separator, sometimes cp1251.
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return pd.read_csv(buf, sep=";", quotechar='"', encoding=enc)
        except Exception:
            if hasattr(buf, "seek"):
                buf.seek(0)
            continue
    # last attempt without encoding
    if hasattr(buf, "seek"):
        buf.seek(0)
    return pd.read_csv(buf, sep=";", quotechar='"')

def load_dataset_df(buf: Union[str, io.BytesIO]) -> pd.DataFrame:
    df = _read_csv_with_fallbacks(buf).copy()

    # normalize columns (strip spaces)
    df.columns = [str(c).strip() for c in df.columns]

    # parse dates (dd.mm.yyyy)
    for c in DATE_COLS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], dayfirst=True, errors="coerce").dt.date

    # parse numerics
    for c in NUM_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # ensure required columns exist
    required = ["Номер животного", "Дата рождения", "Статус коровы", "Лактация"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["Номер животного"] = df["Номер животного"].astype(int)
    df["Лактация"] = df["Лактация"].fillna(0).astype(int)

    return df

def suggest_report_date(df: pd.DataFrame) -> Optional[date]:
    # Heuristic: dataset is a snapshot; suggest max of known "Дата ожидаемого запуска/отела" minus typical offsets?
    # More stable: use max "Дата начала тек.лакт" among alive cows + their "Дни в доении" if present.
    # report ≈ start_lact + days_in_milk
    if "Дата начала тек.лакт" not in df.columns or "Дни в доении" not in df.columns:
        return None
    tmp = df[["Дата начала тек.лакт", "Дни в доении"]].dropna()
    if len(tmp) == 0:
        return None
    # use median to avoid outliers
    starts = pd.to_datetime(tmp["Дата начала тек.лакт"], errors="coerce")
    dims = tmp["Дни в доении"].astype(float)
    series = (starts + pd.to_timedelta(dims, unit="D")).dropna()
    if len(series) == 0:
        return None
    rep_ts = series.median()
    return rep_ts.date()
