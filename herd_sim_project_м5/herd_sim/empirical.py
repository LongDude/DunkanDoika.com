
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Sequence
import random

@dataclass
class EmpiricalDiscreteSampler:
    """
    Эмпирический сэмплер (без сглаживания), как вы просили:

    Требование заказчика:
    1) "узнать день" -> sample()
    2) "обновить массив" -> update()

    Важно: values может содержать повторы, поэтому rng.choice(values)
    корректно воспроизводит эмпирическое распределение.
    """
    values: List[int]

    def sample(self, rng: random.Random) -> int:
        if not self.values:
            raise RuntimeError("EmpiricalDiscreteSampler: пустой массив значений")
        return rng.choice(self.values)

    def update(self, new_values: Sequence[int]) -> None:
        self.values = list(new_values)
