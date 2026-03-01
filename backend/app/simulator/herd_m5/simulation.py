from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple
import random

from .cows_with_death import Cow, cull_cow_combined
from .purchase import PurchaseLog, PurchasePolicyBase
from .samplers import IntSampler


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
        if cow.planned_calving_date and future_day >= cow.planned_calving_date:
            return "fresh"
        if cow.planned_dry_date and future_day >= cow.planned_dry_date:
            return "dry"
        if cow.conception_date is not None and cow.planned_calving_date is not None:
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
        auto_cnt = self.purchase_policy.purchases_today(self, manual_cnt)

        if manual_cnt > 0:
            self._buy_pregnant_heifers(manual_cnt, mode="manual")
        if auto_cnt > 0:
            mode_name = self.purchase_policy.__class__.__name__
            mode = "auto_counter" if mode_name == "AutoCounterPurchasePolicy" else "auto_forecast"
            self._buy_pregnant_heifers(auto_cnt, mode=mode)

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

            if cow.status == "heifer":
                self._tick_heifer(cow)
            elif cow.status == "pregnant_heifer":
                self._tick_pregnant_heifer(cow, new_animals)
            elif cow.status == "fresh":
                self._tick_fresh(cow)
            elif cow.status == "ready_for_breeding":
                self._tick_ready_for_breeding(cow, culled_ids)
            elif cow.status == "pregnant":
                self._tick_pregnant(cow)
            elif cow.status == "dry":
                self._tick_dry(cow, new_animals)

            if cow.is_milking():
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
            age = self.cfg.age_first_insem_days.sample(self.rng)
            if age < self.cfg.min_first_insem_age_days:
                age = self.cfg.min_first_insem_age_days
            cow.planned_first_insem_date = cow.birth_date + timedelta(days=age)

        if self.today >= cow.planned_first_insem_date:
            cow.status = "pregnant_heifer"
            cow.conception_date = self.today
            cow.days_in_current_status = 0
            gd = self.cfg.sample_gestation_days(self.rng)
            cow.planned_calving_date = self.today + timedelta(days=gd)

    def _tick_pregnant_heifer(self, cow: Cow, new_animals: List[Cow]) -> None:
        if cow.planned_calving_date and self.today >= cow.planned_calving_date:
            self._do_calving(cow, new_animals)

    def _tick_fresh(self, cow: Cow) -> None:
        if cow.days_in_current_status >= self.cfg.voluntary_waiting_period:
            cow.status = "ready_for_breeding"
            cow.days_in_current_status = 0
            if cow.last_calving_date is not None:
                sp = self.cfg.service_period_days.sample(self.rng)
                if sp < self.cfg.voluntary_waiting_period:
                    sp = self.cfg.voluntary_waiting_period
                cow.planned_conception_date = cow.last_calving_date + timedelta(days=sp)

    def _tick_ready_for_breeding(self, cow: Cow, culled_ids: set[str]) -> None:
        if cow.days_in_current_status >= self.cfg.max_service_period_after_vwp:
            cow.status = "culled"
            culled_ids.add(cow.id)
            self.purchase_policy.on_removed(1)
            self._culled_today += 1
            self._culled_since_last_record += 1
            return

        if cow.planned_conception_date is None:
            sp = max(1, self.cfg.service_period_days.sample(self.rng))
            cow.planned_conception_date = self.today + timedelta(days=sp)

        if self.today >= cow.planned_conception_date:
            cow.status = "pregnant"
            cow.conception_date = self.today
            cow.days_in_current_status = 0

            gd = self.cfg.sample_gestation_days(self.rng)
            cow.planned_calving_date = self.today + timedelta(days=gd)

            dtd = self.cfg.conception_to_dry_days.sample(self.rng)
            cow.planned_dry_date = self.today + timedelta(days=dtd)
            if cow.planned_dry_date >= cow.planned_calving_date:
                cow.planned_dry_date = cow.planned_calving_date - timedelta(days=1)

    def _tick_pregnant(self, cow: Cow) -> None:
        if cow.planned_dry_date and self.today >= cow.planned_dry_date:
            cow.status = "dry"
            cow.dry_date = self.today
            cow.days_in_current_status = 0
            self._dryoffs_today += 1
            self._dryoffs_since_last_record += 1

    def _tick_dry(self, cow: Cow, new_animals: List[Cow]) -> None:
        if cow.planned_calving_date and self.today >= cow.planned_calving_date:
            self._do_calving(cow, new_animals)

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
