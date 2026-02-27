from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Optional, Tuple, List
import math

import numpy as np
import pandas as pd

from app.simulator.types import Animal, Status

@dataclass
class ServicePeriodPolicy:
    mean_days: int = 115
    std_days: int = 10
    min_days_after_calving: int = 50

    def sample_success_insem_date(self, rng: np.random.Generator, animal: Animal, report_date: date) -> date:
        """Return a FUTURE or report_date-aligned expected success insemination date."""
        if animal.last_calving_date is None:
            # if no calving yet (heifer), shouldn't be here
            return report_date
        sp = int(max(self.min_days_after_calving, rng.normal(self.mean_days, self.std_days) if self.std_days > 0 else self.mean_days))
        target = animal.last_calving_date + timedelta(days=sp)
        if target <= report_date:
            # already overdue; push into near future (0..30 days)
            target = report_date + timedelta(days=int(rng.integers(0, 31)))
        return target

@dataclass
class HeiferInsemPolicy:
    min_age_days: int = 365
    max_age_days: int = 395

    def sample_first_success_insem(self, rng: np.random.Generator, birth_date: date, report_date: date) -> date:
        age = int(rng.integers(self.min_age_days, self.max_age_days + 1))
        target = birth_date + timedelta(days=age)
        if target <= report_date:
            target = report_date + timedelta(days=int(rng.integers(0, 31)))
        return target

@dataclass
class CullingPolicy:
    monthly_hazard_by_group: Dict[str, float]
    fallback_monthly_hazard: float = 0.008

    @staticmethod
    def _lact_group(lact: int) -> str:
        if lact <= 0:
            return "L0"
        if lact == 1:
            return "L1"
        if lact == 2:
            return "L2"
        if lact == 3:
            return "L3"
        return "L4+"

    @staticmethod
    def _status_group(status: str) -> str:
        s = (status or "").strip().lower()
        if "тел" in s:  # телка
            return "heifer"
        if "сухост" in s:
            return "dry"
        if "стель" in s:
            return "pregnant"
        if "осемен" in s:
            return "inseminated"
        if "новот" in s:
            return "fresh"
        return "other"

    @classmethod
    def estimate_from_dataset(
        cls,
        df: pd.DataFrame,
        report_date: date,
        fallback_monthly_hazard: float = 0.008,
        grouping: str = "lactation",
        age_band_years: int = 2,
    ) -> "CullingPolicy":
        """
        Estimate simple monthly hazard from:
        - culled within [report_date-730, report_date] as events
        - alive on report_date as at-risk
        This is a heuristic (good enough for MVP).
        """
        window_start = report_date - timedelta(days=730)
        df = df.copy()
        df["archive"] = pd.to_datetime(df["Дата архива"], errors="coerce")
        def grp_row(row) -> str:
            lact = int(row.get("Лактация", 0)) if pd.notna(row.get("Лактация", 0)) else 0
            if grouping == "lactation_status":
                st = cls._status_group(str(row.get("Статус коровы", "")))
                return f"{cls._lact_group(lact)}|{st}"
            if grouping == "age_band":
                b = row.get("Дата рождения")
                if pd.isna(b):
                    return "age_unknown"
                age_years = max(0.0, (report_date - pd.to_datetime(b).date()).days / 365.25)
                band = int(age_years // max(1, age_band_years))
                return f"age_{band * age_band_years}-{(band + 1) * age_band_years}"
            return cls._lact_group(lact)

        df["grp"] = df.apply(grp_row, axis=1)

        culled = df[(df["archive"].notna()) & (df["archive"].dt.date >= window_start) & (df["archive"].dt.date <= report_date)]
        alive = df[(df["archive"].isna()) | (df["archive"].dt.date > report_date)]

        hazards: Dict[str, float] = {}
        for g in sorted(df["grp"].unique()):
            c = int((culled["grp"] == g).sum())
            a = int((alive["grp"] == g).sum())
            if a + c < 30:
                hazards[g] = fallback_monthly_hazard
                continue
            # exposure ≈ (a + c/2) * 24 months (2-year window) => culled / exposure
            exposure_months = max(1.0, (a + 0.5 * c) * 24.0)
            h = c / exposure_months
            hazards[g] = float(min(0.2, max(0.0, h)))
        return cls(monthly_hazard_by_group=hazards, fallback_monthly_hazard=fallback_monthly_hazard)

    def sample_cull_date(self, rng: np.random.Generator, animal: Animal, start_date: date, end_date: date) -> Optional[date]:
        """Geometric monthly trial. Returns date or None."""
        hazard = self.monthly_hazard_by_group.get(self._lact_group(animal.lactation_no), self.fallback_monthly_hazard)
        if hazard <= 0:
            return None
        # Iterate month by month
        cur = date(start_date.year, start_date.month, 1)
        # ensure cur <= start_date
        if cur < start_date.replace(day=1):
            cur = start_date.replace(day=1)

        while cur < end_date:
            if rng.random() < hazard:
                # random day inside this month
                day = int(rng.integers(1, 29))  # safe day for all months
                d = date(cur.year, cur.month, day)
                if d < start_date:
                    d = start_date
                return d
            # next month
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)
        return None

@dataclass
class ReplacementPolicy:
    enabled: bool = True
    annual_heifer_ratio: float = 0.30
    lookahead_months: int = 12

    def target_first_calvings_next_year(self, milking_count: int) -> int:
        return int(round(self.annual_heifer_ratio * milking_count))

