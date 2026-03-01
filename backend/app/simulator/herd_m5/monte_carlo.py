# herd_sim/monte_carlo.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import List, Tuple, Dict, Optional, Any
import math

from .cows_with_death import Cow
from .simulation import Simulation, ModelConfig
from .purchase import PurchasePolicyBase, PurchaseLog, ManualPurchasePolicy, AutoCounterPurchasePolicy, AutoForecastPurchasePolicy

def _quantile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if q <= 0:
        return sorted_vals[0]
    if q >= 1:
        return sorted_vals[-1]
    n = len(sorted_vals)
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    w = pos - lo
    return sorted_vals[lo] * (1 - w) + sorted_vals[hi] * w

@dataclass
class Bands:
    central: float
    series: Dict[str, List[Tuple[date, float, float, float]]]
    purchase_logs: List[PurchaseLog]

def _run_one(args: Dict[str, Any]) -> Dict[str, Any]:
    base_herd: List[Cow] = args["base_herd"]
    cfg: ModelConfig = args["cfg"]
    start_date: date = args["start_date"]
    file_path: str = args["file_path"]
    days: int = args["days"]
    seed: int = args["seed"]
    policy_name: str = args["policy"]
    manual_purchase_plan = args["manual_purchase_plan"]
    record_monthly: bool = args["record_monthly"]
    lead_time_days: int = args["lead_time_days"]

    herd = [Cow(**vars(c)) for c in base_herd]

    if policy_name == "manual":
        p: PurchasePolicyBase = ManualPurchasePolicy(plan={d: n for d, n in (manual_purchase_plan or [])})
    elif policy_name == "auto_counter":
        p = AutoCounterPurchasePolicy(balance=0)
    elif policy_name == "auto_forecast":
        target_milking = sum(1 for c in herd if c.is_milking())
        p = AutoForecastPurchasePolicy(target_milking=target_milking, lead_time_days=lead_time_days, buffer=0)
    else:
        raise ValueError(f"Unknown policy: {policy_name}")

    sim = Simulation(
        initial_cows=herd,
        cfg=cfg,
        start_date=start_date,
        file_path=file_path,
        purchase_policy=p,
        manual_purchase_plan=manual_purchase_plan,
        random_seed=seed,
        record_monthly=record_monthly
    )
    history = sim.run(days)
    return {"history": history, "purchase_log": sim.purchase_log}

class MonteCarloRunner:
    def __init__(self, base_herd: List[Cow], cfg: ModelConfig, start_date: date, file_path: str):
        self.base_herd = base_herd
        self.cfg = cfg
        self.start_date = start_date
        self.file_path = file_path

    def run(
        self,
        days: int,
        runs: int,
        central: float = 0.95,          
        manual_purchase_plan: Optional[List[Tuple[date, int]]] = None,
        policy: str = "manual",   # manual | auto_counter | auto_forecast
        seed0: int = 42,
        record_monthly: bool = False,
        n_jobs: int = 1,
        lead_time_days: int = 90,
    ) -> Bands:
        jobs = []
        for r in range(runs):
            jobs.append({
                "base_herd": self.base_herd,
                "cfg": self.cfg,
                "start_date": self.start_date,
                "file_path": self.file_path,
                "days": days,
                "seed": seed0 + r * 1000,
                "policy": policy,
                "manual_purchase_plan": manual_purchase_plan,
                "record_monthly": record_monthly,
                "lead_time_days": lead_time_days,
            })

        if n_jobs == 1:
            results = [_run_one(j) for j in jobs]
        else:
            import multiprocessing as mp
            ctx = mp.get_context("spawn")  # Windows-safe
            with ctx.Pool(processes=n_jobs) as pool:
                results = pool.map(_run_one, jobs)

        raw: Dict[str, Dict[date, List[float]]] = {
            "milking": {},
            "dry": {},
            "heifer": {},
            "preg_heifer": {},
            "avg_dim": {},
            "culled": {},
        }
        purchase_logs: List[PurchaseLog] = []

        for res in results:
            purchase_logs.append(res["purchase_log"])
            for m in res["history"]:
                d = m.day
                raw["milking"].setdefault(d, []).append(float(m.milking_count))
                raw["dry"].setdefault(d, []).append(float(m.dry_count))
                raw["heifer"].setdefault(d, []).append(float(m.heifer_count))
                raw["preg_heifer"].setdefault(d, []).append(float(m.pregnant_heifer_count))
                raw["avg_dim"].setdefault(d, []).append(float(m.avg_days_in_milk))
                raw["culled"].setdefault(d, []).append(float(m.culled_count))

        alpha = (1.0 - central) / 2.0
        out: Dict[str, List[Tuple[date, float, float, float]]] = {}
        for name, series in raw.items():
            rows = []
            for d in sorted(series.keys()):
                vals = sorted(series[d])
                med = _quantile(vals, 0.5)
                lo = _quantile(vals, alpha)
                hi = _quantile(vals, 1.0 - alpha)
                rows.append((d, med, lo, hi))
            out[name] = rows

        return Bands(central=central, series=out, purchase_logs=purchase_logs)
