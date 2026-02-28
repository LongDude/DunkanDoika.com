from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np

from app.simulator.types import Animal, Event, EventType, Status
from app.simulator.policies import ServicePeriodPolicy, HeiferInsemPolicy, CullingPolicy, ReplacementPolicy

@dataclass
class EngineConfig:
    report_date: date
    horizon_end: date
    service_policy: ServicePeriodPolicy
    heifer_policy: HeiferInsemPolicy
    cull_policy: CullingPolicy
    replacement_policy: ReplacementPolicy
    dim_mode: Literal["from_calving", "from_dataset_field"] = "from_calving"

@dataclass
class MonthlyEvents:
    month_start: date
    calvings: int = 0
    dryoffs: int = 0
    culls: int = 0
    purchases_in: int = 0
    heifer_intros: int = 0

class SimulationEngine:
    def __init__(self, animals: Dict[int, Animal], rng: np.random.Generator, cfg: EngineConfig):
        self.animals = animals
        self.rng = rng
        self.cfg = cfg

        self._seq = 0
        self._q: List[Event] = []
        self._max_id = max(animals.keys()) if animals else 0

        # month -> MonthlyEvents
        self.month_events: Dict[date, MonthlyEvents] = {}

    def push(self, time: date, et: EventType, animal_id: Optional[int] = None, payload: Optional[dict] = None):
        self._seq += 1
        heapq.heappush(self._q, Event(time=time, seq=self._seq, type=et, animal_id=animal_id, payload=payload))

    def pop_ready(self, until: date) -> List[Event]:
        out = []
        while self._q and self._q[0].time <= until:
            out.append(heapq.heappop(self._q))
        return out

    def _month_start(self, d: date) -> date:
        return date(d.year, d.month, 1)

    def _bump_month_counter(self, d: date, field: str, amount: int = 1):
        m = self._month_start(d)
        if m not in self.month_events:
            self.month_events[m] = MonthlyEvents(month_start=m)
        setattr(self.month_events[m], field, getattr(self.month_events[m], field) + amount)

    def schedule_auto_for_animal_if_needed(self, animal: Animal, now: date):
        # If alive and not pregnant, schedule success insemination depending on type
        if not animal.is_alive_on(now):
            return
        if animal.success_insem_date is not None and animal.next_calving_date is not None and animal.next_calving_date > now:
            return  # already pregnant

        # already scheduled
        if animal.planned_success_insem_date is not None and animal.planned_success_insem_date > now:
            return

        if animal.lactation_no == 0:
            if animal.status in (Status.HEIFER, Status.PREGNANT_HEIFER):
                if animal.status == Status.HEIFER:
                    s = self.cfg.heifer_policy.sample_first_success_insem(self.rng, animal.birth_date, now)
                    self.push(s, EventType.SUCCESS_INSEM, animal.animal_id)
                    animal.planned_success_insem_date = s
        else:
            if animal.status in (Status.MILKING, Status.DRY):
                s = self.cfg.service_policy.sample_success_insem_date(self.rng, animal, now)
                self.push(s, EventType.SUCCESS_INSEM, animal.animal_id)
                animal.planned_success_insem_date = s

    def schedule_cull_if_needed(self, animal: Animal, now: date):
        if not animal.is_alive_on(now):
            return
        if animal.archive_date is not None:
            return
        if animal.planned_cull_date is not None and animal.planned_cull_date > now:
            return
        d = self.cfg.cull_policy.sample_cull_date(self.rng, animal, now, self.cfg.horizon_end)
        if d is not None:
            self.push(d, EventType.CULL, animal.animal_id)
            animal.planned_cull_date = d

    def init_schedules(self, now: date):
        # schedule culls + inseminations for all animals
        for a in self.animals.values():
            self.schedule_cull_if_needed(a, now)
            self.schedule_auto_for_animal_if_needed(a, now)

    def _handle_success_insem(self, a: Animal, t: date):
        if not a.is_alive_on(t):
            return
        # ignore if already pregnant with future calving
        if a.success_insem_date is not None and a.next_calving_date is not None and a.next_calving_date > t:
            return
        a.planned_success_insem_date = None
        a.success_insem_date = t

        # Schedule dryoff and calving by rules (220/280)
        calving = t + timedelta(days=280)
        a.next_calving_date = calving
        self.push(calving, EventType.CALVING, a.animal_id)

        # For cows in lactation: dryoff at +220
        if a.lactation_no > 0:
            dryoff = t + timedelta(days=220)
            a.dryoff_date = dryoff  # expected (will be applied on event)
            self.push(dryoff, EventType.DRYOFF, a.animal_id)
        else:
            a.status = Status.PREGNANT_HEIFER

    def _handle_dryoff(self, a: Animal, t: date):
        if not a.is_alive_on(t):
            return
        # ensure dryoff date set
        a.dryoff_date = t
        a.status = Status.DRY
        self._bump_month_counter(t, "dryoffs")

    def _create_calf_if_female(self, t: date):
        # 50/50
        if self.rng.random() < 0.5:
            self._max_id += 1
            calf = Animal(
                animal_id=self._max_id,
                birth_date=t,
                lactation_no=0,
                status=Status.HEIFER,
            )
            self.animals[calf.animal_id] = calf
            # schedule its reproduction & cull
            self.schedule_cull_if_needed(calf, t)
            self.schedule_auto_for_animal_if_needed(calf, t)

    def _handle_calving(self, a: Animal, t: date):
        if not a.is_alive_on(t):
            return

        # Transition to milking
        a.status = Status.MILKING
        a.lactation_no = max(0, a.lactation_no) + 1
        a.last_calving_date = t

        # Pregnancy ends
        a.success_insem_date = None
        a.next_calving_date = None
        a.dryoff_date = None
        a.planned_success_insem_date = None
        a.dim_anchor_date = t
        a.dim_anchor_value = 0

        self._bump_month_counter(t, "calvings")

        # Birth
        self._create_calf_if_female(t)

        # Schedule next insemination for this cow
        self.schedule_auto_for_animal_if_needed(a, t)

    def _handle_cull(self, a: Animal, t: date):
        if not a.is_alive_on(t):
            return
        a.status = Status.ARCHIVED
        a.archive_date = t
        a.planned_cull_date = None
        self._bump_month_counter(t, "culls")

    def _handle_purchase_in(self, t: date, payload: dict):
        count = int(payload.get("count", 0))
        self._bump_month_counter(t, "purchases_in", count)
        self._create_pregnant_heifers(t, payload, count=count)

    def _handle_heifer_intro(self, t: date, payload: dict):
        count = int(payload.get("count", 0))
        self._bump_month_counter(t, "heifer_intros", count)
        self._create_pregnant_heifers(t, payload, count=count)

    def _create_pregnant_heifers(self, t: date, payload: dict, count: int):
        expected_calving_date = payload.get("expected_calving_date")
        expected_calving_dates = payload.get("expected_calving_dates")
        days_pregnant = payload.get("days_pregnant")

        for i in range(count):
            self._max_id += 1
            h = Animal(
                animal_id=self._max_id,
                birth_date=t - timedelta(days=500),
                lactation_no=0,
                status=Status.PREGNANT_HEIFER,
            )

            if expected_calving_dates is not None:
                calving = expected_calving_dates[min(i, len(expected_calving_dates) - 1)]
                success = calving - timedelta(days=280)
            elif expected_calving_date is not None:
                calving = expected_calving_date
                success = calving - timedelta(days=280)
            elif days_pregnant is not None:
                success = t - timedelta(days=int(days_pregnant))
                calving = success + timedelta(days=280)
            else:
                calving = t + timedelta(days=int(self.rng.integers(120, 241)))
                success = calving - timedelta(days=280)

            h.success_insem_date = success
            h.next_calving_date = calving

            self.animals[h.animal_id] = h
            self.push(calving, EventType.CALVING, h.animal_id)
            self.schedule_cull_if_needed(h, t)

    def step_events_until(self, until: date):
        for ev in self.pop_ready(until):
            if ev.type in (EventType.PURCHASE_IN, EventType.HEIFER_INTRO):
                if ev.type == EventType.PURCHASE_IN:
                    self._handle_purchase_in(ev.time, ev.payload or {})
                else:
                    self._handle_heifer_intro(ev.time, ev.payload or {})
                continue

            if ev.animal_id is None:
                continue
            a = self.animals.get(ev.animal_id)
            if a is None:
                continue

            if ev.type == EventType.SUCCESS_INSEM:
                self._handle_success_insem(a, ev.time)
            elif ev.type == EventType.DRYOFF:
                self._handle_dryoff(a, ev.time)
            elif ev.type == EventType.CALVING:
                self._handle_calving(a, ev.time)
            elif ev.type == EventType.CULL:
                self._handle_cull(a, ev.time)

    def counts_on(self, d: date) -> Tuple[int, int, int, int]:
        milking = 0
        dry = 0
        heifer = 0
        preg_heifer = 0
        for a in self.animals.values():
            if not a.is_alive_on(d):
                continue
            if a.lactation_no == 0:
                if a.status == Status.PREGNANT_HEIFER:
                    preg_heifer += 1
                else:
                    heifer += 1
            else:
                if a.in_dry_on(d) or a.status == Status.DRY:
                    dry += 1
                elif a.in_milking_on(d) or a.status == Status.MILKING:
                    milking += 1
        return milking, dry, heifer, preg_heifer

    def avg_days_in_milk_on(self, d: date) -> Optional[float]:
        def estimate_dim(animal: Animal) -> Optional[int]:
            if self.cfg.dim_mode == "from_dataset_field":
                if animal.dim_anchor_date is not None and animal.dim_anchor_value is not None:
                    return max(0, int(animal.dim_anchor_value + (d - animal.dim_anchor_date).days))
            if animal.last_calving_date is None:
                return None
            return max(0, (d - animal.last_calving_date).days)

        total = 0
        n = 0
        for a in self.animals.values():
            if a.in_milking_on(d):
                dim = estimate_dim(a)
                if dim is None:
                    continue
                total += dim
                n += 1
        if n == 0:
            return None
        return total / n

    def apply_replacement_policy(self, d: date):
        rp = self.cfg.replacement_policy
        if not rp.enabled:
            return

        milking, _, _, _ = self.counts_on(d)
        target = rp.target_first_calvings_next_year(milking)
        if target <= 0:
            return

        # Count scheduled first-calvings in the next lookahead window
        lookahead_end = d + timedelta(days=30 * rp.lookahead_months)
        scheduled = 0
        for a in self.animals.values():
            if not a.is_alive_on(d):
                continue
            if a.lactation_no == 0 and a.next_calving_date is not None and d < a.next_calving_date <= lookahead_end:
                scheduled += 1

        deficit = target - scheduled
        if deficit <= 0:
            return

        # Introduce deficit pregnant heifers with calvings spread across the lookahead window
        calvings = [
            d + timedelta(days=int(self.rng.integers(30, 30 * rp.lookahead_months + 1)))
            for _ in range(deficit)
        ]
        self.push(d, EventType.HEIFER_INTRO, None, payload={"count": deficit, "expected_calving_dates": calvings})

    def run(self, snapshot_dates: List[date]) -> List[dict]:
        out = []
        for snap in snapshot_dates:
            self.step_events_until(snap)
            # Apply replacement at month starts for stability
            if snap.day == 1:
                self.apply_replacement_policy(snap)
                # apply immediate intros scheduled on the same date
                self.step_events_until(snap)

            milking, dry, heifer, preg_heifer = self.counts_on(snap)
            avg_dim = self.avg_days_in_milk_on(snap)
            out.append({
                "date": snap,
                "milking_count": milking,
                "dry_count": dry,
                "heifer_count": heifer,
                "pregnant_heifer_count": preg_heifer,
                "avg_days_in_milk": avg_dim,
            })
        return out
