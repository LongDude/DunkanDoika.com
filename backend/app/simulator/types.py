from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Dict, Any

class Status(str, Enum):
    HEIFER = "heifer"
    PREGNANT_HEIFER = "pregnant_heifer"
    MILKING = "milking"
    DRY = "dry"
    ARCHIVED = "archived"

class EventType(str, Enum):
    SUCCESS_INSEM = "SUCCESS_INSEM"
    DRYOFF = "DRYOFF"
    CALVING = "CALVING"
    CULL = "CULL"
    PURCHASE_IN = "PURCHASE_IN"
    HEIFER_INTRO = "HEIFER_INTRO"

@dataclass
class Animal:
    animal_id: int
    birth_date: date
    lactation_no: int = 0
    status: Status = Status.HEIFER

    last_calving_date: Optional[date] = None
    success_insem_date: Optional[date] = None
    dryoff_date: Optional[date] = None
    archive_date: Optional[date] = None

    # convenience: next planned calving (if pregnant)
    next_calving_date: Optional[date] = None

    # internal: prevent duplicate scheduling
    planned_success_insem_date: Optional[date] = None
    planned_cull_date: Optional[date] = None
    # Anchor for DIM calculation when mode uses dataset DIM as baseline.
    dim_anchor_date: Optional[date] = None
    dim_anchor_value: Optional[int] = None

    def is_alive_on(self, d: date) -> bool:
        return self.archive_date is None or self.archive_date > d

    def in_milking_on(self, d: date) -> bool:
        if not self.is_alive_on(d):
            return False
        if self.lactation_no <= 0 or self.last_calving_date is None:
            return False
        if self.dryoff_date is not None and self.dryoff_date <= d:
            return False
        return self.last_calving_date <= d

    def in_dry_on(self, d: date) -> bool:
        if not self.is_alive_on(d):
            return False
        if self.dryoff_date is None:
            return False
        return self.dryoff_date <= d and (self.next_calving_date is None or d < self.next_calving_date)

@dataclass(order=True)
class Event:
    time: date
    seq: int
    type: EventType
    animal_id: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
