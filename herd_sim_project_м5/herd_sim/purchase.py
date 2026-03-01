# herd_sim/purchase.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .simulation import Simulation

@dataclass
class PurchaseLog:
    manual: List[Tuple[date, int]] = field(default_factory=list)
    auto_counter: List[Tuple[date, int]] = field(default_factory=list)
    auto_forecast: List[Tuple[date, int]] = field(default_factory=list)

class PurchasePolicyBase:
    def purchases_today(self, sim: "Simulation", manual_planned: int) -> int:
        raise NotImplementedError
    def on_added(self, count: int) -> None: pass
    def on_removed(self, count: int) -> None: pass

@dataclass
class ManualPurchasePolicy(PurchasePolicyBase):
    plan: Dict[date, int]
    def purchases_today(self, sim: "Simulation", manual_planned: int) -> int:
        return self.plan.get(sim.today, 0)

@dataclass
class AutoCounterPurchasePolicy(PurchasePolicyBase):
    balance: int = 0
    def purchases_today(self, sim: "Simulation", manual_planned: int) -> int:
        if sim.today.day != 1:
            return 0
        return -self.balance if self.balance < 0 else 0
    def on_added(self, count: int) -> None:
        self.balance += int(count)
    def on_removed(self, count: int) -> None:
        self.balance -= int(count)

@dataclass
class AutoForecastPurchasePolicy(PurchasePolicyBase):
    target_milking: int
    lead_time_days: int = 90
    buffer: int = 0
    max_buy: int = 10_000
    def purchases_today(self, sim: "Simulation", manual_planned: int) -> int:
        if sim.today.day != 1:
            return 0
        future = sim.today + timedelta(days=self.lead_time_days)
        forecast = sim.forecast_milking_count(future)
        need = (self.target_milking + self.buffer) - forecast
        if need <= 0:
            return 0
        return min(int(need), int(self.max_buy))