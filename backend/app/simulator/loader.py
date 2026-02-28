from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, timedelta
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

# Backward-compatibility aliases for previously broken mojibake headers.
_COLUMN_ALIASES = {
    "Р СњР С•Р СР ВµРЎР‚ Р В¶Р С‘Р Р†Р С•РЎвЂљР Р…Р С•Р С–Р С•": COL_ANIMAL_ID,
    "Р вЂќР В°РЎвЂљР В° РЎР‚Р С•Р В¶Р Т‘Р ВµР Р…Р С‘РЎРЏ": COL_BIRTH_DATE,
    "Р вЂќР В°РЎвЂљР В° Р В°РЎР‚РЎвЂ¦Р С‘Р Р†Р В°": COL_ARCHIVE_DATE,
    "Р вЂєР В°Р С”РЎвЂљР В°РЎвЂ Р С‘РЎРЏ": COL_LACTATION,
    "Р вЂќР В°РЎвЂљР В° Р Р…Р В°РЎвЂЎР В°Р В»Р В° РЎвЂљР ВµР С”.Р В»Р В°Р С”РЎвЂљ": COL_LACTATION_START,
    "Р вЂќР Р…Р С‘ Р Р† Р Т‘Р С•Р ВµР Р…Р С‘Р С‘": COL_DAYS_IN_MILK,
    "Р РЋРЎвЂљР В°РЎвЂљРЎС“РЎРѓ Р С”Р С•РЎР‚Р С•Р Р†РЎвЂ№": COL_STATUS,
    "Р вЂќР В°РЎвЂљР В° Р С•РЎРѓР ВµР СР ВµР Р…Р ВµР Р…Р С‘РЎРЏ": COL_INSEM_DATE,
    "Р вЂќР В°РЎвЂљР В° РЎС“РЎРѓР С—Р ВµРЎв‚¬Р Р…Р С•Р С–Р С• Р С•РЎРѓР ВµР СР ВµР Р…Р ВµР Р…Р С‘РЎРЏ": COL_SUCCESS_INSEM_DATE,
    "Р вЂќР Р…Р С‘ РЎРѓРЎвЂљР ВµР В»РЎРЉР Р…Р С•РЎРѓРЎвЂљР С‘": COL_DAYS_PREGNANT,
    "Р вЂќР В°РЎвЂљР В° Р В·Р В°Р С—РЎС“РЎРѓР С”Р В° РЎвЂљР ВµР С”.Р В»Р В°Р С”РЎвЂљ": COL_DRYOFF_DATE,
    "Р вЂќР В°РЎвЂљР В° Р С•Р В¶Р С‘Р Т‘Р В°Р ВµР СР С•Р С–Р С• Р В·Р В°Р С—РЎС“РЎРѓР С”Р В°": COL_EXPECTED_DRYOFF,
    "Р вЂќР В°РЎвЂљР В° Р С•Р В¶Р С‘Р Т‘Р В°Р ВµР СР С•Р С–Р С• Р С•РЎвЂљР ВµР В»Р В°": COL_EXPECTED_CALVING,
}

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

REQUIRED_COLS = [COL_ANIMAL_ID, COL_BIRTH_DATE, COL_STATUS, COL_LACTATION]


@dataclass
class DatasetLoadResult:
    dataframe: pd.DataFrame
    quality_issues: list[dict]
    report_date_suggested: Optional[date]


class DatasetValidationError(ValueError):
    def __init__(self, message: str, error_code: str = "DATASET_VALIDATION_FAILED", details: dict | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


def _read_csv_with_fallbacks(buf: Union[str, io.BytesIO]) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return pd.read_csv(buf, sep=";", quotechar='"', encoding=enc)
        except Exception:
            if hasattr(buf, "seek"):
                buf.seek(0)
            continue
    if hasattr(buf, "seek"):
        buf.seek(0)
    return pd.read_csv(buf, sep=";", quotechar='"')


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    normalized: list[str] = []
    for col in out.columns:
        name = str(col).strip()
        normalized.append(_COLUMN_ALIASES.get(name, name))
    out.columns = normalized
    return out


def _parse_dataset(raw_df: pd.DataFrame) -> pd.DataFrame:
    df = raw_df.copy()
    for c in DATE_COLS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], dayfirst=True, errors="coerce").dt.date
    for c in NUM_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _sample_rows(mask: pd.Series, max_items: int = 5) -> list[int]:
    if mask.empty:
        return []
    idx = list(mask[mask].index[:max_items])
    # +2 converts pandas 0-based row index to common CSV row number with header line.
    return [int(i) + 2 for i in idx]


def _quality_issue(
    *,
    code: str,
    severity: str,
    message: str,
    mask: pd.Series | None = None,
    row_count: int | None = None,
) -> dict:
    count = row_count if row_count is not None else (int(mask.sum()) if mask is not None else None)
    issue: dict = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if count is not None:
        issue["row_count"] = count
    if mask is not None:
        sample = _sample_rows(mask)
        if sample:
            issue["sample_rows"] = sample
    return issue


def validate_dataset_quality(
    raw_df: pd.DataFrame,
    parsed_df: pd.DataFrame,
    report_date: Optional[date],
) -> list[dict]:
    issues: list[dict] = []

    for c in DATE_COLS:
        if c not in raw_df.columns or c not in parsed_df.columns:
            continue
        raw = raw_df[c]
        non_empty = raw.notna() & raw.astype(str).str.strip().ne("")
        invalid = non_empty & parsed_df[c].isna()
        if int(invalid.sum()) > 0:
            issues.append(
                _quality_issue(
                    code="invalid_date_values",
                    severity="warning",
                    message=f"Column '{c}' contains invalid date values.",
                    mask=invalid,
                )
            )

    if COL_ANIMAL_ID in parsed_df.columns:
        dup_mask = parsed_df[COL_ANIMAL_ID].duplicated(keep=False) & parsed_df[COL_ANIMAL_ID].notna()
        if int(dup_mask.sum()) > 0:
            issues.append(
                _quality_issue(
                    code="duplicate_animal_id",
                    severity="error",
                    message="Dataset contains duplicate animal identifiers.",
                    mask=dup_mask,
                )
            )

    if COL_LACTATION in parsed_df.columns and COL_LACTATION_START in parsed_df.columns:
        lact_zero_with_lact_start = (parsed_df[COL_LACTATION].fillna(0) == 0) & parsed_df[COL_LACTATION_START].notna()
        if int(lact_zero_with_lact_start.sum()) > 0:
            issues.append(
                _quality_issue(
                    code="inconsistent_lactation",
                    severity="warning",
                    message="Rows with lactation=0 contain lactation start date.",
                    mask=lact_zero_with_lact_start,
                )
            )
        lact_positive_without_start = (parsed_df[COL_LACTATION].fillna(0) > 0) & parsed_df[COL_LACTATION_START].isna()
        if int(lact_positive_without_start.sum()) > 0:
            issues.append(
                _quality_issue(
                    code="inconsistent_lactation",
                    severity="warning",
                    message="Rows with lactation>0 have no lactation start date.",
                    mask=lact_positive_without_start,
                )
            )

    if (
        report_date is not None
        and COL_ARCHIVE_DATE in parsed_df.columns
        and parsed_df[COL_ARCHIVE_DATE].notna().any()
    ):
        lower_bound = report_date - timedelta(days=730)
        old_archive = parsed_df[COL_ARCHIVE_DATE].notna() & (parsed_df[COL_ARCHIVE_DATE] < lower_bound)
        if int(old_archive.sum()) > 0:
            issues.append(
                _quality_issue(
                    code="archive_outside_730_days",
                    severity="warning",
                    message="Archived animals older than 730 days before report date are present.",
                    mask=old_archive,
                )
            )

    if COL_STATUS in parsed_df.columns:
        missing_status = parsed_df[COL_STATUS].isna() | parsed_df[COL_STATUS].astype(str).str.strip().eq("")
        if int(missing_status.sum()) > 0:
            issues.append(
                _quality_issue(
                    code="missing_status",
                    severity="warning",
                    message="Rows with empty status are present.",
                    mask=missing_status,
                )
            )

    return issues


def _validate_required_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise DatasetValidationError(
            "Missing required columns",
            error_code="MISSING_REQUIRED_COLUMNS",
            details={"missing_columns": missing},
        )


def _validate_numeric_columns(df: pd.DataFrame) -> None:
    if COL_ANIMAL_ID in df.columns:
        invalid_animal_id = df[COL_ANIMAL_ID].isna()
        if int(invalid_animal_id.sum()) > 0:
            raise DatasetValidationError(
                "Invalid animal identifiers",
                error_code="INVALID_ANIMAL_ID",
                details={"row_count": int(invalid_animal_id.sum()), "sample_rows": _sample_rows(invalid_animal_id)},
            )

    if COL_LACTATION in df.columns:
        invalid_lact = df[COL_LACTATION].isna()
        if int(invalid_lact.sum()) > 0:
            raise DatasetValidationError(
                "Invalid lactation values",
                error_code="INVALID_LACTATION",
                details={"row_count": int(invalid_lact.sum()), "sample_rows": _sample_rows(invalid_lact)},
            )


def load_dataset_df(buf: Union[str, io.BytesIO]) -> pd.DataFrame:
    raw_df = _normalize_columns(_read_csv_with_fallbacks(buf))
    _validate_required_columns(raw_df)
    parsed_df = _parse_dataset(raw_df)
    _validate_numeric_columns(parsed_df)

    parsed_df[COL_ANIMAL_ID] = parsed_df[COL_ANIMAL_ID].astype(int)
    parsed_df[COL_LACTATION] = parsed_df[COL_LACTATION].fillna(0).astype(int)
    return parsed_df


def load_dataset_with_quality(buf: Union[str, io.BytesIO]) -> DatasetLoadResult:
    raw_df = _normalize_columns(_read_csv_with_fallbacks(buf))
    _validate_required_columns(raw_df)
    parsed_df = _parse_dataset(raw_df)
    _validate_numeric_columns(parsed_df)
    parsed_df[COL_ANIMAL_ID] = parsed_df[COL_ANIMAL_ID].astype(int)
    parsed_df[COL_LACTATION] = parsed_df[COL_LACTATION].fillna(0).astype(int)

    report_date = suggest_report_date(parsed_df)
    issues = validate_dataset_quality(raw_df, parsed_df, report_date)
    return DatasetLoadResult(
        dataframe=parsed_df,
        quality_issues=issues,
        report_date_suggested=report_date,
    )


def suggest_report_date(df: pd.DataFrame) -> Optional[date]:
    if COL_LACTATION_START not in df.columns or COL_DAYS_IN_MILK not in df.columns:
        return None
    tmp = df[[COL_LACTATION_START, COL_DAYS_IN_MILK]].dropna()
    if len(tmp) == 0:
        return None
    starts = pd.to_datetime(tmp[COL_LACTATION_START], errors="coerce")
    dims = tmp[COL_DAYS_IN_MILK].astype(float)
    series = (starts + pd.to_timedelta(dims, unit="D")).dropna()
    if len(series) == 0:
        return None
    rep_ts = series.median()
    return rep_ts.date()
