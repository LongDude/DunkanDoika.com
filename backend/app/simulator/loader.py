from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from typing import Optional, Union

import pandas as pd

COL_ANIMAL_ID = "Номер животного"
COL_BIRTH_DATE = "Дата рождения"
COL_ARCHIVE_DATE = "Дата архива"
COL_LACTATION = "Лактация"
COL_LACTATION_START = "Дата начала тек.лакт"
COL_DAYS_IN_MILK = "Дни в доении"
COL_STATUS = "Статус коровы"
COL_INSEM_DATE = "Дата осеменения"
COL_SUCCESS_INSEM_DATE = "Дата успешного осеменения"
COL_DAYS_PREGNANT = "Дни стельности"
COL_DRYOFF_DATE = "Дата запуска тек.лакт"
COL_EXPECTED_DRYOFF = "Дата ожидаемого запуска"
COL_EXPECTED_CALVING = "Дата ожидаемого отела"

DATE_COLS = [
    COL_BIRTH_DATE,
    COL_ARCHIVE_DATE,
    COL_LACTATION_START,
    COL_INSEM_DATE,
    COL_SUCCESS_INSEM_DATE,
    COL_DRYOFF_DATE,
    COL_EXPECTED_DRYOFF,
    COL_EXPECTED_CALVING,
]

NUM_COLS = [
    COL_ANIMAL_ID,
    COL_LACTATION,
    COL_DAYS_IN_MILK,
    COL_DAYS_PREGNANT,
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
    required = [COL_ANIMAL_ID, COL_BIRTH_DATE, COL_STATUS, COL_LACTATION]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df[COL_ANIMAL_ID] = df[COL_ANIMAL_ID].astype(int)
    df[COL_LACTATION] = df[COL_LACTATION].fillna(0).astype(int)

    return df

def suggest_report_date(df: pd.DataFrame) -> Optional[date]:
    # Heuristic: dataset is a snapshot; suggest max of known "Дата ожидаемого запуска/отела" minus typical offsets?
    # More stable: use max "Дата начала тек.лакт" among alive cows + their "Дни в доении" if present.
    # report ≈ start_lact + days_in_milk
    if COL_LACTATION_START not in df.columns or COL_DAYS_IN_MILK not in df.columns:
        return None
    tmp = df[[COL_LACTATION_START, COL_DAYS_IN_MILK]].dropna()
    if len(tmp) == 0:
        return None
    # use median to avoid outliers
    starts = pd.to_datetime(tmp[COL_LACTATION_START], errors="coerce")
    dims = tmp[COL_DAYS_IN_MILK].astype(float)
    series = (starts + pd.to_timedelta(dims, unit="D")).dropna()
    if len(series) == 0:
        return None
    rep_ts = series.median()
    return rep_ts.date()
