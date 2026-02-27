from __future__ import annotations

import io

import pandas as pd

from app.api.schemas import ForecastResult


def export_forecast_csv(res: ForecastResult) -> str:
    """UTF‑8 CSV with two sections: SERIES and EVENTS."""

    def series_df(tag: str, s) -> pd.DataFrame:
        if s is None:
            return pd.DataFrame()
        df = pd.DataFrame([p.model_dump() for p in s.points])
        df = df.rename(columns={"avg_days_in_milk": f"avg_days_in_milk_{tag}"})
        return df[[
            "date",
            "milking_count",
            "dry_count",
            "heifer_count",
            "pregnant_heifer_count",
            f"avg_days_in_milk_{tag}",
        ]]

    df50 = series_df("p50", res.series_p50)
    df10 = series_df("p10", res.series_p10)
    df90 = series_df("p90", res.series_p90)

    df = df50
    if not df10.empty:
        df = df.merge(df10[["date", "avg_days_in_milk_p10"]], on="date", how="left")
    if not df90.empty:
        df = df.merge(df90[["date", "avg_days_in_milk_p90"]], on="date", how="left")

    ev = pd.DataFrame([e.model_dump() for e in res.events])
    fut = pd.DataFrame([res.future_point.model_dump()]) if res.future_point is not None else pd.DataFrame()

    buf = io.StringIO()
    buf.write("[SERIES]\n")
    df.to_csv(buf, index=False)
    buf.write("\n[EVENTS]\n")
    ev.to_csv(buf, index=False)
    buf.write("\n[FUTURE]\n")
    fut.to_csv(buf, index=False)
    return buf.getvalue()


def export_forecast_xlsx(res: ForecastResult) -> bytes:
    """XLSX with Series/Events/Future sheets."""
    out = io.BytesIO()

    def series_df(tag: str, s) -> pd.DataFrame:
        if s is None:
            return pd.DataFrame()
        df = pd.DataFrame([p.model_dump() for p in s.points])
        df = df.rename(columns={"avg_days_in_milk": f"avg_days_in_milk_{tag}"})
        return df

    df50 = series_df("p50", res.series_p50)
    df10 = series_df("p10", res.series_p10)
    df90 = series_df("p90", res.series_p90)

    df = df50
    if not df10.empty:
        df = df.merge(df10[["date", "avg_days_in_milk_p10"]], on="date", how="left")
    if not df90.empty:
        df = df.merge(df90[["date", "avg_days_in_milk_p90"]], on="date", how="left")

    ev = pd.DataFrame([e.model_dump() for e in res.events])
    fut = pd.DataFrame([res.future_point.model_dump()]) if res.future_point is not None else pd.DataFrame()

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Series", index=False)
        ev.to_excel(writer, sheet_name="Events", index=False)
        fut.to_excel(writer, sheet_name="Future", index=False)

    return out.getvalue()
