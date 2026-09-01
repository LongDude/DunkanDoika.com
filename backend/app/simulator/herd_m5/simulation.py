from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple
import random

from .cows_with_death import Cow, cull_cow_combined
from .purchase import PurchaseLog, PurchasePolicyBase
from .samplers import IntSampler, sample_at_least


@dataclass
class DailyMetrics:
    day: date
    milking_count: int
    dry_count: int
    heifer_count: int
    pregnant_heifer_count: int
    avg_days_in_milk: float
    culled_count: int
    calvings_count: int = 0
    dryoffs_count: int = 0
    purchases_in_count: int = 0
    heifer_intros_count: int = 0


@dataclass
class ModelConfig:
    age_first_insem_days: IntSampler
    service_period_days: IntSampler
    conception_to_dry_days: IntSampler

    min_first_insem_age_days: int = 365
    voluntary_waiting_period: int = 50
    max_service_period_after_vwp: int = 300
    max_days_in_milk: int = 350
    overdue_event_spread_days: int = 21
    overdue_conception_probability_per_cycle: float = 0.20
    population_regulation: float = 1.0

    gestation_lo: int = 275
    gestation_hi: int = 280
    gestation_mu: float = 277.5
    gestation_sigma: float = 2.0

    heifer_birth_prob: float = 0.5

    purchased_days_to_calving_lo: int = 1
    purchased_days_to_calving_hi: int = 280

    def sample_gestation_days(self, rng: random.Random) -> int:
        x = int(round(rng.gauss(self.gestation_mu, self.gestation_sigma)))
        if x < self.gestation_lo:
            return self.gestation_lo
        if x > self.gestation_hi:
            return self.gestation_hi
        return x

    def sample_gestation_at_least(self, rng: random.Random, minimum: int) -> Optional[int]:
        minimum = max(int(minimum), int(self.gestation_lo))
        if minimum > self.gestation_hi:
            return None
        for _ in range(512):
            value = self.sample_gestation_days(rng)
            if value >= minimum:
                return value
        return None


class Simulation:
    def __init__(
        self,
        initial_cows: List[Cow],
        cfg: ModelConfig,
        start_date: date,
        file_path: str,
        purchase_policy: PurchasePolicyBase,
        manual_purchase_plan: Optional[List[Tuple[date, int]]] = None,
        random_seed: int = 42,
        record_monthly: bool = False,
    ):
        self.herd = initial_cows
        self.cfg = cfg
        self.today = start_date
        self.file_path = file_path
        self.rng = random.Random(random_seed)

        self.purchase_policy = purchase_policy
        self.manual_plan = {d: n for d, n in (manual_purchase_plan or [])}

        self.history: List[DailyMetrics] = []
        self.purchase_log = PurchaseLog()
        self.record_monthly = record_monthly

        self._culled_today = 0
        self._culled_since_last_record = 0
        self._calvings_today = 0
        self._calvings_since_last_record = 0
        self._dryoffs_today = 0
        self._dryoffs_since_last_record = 0
        self._purchases_today = 0
        self._purchases_since_last_record = 0
        self._heifer_intros_today = 0
        self._heifer_intros_since_last_record = 0

    def forecast_milking_count(self, future_day: date) -> int:
        cnt = 0
        for cow in self.herd:
            st = self._projected_status(cow, future_day)
            if st in ("fresh", "ready_for_breeding", "pregnant"):
                cnt += 1
        return cnt

    def _projected_status(self, cow: Cow, future_day: date) -> str:
        if cow.status == "culled":
            return "culled"
        projected_conception_date = cow.conception_date
        if (
            projected_conception_date is None
            and cow.planned_conception_date is not None
            and cow.planned_conception_date <= future_day
        ):
            projected_conception_date = cow.planned_conception_date
        if (
            projected_conception_date is None
            and cow.status == "heifer"
            and cow.planned_first_insem_date is not None
            and cow.planned_first_insem_date <= future_day
        ):
            projected_conception_date = cow.planned_first_insem_date

        projected_calving_date = cow.planned_calving_date
        if projected_calving_date is None and projected_conception_date is not None:
            gestation = int(round(self.cfg.gestation_mu))
            gestation = min(self.cfg.gestation_hi, max(self.cfg.gestation_lo, gestation))
            projected_calving_date = max(
                projected_conception_date + timedelta(days=gestation),
                self.today,
            )
        if projected_calving_date and future_day >= projected_calving_date:
            if (future_day - projected_calving_date).days > self.cfg.max_days_in_milk:
                return "culled"
            return "fresh"
        if cow.planned_dry_date and future_day >= cow.planned_dry_date:
            return "dry"
        if cow.is_milking():
            if cow.last_calving_date is not None:
                projected_dim = (future_day - cow.last_calving_date).days
            else:
                projected_dim = cow.days_in_milk + max(0, (future_day - self.today).days)
            if projected_dim > self.cfg.max_days_in_milk:
                return "dry" if projected_conception_date is not None else "culled"
        if projected_conception_date is not None:
            return "pregnant"
        if cow.status == "heifer":
            if cow.planned_first_insem_date and future_day >= cow.planned_first_insem_date:
                return "pregnant_heifer"
            return "heifer"
        if cow.status == "pregnant_heifer":
            return "pregnant_heifer"
        return cow.status

    def step_day(self) -> None:
        self._culled_today = 0
        self._calvings_today = 0
        self._dryoffs_today = 0
        self._purchases_today = 0
        self._heifer_intros_today = 0

        manual_cnt = self.manual_plan.get(self.today, 0)
        purchase_cnt = self.purchase_policy.purchases_today(self, manual_cnt)
        if purchase_cnt > 0:
            mode_name = self.purchase_policy.__class__.__name__
            if mode_name == "ManualPurchasePolicy":
                mode = "manual"
            elif mode_name == "AutoCounterPurchasePolicy":
                mode = "auto_counter"
            else:
                mode = "auto_forecast"
            self._buy_pregnant_heifers(purchase_cnt, mode=mode)

        new_animals: List[Cow] = []
        culled_ids: set[str] = set()

        for cow in self.herd:
            if cull_cow_combined(
                cow,
                self.today,
                self.file_path,
                rng=self.rng,
                population_regulation=self.cfg.population_regulation,
            ):
                cow.status = "culled"
                culled_ids.add(cow.id)
                self.purchase_policy.on_removed(1)
                self._culled_today += 1
                self._culled_since_last_record += 1
                continue

            # DIM is a state constraint, not a value to clamp in the report.
            # At the first day after reaching the limit a pregnant cow is
            # dried off; an open cow leaves the herd as a non-conceiver.
            if cow.is_milking() and cow.days_in_milk >= self.cfg.max_days_in_milk:
                if cow.status == "pregnant":
                    self._ensure_pregnancy_schedule(cow)
                    if cow.planned_calving_date and self.today >= cow.planned_calving_date:
                        self._do_calving(cow, new_animals)
                    else:
                        self._dry_off(cow)
                else:
                    self._cull(cow, culled_ids)
                    continue

            if cow.status == "heifer":
                self._tick_heifer(cow)
            elif cow.status == "pregnant_heifer":
                self._tick_pregnant_heifer(cow, new_animals)
            elif cow.status == "fresh":
                self._tick_fresh(cow, culled_ids)
            elif cow.status == "ready_for_breeding":
                self._tick_ready_for_breeding(cow, culled_ids)
            elif cow.status == "pregnant":
                self._tick_pregnant(cow, new_animals)
            elif cow.status == "dry":
                self._tick_dry(cow, new_animals)

            if cow.is_milking() and cow.last_calving_date != self.today:
                cow.days_in_milk += 1
            cow.days_in_current_status += 1

        if culled_ids:
            self.herd = [c for c in self.herd if c.id not in culled_ids]

        if new_animals:
            self.herd.extend(new_animals)
            self.purchase_policy.on_added(len(new_animals))

        if (not self.record_monthly) or (self.today.day == 1):
            self._record_metrics()

        self.today += timedelta(days=1)

    def _tick_heifer(self, cow: Cow) -> None:
        if cow.planned_first_insem_date is None:
            current_age = max(0, (self.today - cow.birth_date).days)
            minimum_age = max(self.cfg.min_first_insem_age_days, current_age)
            age = sample_at_least(self.cfg.age_first_insem_days, self.rng, minimum_age)
            if age is None:
                # The animal is beyond the observed support. Model repeated
                # oestrous cycles instead of guaranteeing conception during
                # the first cycle and creating an artificial calving wave.
                wait = self._sample_overdue_conception_wait()
                cow.planned_first_insem_date = self.today + timedelta(days=wait)
            else:
                cow.planned_first_insem_date = cow.birth_date + timedelta(days=age)

        if self.today >= cow.planned_first_insem_date:
            cow.status = "pregnant_heifer"
            cow.conception_date = self.today
            cow.days_in_current_status = 0
            gd = self.cfg.sample_gestation_days(self.rng)
            cow.planned_calving_date = self.today + timedelta(days=gd)

    def _tick_pregnant_heifer(self, cow: Cow, new_animals: List[Cow]) -> None:
        self._ensure_calving_schedule(cow)
        if cow.planned_calving_date and self.today >= cow.planned_calving_date:
            self._do_calving(cow, new_animals)

    def _tick_fresh(self, cow: Cow, culled_ids: set[str]) -> None:
        elapsed_since_calving = (
            (self.today - cow.last_calving_date).days
            if cow.last_calving_date is not None
            else cow.days_in_current_status
        )
        if elapsed_since_calving >= self.cfg.voluntary_waiting_period:
            cow.status = "ready_for_breeding"
            cow.days_in_current_status = 0
            self._tick_ready_for_breeding(cow, culled_ids)

    def _tick_ready_for_breeding(self, cow: Cow, culled_ids: set[str]) -> None:
        elapsed_after_vwp = cow.days_in_current_status
        if cow.last_calving_date is not None:
            elapsed_after_vwp = max(
                elapsed_after_vwp,
                (self.today - cow.last_calving_date).days - self.cfg.voluntary_waiting_period,
            )
        if elapsed_after_vwp >= self.cfg.max_service_period_after_vwp:
            self._cull(cow, culled_ids)
            return

        if cow.planned_conception_date is None:
            if cow.last_calving_date is None:
                wait = self._sample_overdue_conception_wait()
                cow.planned_conception_date = self.today + timedelta(days=wait)
            else:
                elapsed = max(0, (self.today - cow.last_calving_date).days)
                minimum_sp = max(self.cfg.voluntary_waiting_period, elapsed)
                sp = sample_at_least(self.cfg.service_period_days, self.rng, minimum_sp)
                if sp is None:
                    wait = self._sample_overdue_conception_wait()
                    cow.planned_conception_date = self.today + timedelta(days=wait)
                else:
                    cow.planned_conception_date = cow.last_calving_date + timedelta(days=sp)

        if self.today >= cow.planned_conception_date:
            cow.status = "pregnant"
            cow.conception_date = self.today
            cow.planned_conception_date = None
            cow.days_in_current_status = 0

            gd = self.cfg.sample_gestation_days(self.rng)
            cow.planned_calving_date = self.today + timedelta(days=gd)

            dtd = self.cfg.conception_to_dry_days.sample(self.rng)
            cow.planned_dry_date = self.today + timedelta(days=dtd)
            if cow.last_calving_date is not None:
                dim_limit_date = cow.last_calving_date + timedelta(days=self.cfg.max_days_in_milk + 1)
                if cow.planned_dry_date > dim_limit_date:
                    cow.planned_dry_date = dim_limit_date
            if cow.planned_dry_date >= cow.planned_calving_date:
                cow.planned_dry_date = cow.planned_calving_date - timedelta(days=1)

    def _tick_pregnant(self, cow: Cow, new_animals: List[Cow]) -> None:
        self._ensure_pregnancy_schedule(cow)
        if cow.planned_calving_date and self.today >= cow.planned_calving_date:
            self._do_calving(cow, new_animals)
            return
        if cow.planned_dry_date and self.today >= cow.planned_dry_date:
            self._dry_off(cow)

    def _tick_dry(self, cow: Cow, new_animals: List[Cow]) -> None:
        self._ensure_calving_schedule(cow)
        if cow.planned_calving_date and self.today >= cow.planned_calving_date:
            self._do_calving(cow, new_animals)

    def _ensure_pregnancy_schedule(self, cow: Cow) -> None:
        self._ensure_calving_schedule(cow)
        if cow.planned_dry_date is not None or cow.conception_date is None:
            return

        elapsed = max(0, (self.today - cow.conception_date).days)
        dtd = sample_at_least(self.cfg.conception_to_dry_days, self.rng, elapsed)
        cow.planned_dry_date = self.today if dtd is None else cow.conception_date + timedelta(days=dtd)

        if cow.last_calving_date is not None:
            dim_limit_date = cow.last_calving_date + timedelta(days=self.cfg.max_days_in_milk + 1)
            if cow.planned_dry_date > dim_limit_date:
                cow.planned_dry_date = dim_limit_date
        if cow.planned_calving_date and cow.planned_dry_date >= cow.planned_calving_date:
            cow.planned_dry_date = cow.planned_calving_date - timedelta(days=1)

    def _sample_overdue_conception_wait(self) -> int:
        cycle_days = max(1, int(self.cfg.overdue_event_spread_days))
        probability = min(1.0, max(0.001, float(self.cfg.overdue_conception_probability_per_cycle)))
        failed_cycles = 0
        while failed_cycles < 10_000 and self.rng.random() >= probability:
            failed_cycles += 1
        return failed_cycles * cycle_days + self.rng.randint(1, cycle_days)

    def _ensure_calving_schedule(self, cow: Cow) -> None:
        if cow.planned_calving_date is not None:
            return

        if cow.conception_date is not None:
            elapsed = max(0, (self.today - cow.conception_date).days)
            gestation = self.cfg.sample_gestation_at_least(self.rng, elapsed)
            cow.planned_calving_date = (
                self.today if gestation is None else cow.conception_date + timedelta(days=gestation)
            )
            return

        if cow.status == "dry" and cow.dry_date is not None:
            gestation = self.cfg.sample_gestation_days(self.rng)
            dtd = max(1, self.cfg.conception_to_dry_days.sample(self.rng))
            remaining = max(1, gestation - dtd)
            candidate = cow.dry_date + timedelta(days=remaining)
            cow.planned_calving_date = max(candidate, self.today)

    def _dry_off(self, cow: Cow) -> None:
        if cow.status == "dry":
            return
        cow.status = "dry"
        cow.dry_date = self.today
        cow.days_in_current_status = 0
        self._dryoffs_today += 1
        self._dryoffs_since_last_record += 1

    def _cull(self, cow: Cow, culled_ids: set[str]) -> None:
        if cow.id in culled_ids:
            return
        cow.status = "culled"
        culled_ids.add(cow.id)
        self.purchase_policy.on_removed(1)
        self._culled_today += 1
        self._culled_since_last_record += 1

    def _do_calving(self, cow: Cow, new_animals: List[Cow]) -> None:
        self._calvings_today += 1
        self._calvings_since_last_record += 1
        if self.rng.random() < self.cfg.heifer_birth_prob:
            new_animals.append(
                Cow(
                    id=f"BORN_{self.today.isoformat()}_{len(new_animals)}",
                    birth_date=self.today,
                    status="heifer",
                )
            )
        cow.reset_for_new_lactation(self.today)

    def _buy_pregnant_heifers(self, count: int, mode: str) -> None:
        if count <= 0:
            return

        self._purchases_today += count
        self._purchases_since_last_record += count

        if mode == "manual":
            self.purchase_log.manual.append((self.today, count))
        elif mode == "auto_counter":
            self.purchase_log.auto_counter.append((self.today, count))
        else:
            self.purchase_log.auto_forecast.append((self.today, count))

        for i in range(count):
            days_to_calving = self.rng.randint(
                self.cfg.purchased_days_to_calving_lo,
                self.cfg.purchased_days_to_calving_hi,
            )
            calving_date = self.today + timedelta(days=days_to_calving)

            gd = self.cfg.sample_gestation_days(self.rng)
            conception_date = calving_date - timedelta(days=gd)

            age_insem = self.cfg.age_first_insem_days.sample(self.rng)
            if age_insem < self.cfg.min_first_insem_age_days:
                age_insem = self.cfg.min_first_insem_age_days
            birth = conception_date - timedelta(days=age_insem)

            cow = Cow(
                id=f"PURCHASE_{self.today.isoformat()}_{i}",
                birth_date=birth,
                status="pregnant_heifer",
                lactation_number=0,
                conception_date=conception_date,
                planned_calving_date=calving_date,
            )
            self.herd.append(cow)
            self.purchase_policy.on_added(1)

    def _record_metrics(self) -> None:
        milking = dry = heifer = preg_heifer = 0
        dim_sum = 0

        if self.record_monthly:
            culled_value = self._culled_since_last_record
            calvings_value = self._calvings_since_last_record
            dryoffs_value = self._dryoffs_since_last_record
            purchases_value = self._purchases_since_last_record
            heifer_intros_value = self._heifer_intros_since_last_record
        else:
            culled_value = self._culled_today
            calvings_value = self._calvings_today
            dryoffs_value = self._dryoffs_today
            purchases_value = self._purchases_today
            heifer_intros_value = self._heifer_intros_today

        for c in self.herd:
            if c.status == "dry":
                dry += 1
            elif c.status == "heifer":
                heifer += 1
            elif c.status == "pregnant_heifer":
                preg_heifer += 1
            if c.is_milking():
                milking += 1
                dim_sum += c.days_in_milk

        avg_dim = (dim_sum / milking) if milking else 0.0

        self.history.append(
            DailyMetrics(
                day=self.today,
                milking_count=milking,
                dry_count=dry,
                heifer_count=heifer,
                pregnant_heifer_count=preg_heifer,
                avg_days_in_milk=avg_dim,
                culled_count=culled_value,
                calvings_count=calvings_value,
                dryoffs_count=dryoffs_value,
                purchases_in_count=purchases_value,
                heifer_intros_count=heifer_intros_value,
            )
        )

        if self.record_monthly:
            self._culled_since_last_record = 0
            self._calvings_since_last_record = 0
            self._dryoffs_since_last_record = 0
            self._purchases_since_last_record = 0
            self._heifer_intros_since_last_record = 0

    def run(self, days: int) -> List[DailyMetrics]:
        for _ in range(days):
            self.step_day()
        return self.history
