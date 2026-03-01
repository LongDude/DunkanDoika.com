# herd_sim/samplers.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Sequence, Protocol, Tuple
import random
import math

class IntSampler(Protocol):
    def sample(self, rng: random.Random) -> int: ...
    def update(self, new_values: Sequence[int]) -> None: ...

@dataclass
class EmpiricalDiscreteSampler:
    values: List[int]
    record_history: bool = False
    append_to_values: bool = False  # ⚠️ ломает распределение, оставлено только если тебе прям нужно
    history: List[int] = field(default_factory=list)

    def sample(self, rng: random.Random) -> int:
        if not self.values:
            raise RuntimeError("EmpiricalDiscreteSampler: пустой массив значений")
        v = rng.choice(self.values)
        if self.record_history:
            self.history.append(v)
        if self.append_to_values:
            # ⚠️ Это изменяет распределение (самоусиление). Используй только для дебага.
            self.values.append(v)
        return v

    def update(self, new_values: Sequence[int]) -> None:
        self.values = list(new_values)

@dataclass
class TruncatedNormalSampler:
    mu: float
    sigma: float
    lo: int
    hi: int

    def sample(self, rng: random.Random) -> int:
        x = int(round(rng.gauss(self.mu, self.sigma)))
        if x < self.lo: x = self.lo
        if x > self.hi: x = self.hi
        return x

    def update(self, new_values: Sequence[int]) -> None:
        pass

@dataclass
class LogNormalSampler:
    mu_ln: float
    sigma_ln: float
    lo: int
    hi: int

    def sample(self, rng: random.Random) -> int:
        x = int(round(rng.lognormvariate(self.mu_ln, self.sigma_ln)))
        if x < self.lo: x = self.lo
        if x > self.hi: x = self.hi
        return x

    def update(self, new_values: Sequence[int]) -> None:
        pass

@dataclass
class MixtureDrySampler:
    """
    Теоретическая смесь для days_to_dry:
      - p_peak: пик около 220 (значения >= 200)
      - иначе равномерный хвост слева
    """
    p_peak: float
    mu_peak: float
    sigma_peak: float
    peak_lo: int
    peak_hi: int
    tail_lo: int
    tail_hi: int

    def sample(self, rng: random.Random) -> int:
        if rng.random() < self.p_peak:
            x = int(round(rng.gauss(self.mu_peak, self.sigma_peak)))
            if x < self.peak_lo: x = self.peak_lo
            if x > self.peak_hi: x = self.peak_hi
        else:
            x = rng.randint(self.tail_lo, self.tail_hi)
        return x

    def update(self, new_values: Sequence[int]) -> None:
        pass

def fit_lognormal_params(values: List[int]) -> Tuple[float, float, int, int]:
    if not values:
        raise ValueError("fit_lognormal_params: пустой список")
    lo, hi = min(values), max(values)
    m = sum(values) / len(values)
    v = sum((x - m) ** 2 for x in values) / max(1, (len(values) - 1))
    if m <= 0:
        return 0.0, 1.0, lo, hi
    sigma2 = math.log(1.0 + (v / (m * m)))
    sigma = math.sqrt(max(1e-9, sigma2))
    mu = math.log(m) - 0.5 * sigma2
    return mu, sigma, lo, hi

def build_theoretical_samplers_from_empirical(
    ages: List[int],
    service_periods: List[int],
    days_to_dry: List[int],
) -> Tuple[IntSampler, IntSampler, IntSampler]:
    # age, sp: lognormal
    mu_a, sig_a, lo_a, hi_a = fit_lognormal_params(ages)
    mu_s, sig_s, lo_s, hi_s = fit_lognormal_params(service_periods)
    age_sampler: IntSampler = LogNormalSampler(mu_a, sig_a, lo_a, hi_a)
    sp_sampler: IntSampler = LogNormalSampler(mu_s, sig_s, lo_s, hi_s)

    # dry: mixture (peak>=200)
    if not days_to_dry:
        dtd_sampler: IntSampler = TruncatedNormalSampler(220.0, 10.0, 34, 239)
        return age_sampler, sp_sampler, dtd_sampler

    peak_vals = [x for x in days_to_dry if x >= 200]
    tail_vals = [x for x in days_to_dry if x < 200]
    p_peak = len(peak_vals) / len(days_to_dry)

    if peak_vals:
        mu_peak = sum(peak_vals) / len(peak_vals)
        v_peak = sum((x - mu_peak) ** 2 for x in peak_vals) / max(1, (len(peak_vals) - 1))
        sigma_peak = max(1.0, math.sqrt(max(1e-9, v_peak)))
        peak_lo, peak_hi = min(peak_vals), max(peak_vals)
    else:
        mu_peak, sigma_peak, peak_lo, peak_hi = 220.0, 5.0, 210, 239

    if tail_vals:
        tail_lo, tail_hi = min(tail_vals), min(199, max(tail_vals))
        if tail_hi < tail_lo:
            tail_lo, tail_hi = 34, 199
    else:
        tail_lo, tail_hi = 34, 199

    dtd_sampler = MixtureDrySampler(
        p_peak=p_peak,
        mu_peak=mu_peak,
        sigma_peak=sigma_peak,
        peak_lo=peak_lo,
        peak_hi=peak_hi,
        tail_lo=tail_lo,
        tail_hi=tail_hi,
    )
    return age_sampler, sp_sampler, dtd_sampler