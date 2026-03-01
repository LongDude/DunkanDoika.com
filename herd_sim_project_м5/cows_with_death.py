# cows_with_death.py
import csv
import random
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Константы для статусов выбытия
CULLED_STATUSES = {"Продана", "Брак", "Мертвое животное"}

@dataclass
class Cow:
    id: str
    birth_date: date
    status: str  # 'heifer', 'pregnant_heifer', 'fresh', 'ready_for_breeding', 'pregnant', 'dry', 'culled'
    lactation_number: int = 0
    last_calving_date: Optional[date] = None
    conception_date: Optional[date] = None
    dry_date: Optional[date] = None
    planned_dry_date: Optional[date] = None
    planned_calving_date: Optional[date] = None
    days_in_current_status: int = 0
    days_in_milk: int = 0

    planned_first_insem_date: Optional[date] = None   # План: 1-е успешное осеменение (для тёлки)
    planned_conception_date: Optional[date] = None    # План: успешное осеменение (для коровы)

    def age_in_days(self, current_date: date) -> int:
        return (current_date - self.birth_date).days

    def is_milking(self) -> bool:
        return self.status in ('fresh', 'ready_for_breeding', 'pregnant')

    def reset_for_new_lactation(self, calving_date: date):
        self.status = 'fresh'
        self.lactation_number += 1
        self.last_calving_date = calving_date
        self.days_in_milk = 0
        self.conception_date = None
        self.dry_date = None
        self.planned_dry_date = None
        self.planned_calving_date = None
        self.days_in_current_status = 0


def parse_date(date_str: str) -> Optional[date]:
    if not date_str or date_str.strip() == "":
        return None
    try:
        return datetime.strptime(date_str.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def get_max_date_from_file(rows: List[dict]) -> date:
    """
    Важно: 'today' считаем по ФАКТИЧЕСКИМ датам.
    НЕ включаем ожидаемые даты, иначе today может уехать в будущее.
    """
    max_date = None
    date_fields = [
        'Дата рождения', 'Дата архива', 'Дата начала тек.лакт',
        'Дата осеменения', 'Дата успешного осеменения', 'Дата запуска тек.лакт',
    ]
    for row in rows:
        for field in date_fields:
            d = parse_date(row.get(field, ''))
            if d and (max_date is None or d > max_date):
                max_date = d
    if max_date is None:
        raise ValueError("Не найдено ни одной фактической даты в файле")
    return max_date


def determine_status(
    lactation: int,
    last_calving: Optional[date],
    conception: Optional[date],
    dry: Optional[date],
    birth_date: date,
    today: date
) -> Tuple[str, int]:
    if lactation == 0:
        if conception is None:
            return 'heifer', (today - birth_date).days
        return 'pregnant_heifer', (today - conception).days

    if dry is not None:
        return 'dry', (today - dry).days

    if conception is not None:
        return 'pregnant', (today - conception).days

    if last_calving is None:
        return 'fresh', 0

    days_after_calving = (today - last_calving).days
    if days_after_calving < 50:
        return 'fresh', days_after_calving
    return 'ready_for_breeding', days_after_calving - 50


def load_active_cows(file_path: str) -> List[Cow]:
    active_cows: List[Cow] = []

    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f, delimiter=';', quotechar='"'))
        today = get_max_date_from_file(rows)

        for row in rows:
            status_raw = row.get('Статус коровы', '').strip()
            if status_raw in CULLED_STATUSES:
                continue

            archive_date = parse_date(row.get('Дата архива', ''))
            if archive_date is not None:
                continue

            cow_id = row.get('Номер животного', '').strip()
            birth_date = parse_date(row.get('Дата рождения', ''))
            if birth_date is None:
                continue

            lactation_str = row.get('Лактация', '').strip()
            lactation = int(lactation_str) if lactation_str.isdigit() else 0

            last_calving = parse_date(row.get('Дата начала тек.лакт', ''))
            conception = parse_date(row.get('Дата успешного осеменения', ''))
            dry = parse_date(row.get('Дата запуска тек.лакт', ''))
            planned_dry = parse_date(row.get('Дата ожидаемого запуска', ''))
            planned_calving = parse_date(row.get('Дата ожидаемого отела', ''))

            dim_str = row.get('Дни в доении', '').strip()
            days_in_milk = int(dim_str) if dim_str.isdigit() else 0

            status, days_in_status = determine_status(
                lactation, last_calving, conception, dry, birth_date, today
            )

            active_cows.append(Cow(
                id=cow_id,
                birth_date=birth_date,
                status=status,
                lactation_number=lactation,
                last_calving_date=last_calving,
                conception_date=conception,
                dry_date=dry,
                planned_dry_date=planned_dry,
                planned_calving_date=planned_calving,
                days_in_current_status=days_in_status,
                days_in_milk=days_in_milk
            ))

    return active_cows



# =========================
# Эмпирические распределения (нужны для init_empirical_data / get_empirical_lists)
# =========================

_emp_ages: List[int] = []
_emp_dry: List[int] = []
_emp_sp: List[int] = []

def _load_empirical_lists(file_path: str) -> Tuple[List[int], List[int], List[int]]:
    """
    Возвращает:
    - ages_first_insem: возраст 1-го успешного осеменения (только лактация 0)
    - days_to_dry: дни от успешного осеменения до запуска
    - service_periods: сервис-период (от отёла до успешного осеменения)
    """
    ages_first_insem: List[int] = []
    days_to_dry: List[int] = []
    service_periods: List[int] = []

    with open(file_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";", quotechar='"')
        for row in reader:
            lact_str = (row.get("Лактация", "") or "").strip()
            lact = int(lact_str) if lact_str.isdigit() else 0

            birth = parse_date(row.get("Дата рождения", ""))
            insem_success = parse_date(row.get("Дата успешного осеменения", ""))
            dry = parse_date(row.get("Дата запуска тек.лакт", ""))
            calving = parse_date(row.get("Дата начала тек.лакт", ""))

            # 1) возраст 1-го успешного осеменения (только для тёлок, lact=0)
            if lact == 0 and birth and insem_success:
                v = (insem_success - birth).days
                if v > 0:
                    ages_first_insem.append(v)

            # 2) дни от успеха до запуска
            if insem_success and dry:
                v = (dry - insem_success).days
                if v > 0:
                    days_to_dry.append(v)

            # 3) сервис-период: от отёла до успеха
            if calving and insem_success and insem_success > calving:
                v = (insem_success - calving).days
                if v > 0:
                    service_periods.append(v)

    return ages_first_insem, days_to_dry, service_periods

def init_empirical_data(file_path: str) -> None:
    """Загрузка эмпирики для дальнейшего использования."""
    global _emp_ages, _emp_dry, _emp_sp
    _emp_ages, _emp_dry, _emp_sp = _load_empirical_lists(file_path)

def update_empirical_data(file_path: str) -> None:
    """Перезагрузка эмпирики (если нужно)."""
    init_empirical_data(file_path)

def get_empirical_lists() -> Tuple[List[int], List[int], List[int]]:
    """(ages_first_insem, days_to_dry, service_periods)"""
    return _emp_ages, _emp_dry, _emp_sp

# Опционально: совместимость со старыми вызовами random_*
def random_age_first_insemination() -> int:
    if not _emp_ages:
        raise RuntimeError("Эмпирика не загружена: вызови init_empirical_data(file_path)")
    return random.choice(_emp_ages)

def random_days_to_dry() -> int:
    if not _emp_dry:
        raise RuntimeError("Эмпирика не загружена: вызови init_empirical_data(file_path)")
    return random.choice(_emp_dry)

def random_service_period() -> int:
    if not _emp_sp:
        raise RuntimeError("Эмпирика не загружена: вызови init_empirical_data(file_path)")
    return random.choice(_emp_sp)


# ---------- Вероятности выбытия ----------

def calculate_culling_probabilities(file_path: str) -> Dict[int, float]:
    total_days: Dict[int, int] = {}
    exited: Dict[int, int] = {}

    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f, delimiter=';', quotechar='"'))
        today = get_max_date_from_file(rows)

        for row in rows:
            lact_str = row.get('Лактация', '').strip()
            lactation = int(lact_str) if lact_str.isdigit() else 0

            birth = parse_date(row.get('Дата рождения', ''))
            if birth is None:
                continue

            archive = parse_date(row.get('Дата архива', ''))
            status_raw = row.get('Статус коровы', '').strip()
            is_culled_by_status = status_raw in CULLED_STATUSES

            if is_culled_by_status and archive is None:
                continue

            calving = parse_date(row.get('Дата начала тек.лакт', ''))

            if lactation == 0:
                start = birth
            else:
                if calving is None:
                    continue
                start = calving

            end = archive if archive else today
            if end <= start:
                continue

            days = (end - start).days
            total_days[lactation] = total_days.get(lactation, 0) + days
            if archive is not None or is_culled_by_status:
                exited[lactation] = exited.get(lactation, 0) + 1

    probs: Dict[int, float] = {}
    for lact in total_days:
        probs[lact] = exited.get(lact, 0) / total_days[lact] if total_days[lact] > 0 else 0.0
    return probs


def calculate_culling_probabilities_by_month(file_path: str) -> Dict[int, float]:
    month_days: Dict[int, int] = {m: 0 for m in range(1, 13)}
    month_exits: Dict[int, int] = {m: 0 for m in range(1, 13)}

    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f, delimiter=';', quotechar='"'))
        today = get_max_date_from_file(rows)

        for row in rows:
            birth = parse_date(row.get('Дата рождения', ''))
            if birth is None:
                continue

            archive = parse_date(row.get('Дата архива', ''))
            status_raw = row.get('Статус коровы', '').strip()
            is_culled = status_raw in CULLED_STATUSES or archive is not None

            if is_culled and archive is None:
                continue

            start = birth
            end = archive if archive else today
            if end <= start:
                continue

            current = start
            while current < end:
                if current.month == 12:
                    next_month = date(current.year + 1, 1, 1)
                else:
                    next_month = date(current.year, current.month + 1, 1)

                month_end = min(next_month, end)
                days_in_month = (month_end - current).days
                month_days[current.month] += days_in_month

                if archive and current.year == archive.year and current.month == archive.month:
                    month_exits[current.month] += 1

                current = month_end

    probs: Dict[int, float] = {}
    for m in range(1, 13):
        probs[m] = month_exits[m] / month_days[m] if month_days[m] > 0 else 0.0
    return probs


# ---------- Кэш по file_path (важно для производительности) ----------

_CULL_CACHE: Dict[str, Dict[str, Dict[int, float]]] = {}
# _CULL_CACHE[file_path] = {"lact": {...}, "month": {...}}

def _ensure_cull_cache(file_path: str) -> None:
    if file_path in _CULL_CACHE:
        return
    _CULL_CACHE[file_path] = {
        "lact": calculate_culling_probabilities(file_path),
        "month": calculate_culling_probabilities_by_month(file_path),
    }

def cull_probability_lact(cow: Cow, file_path: str) -> float:
    _ensure_cull_cache(file_path)
    return _CULL_CACHE[file_path]["lact"].get(cow.lactation_number, 0.0)

def cull_probability_month(current_date: date, file_path: str) -> float:
    _ensure_cull_cache(file_path)
    return _CULL_CACHE[file_path]["month"].get(current_date.month, 0.0)

def cull_probability_combined(cow: Cow, current_date: date, file_path: str) -> float:
    """
    Комбинация по независимости:
    p = p_lact + p_month - p_lact*p_month
    """
    p_l = cull_probability_lact(cow, file_path)
    p_m = cull_probability_month(current_date, file_path)
    return p_l + p_m - p_l * p_m

def cull_cow_combined(cow: Cow, current_date: date, file_path: str, rng: Optional[random.Random] = None, population_regulation: float = 1.0) -> bool:
    p = cull_probability_combined(cow, current_date, file_path)
    p *= population_regulation  # apply population regulation factor    
    
    r = rng.random() if rng is not None else random.random()
    return r < p