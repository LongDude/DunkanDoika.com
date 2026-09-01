from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Iterable, Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_DATASETS_DIR = PROJECT_DIR / "herd_sim_project_м5"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "Results" / "Backtests"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.schemas import ScenarioParams  # noqa: E402
from app.simulator.forecast_herd_m5 import (  # noqa: E402
    resolve_dataset_start_date,
    run_forecast_herd_m5,
)
from scripts.plot_milk_days_forecast import resolve_dataset  # noqa: E402


DATE_FORMAT = "%d.%m.%Y"
CULLED_STATUSES = {"Продана", "Брак", "Мертвое животное", "Перемещена"}
MOVED_STATUS = "Перемещена"
DEFAULT_MAX_DIM_DAYS = 350

COL_ID = "Номер животного"
COL_BIRTH = "Дата рождения"
COL_ARCHIVE = "Дата архива"
COL_LACTATION = "Лактация"
COL_CALVING = "Дата начала тек.лакт"
COL_DIM = "Дни в доении"
COL_STATUS = "Статус коровы"
COL_INSEM = "Дата осеменения"
COL_SUCCESS_INSEM = "Дата успешного осеменения"
COL_DAYS_PREGNANT = "Дни стельности"
COL_DRY = "Дата запуска тек.лакт"
COL_EXPECTED_DRY = "Дата ожидаемого запуска"
COL_EXPECTED_CALVING = "Дата ожидаемого отела"

FACTUAL_DATE_COLUMNS = (COL_ARCHIVE, COL_CALVING, COL_INSEM, COL_SUCCESS_INSEM, COL_DRY)


def parse_date(value: str | None) -> Optional[date]:
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError:
        return None


def parse_lactation(value: str | None) -> int:
    try:
        return max(0, int((value or "0").strip()))
    except ValueError:
        return 0


def shift_month(month_start: date, months: int) -> date:
    month_index = month_start.year * 12 + month_start.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


def read_dataset(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter=";", quotechar='"')
        if not reader.fieldnames:
            raise ValueError("CSV не содержит заголовок.")
        return list(reader.fieldnames), [dict(row) for row in reader]


def status_at_cutoff(row: dict[str, str], lactation: int, cutoff: date) -> str:
    archive = parse_date(row.get(COL_ARCHIVE))
    if archive is not None and archive <= cutoff:
        return row.get(COL_STATUS, "") or "Выбыло"
    conception = parse_date(row.get(COL_SUCCESS_INSEM))
    if lactation == 0:
        return "Стельная" if conception is not None and conception <= cutoff else "Телка"
    dry = parse_date(row.get(COL_DRY))
    if dry is not None and dry <= cutoff:
        return "Сухостой"
    if conception is not None and conception <= cutoff:
        return "Осемененная"
    return "Дойная"


def rollback_dataset(
    *,
    fieldnames: list[str],
    source_rows: list[dict[str, str]],
    cutoff: date,
    max_dim_days: int = DEFAULT_MAX_DIM_DAYS,
    max_gestation_days: int = 280,
) -> tuple[list[dict[str, str]], set[str], dict[str, int | float]]:
    """Build a leakage-reduced herd snapshot for the requested historical date."""
    source_ids = [(row.get(COL_ID) or "").strip() for row in source_rows]
    id_counts = Counter(animal_id for animal_id in source_ids if animal_id)
    duplicate_ids = sorted(animal_id for animal_id, count in id_counts.items() if count > 1)
    if duplicate_ids:
        sample = ", ".join(duplicate_ids[:5])
        raise ValueError(f"CSV содержит повторяющиеся номера животных: {sample}")

    rolled_rows: list[dict[str, str]] = []
    cohort_ids: set[str] = set()
    stats = {
        "source_rows": len(source_rows),
        "excluded_not_born": 0,
        "excluded_missing_id": 0,
        "excluded_unknown_cull_date": 0,
        "excluded_moved_without_date": 0,
        "excluded_missing_previous_lactation": 0,
        "excluded_missing_first_pregnancy": 0,
        "excluded_dim_above_limit": 0,
        "excluded_conception_after_dim_limit": 0,
        "transitioned_to_dry_at_dim_limit": 0,
        "excluded_overdue_pregnancy": 0,
        "excluded_dry_without_conception": 0,
        "candidate_active_animals": 0,
        "included_rows": 0,
        "active_cohort_animals": 0,
    }

    for source_row in source_rows:
        row = {name: (source_row.get(name) or "") for name in fieldnames}
        animal_id = row.get(COL_ID, "").strip()
        if not animal_id:
            stats["excluded_missing_id"] += 1
            continue
        birth = parse_date(row.get(COL_BIRTH))
        if birth is None or birth > cutoff:
            stats["excluded_not_born"] += 1
            continue

        archive = parse_date(row.get(COL_ARCHIVE))
        raw_status = row.get(COL_STATUS, "").strip()
        if archive is None or archive > cutoff:
            stats["candidate_active_animals"] += 1
        if raw_status == MOVED_STATUS and archive is None:
            stats["excluded_moved_without_date"] += 1
            continue
        if raw_status in CULLED_STATUSES and archive is None:
            stats["excluded_unknown_cull_date"] += 1
            continue

        lactation = parse_lactation(row.get(COL_LACTATION))
        current_calving = parse_date(row.get(COL_CALVING))

        if lactation > 0 and (current_calving is None or current_calving > cutoff):
            if lactation == 1:
                conception = parse_date(row.get(COL_SUCCESS_INSEM))
                conception_is_known_at_cutoff = (
                    conception is not None
                    and conception <= cutoff
                    and current_calving is not None
                    and conception < current_calving
                )
                may_already_be_pregnant = (
                    current_calving is not None
                    and (current_calving - cutoff).days <= max_gestation_days
                )
                if may_already_be_pregnant and not conception_is_known_at_cutoff:
                    # The final snapshot has overwritten the first-pregnancy
                    # fields with the current lactation. Treating this animal
                    # as open would be wrong; inferring conception from its
                    # future calving would leak the holdout outcome.
                    stats["excluded_missing_first_pregnancy"] += 1
                    continue
                # If the first calving is farther away than a full gestation,
                # the animal is safely known to be an open heifer at cutoff.
                lactation = 0
                row[COL_LACTATION] = "0"
                row[COL_CALVING] = ""
            else:
                # The CSV stores only the current lactation. Reconstructing the preceding one
                # would require information that is absent from the source dataset.
                stats["excluded_missing_previous_lactation"] += 1
                continue

        for column in FACTUAL_DATE_COLUMNS:
            event_date = parse_date(row.get(column))
            if event_date is not None and event_date > cutoff:
                row[column] = ""

        # Expected dates describe knowledge from the latest snapshot and would leak future data.
        row[COL_EXPECTED_DRY] = ""
        row[COL_EXPECTED_CALVING] = ""

        archive_at_cutoff = parse_date(row.get(COL_ARCHIVE))
        calving_at_cutoff = parse_date(row.get(COL_CALVING))
        dry_at_cutoff = parse_date(row.get(COL_DRY))
        conception_at_cutoff = parse_date(row.get(COL_SUCCESS_INSEM))
        is_active = archive_at_cutoff is None

        if is_active and conception_at_cutoff is not None:
            conception_before_lactation = (
                lactation > 0
                and calving_at_cutoff is not None
                and conception_at_cutoff <= calving_at_cutoff
            )
            pregnancy_too_long = (
                (cutoff - conception_at_cutoff).days > max_gestation_days
            )
            if conception_before_lactation or pregnancy_too_long:
                stats["excluded_overdue_pregnancy"] += 1
                continue

        if is_active and dry_at_cutoff is not None and conception_at_cutoff is None:
            stats["excluded_dry_without_conception"] += 1
            continue

        is_milking = (
            is_active
            and lactation > 0
            and calving_at_cutoff is not None
            and calving_at_cutoff <= cutoff
            and (dry_at_cutoff is None or dry_at_cutoff > cutoff)
        )
        dim_at_cutoff = (cutoff - calving_at_cutoff).days if is_milking else 0
        if dim_at_cutoff > max_dim_days:
            if conception_at_cutoff is not None:
                limit_exit_date = calving_at_cutoff + timedelta(days=max_dim_days + 1)
                if conception_at_cutoff >= limit_exit_date:
                    # The simulator would already have removed this open cow
                    # before that conception date, so the row cannot be
                    # reconciled with the selected DIM rule.
                    stats["excluded_conception_after_dim_limit"] += 1
                    continue
                # Match the simulator's state transition: a pregnant animal
                # remains in the cohort but is no longer counted as milking.
                cap_dry_date = limit_exit_date
                row[COL_DRY] = cap_dry_date.strftime(DATE_FORMAT)
                dry_at_cutoff = cap_dry_date
                dim_at_cutoff = 0
                stats["transitioned_to_dry_at_dim_limit"] += 1
            else:
                stats["excluded_dim_above_limit"] += 1
                continue
        row[COL_DIM] = str(dim_at_cutoff)
        row[COL_DAYS_PREGNANT] = ""
        row[COL_STATUS] = status_at_cutoff(row, lactation, cutoff)

        rolled_rows.append(row)
        if animal_id and archive_at_cutoff is None:
            cohort_ids.add(animal_id)

    if not rolled_rows:
        raise ValueError("После отката в датасете не осталось восстанавливаемых животных.")

    # The model derives the snapshot date from the maximum factual date. This marker is stored
    # only in the temporary backtest CSV and is ignored by herd state and empirical samplers.
    marker_row = next(
        (row for row in rolled_rows if not row.get(COL_INSEM, "").strip()),
        rolled_rows[0],
    )
    marker_row[COL_INSEM] = cutoff.strftime(DATE_FORMAT)

    stats["included_rows"] = len(rolled_rows)
    stats["active_cohort_animals"] = len(cohort_ids)
    candidate_count = stats["candidate_active_animals"]
    stats["active_cohort_coverage_percent"] = (
        round(len(cohort_ids) / candidate_count * 100.0, 3) if candidate_count else 0.0
    )
    return rolled_rows, cohort_ids, stats


def write_dataset(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames, delimiter=";", quotechar='"', quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def actual_dim_snapshot(
    rows: list[dict[str, str]],
    cohort_ids: set[str],
    target_date: date,
    *,
    max_dim_days: int = DEFAULT_MAX_DIM_DAYS,
) -> dict[str, Optional[float] | int]:
    values: list[int] = []
    forced_dim_limit_count = 0
    for row in rows:
        animal_id = (row.get(COL_ID) or "").strip()
        if animal_id not in cohort_ids:
            continue

        archive = parse_date(row.get(COL_ARCHIVE))
        raw_status = (row.get(COL_STATUS) or "").strip()
        if (archive is not None and archive <= target_date) or (raw_status in CULLED_STATUSES and archive is None):
            continue

        calving = parse_date(row.get(COL_CALVING))
        dry = parse_date(row.get(COL_DRY))
        if calving is None or calving > target_date:
            continue
        if dry is not None and dry <= target_date:
            continue

        dim = (target_date - calving).days
        if dim < 0:
            continue
        if dim > max_dim_days:
            # Apply the same domain transition as the simulator: after the
            # limit this animal is no longer part of the milking population.
            forced_dim_limit_count += 1
            continue
        values.append(dim)

    return {
        "average_dim": float(mean(values)) if values else None,
        "milking_count": len(values),
        "forced_dim_limit_count": forced_dim_limit_count,
    }


def actual_average_dim(
    rows: list[dict[str, str]],
    cohort_ids: set[str],
    target_date: date,
    *,
    max_dim_days: int = DEFAULT_MAX_DIM_DAYS,
) -> Optional[float]:
    snapshot = actual_dim_snapshot(
        rows,
        cohort_ids,
        target_date,
        max_dim_days=max_dim_days,
    )
    value = snapshot["average_dim"]
    return float(value) if value is not None else None


def safe_mean(values: list[float]) -> Optional[float]:
    return float(mean(values)) if values else None


def calculate_metrics(records: list[dict]) -> dict[str, Optional[float] | int]:
    comparable = [row for row in records if row["actual_dim"] is not None and row["predicted_dim"] is not None]
    errors = [float(row["error"]) for row in comparable]
    absolute_errors = [abs(value) for value in errors]
    squared_errors = [value * value for value in errors]
    percentage_errors = [
        abs(float(row["error"])) / float(row["actual_dim"]) * 100.0
        for row in comparable
        if float(row["actual_dim"]) != 0.0
    ]
    covered = [
        float(row["lower_dim"]) <= float(row["actual_dim"]) <= float(row["upper_dim"])
        for row in comparable
        if row["lower_dim"] is not None and row["upper_dim"] is not None
    ]

    return {
        "points": len(comparable),
        "mae_days": safe_mean(absolute_errors),
        "rmse_days": math.sqrt(mean(squared_errors)) if squared_errors else None,
        "mape_percent": safe_mean(percentage_errors),
        "bias_days": safe_mean(errors),
        "interval_coverage_percent": safe_mean([100.0 if value else 0.0 for value in covered]),
    }


def build_quality_warnings(
    rollback_stats: dict[str, int | float],
    forced_dim_total: int,
) -> list[str]:
    warnings = [
        "Оценка построена ретроспективно по одному конечному срезу и является диагностической: "
        "доступность строк и истории может зависеть от исхода животного."
    ]
    if int(rollback_stats.get("excluded_missing_previous_lactation", 0)):
        warnings.append(
            "Часть мультипарных животных исключена, потому что предыдущую лактацию нельзя "
            "восстановить без будущих данных; метрики подвержены смещению отбора по исходу."
        )
    if int(rollback_stats.get("excluded_missing_first_pregnancy", 0)):
        warnings.append(
            "Исключены тёлки с близким будущим первым отёлом, для которых конечный срез не хранит "
            "состояние первой стельности на дату отката; обратный расчёт по будущему отёлу не использовался."
        )
    if int(rollback_stats.get("excluded_conception_after_dim_limit", 0)):
        warnings.append(
            "Исключены строки, где успешное осеменение произошло уже после выхода нестельного "
            "животного по лимиту DIM; такое состояние несовместимо с выбранным доменным правилом."
        )
    if float(rollback_stats.get("active_cohort_coverage_percent", 0.0)) < 70.0:
        warnings.append(
            "Покрытие восстанавливаемой активной когорты ниже 70%; метрики пригодны только как диагностические."
        )
    if forced_dim_total:
        warnings.append(
            f"В исходных фактах обнаружено {forced_dim_total} помесячных случаев продолжения лактации сверх лимита; "
            "при расчёте факта применён доменный переход из дойного состояния."
        )
    return warnings


def build_records(
    result,
    source_rows: list[dict[str, str]],
    cohort_ids: set[str],
    *,
    max_dim_days: int = DEFAULT_MAX_DIM_DAYS,
) -> list[dict]:
    median_by_date = {point.date: point for point in result.series_p50.points}
    lower_by_date = (
        {point.date: point.avg_days_in_milk for point in result.series_p10.points}
        if result.series_p10 is not None
        else {}
    )
    upper_by_date = (
        {point.date: point.avg_days_in_milk for point in result.series_p90.points}
        if result.series_p90 is not None
        else {}
    )

    records: list[dict] = []
    for target_date, predicted_point in median_by_date.items():
        predicted = predicted_point.avg_days_in_milk
        if predicted is not None and (not math.isfinite(float(predicted)) or not 0 <= float(predicted) <= max_dim_days):
            raise RuntimeError(
                f"Прогноз DIM вышел за допустимый диапазон 0..{max_dim_days}: "
                f"{target_date} = {predicted}"
            )
        actual_snapshot = actual_dim_snapshot(
            source_rows,
            cohort_ids,
            target_date,
            max_dim_days=max_dim_days,
        )
        actual = actual_snapshot["average_dim"]
        error = None if actual is None or predicted is None else float(predicted) - actual
        records.append(
            {
                "date": target_date,
                "actual_dim": actual,
                "actual_milking_count": actual_snapshot["milking_count"],
                "actual_forced_dim_limit_count": actual_snapshot["forced_dim_limit_count"],
                "predicted_dim": float(predicted) if predicted is not None else None,
                "predicted_milking_count": int(predicted_point.milking_count),
                "lower_dim": lower_by_date.get(target_date),
                "upper_dim": upper_by_date.get(target_date),
                "error": error,
                "absolute_error": abs(error) if error is not None else None,
            }
        )
    return records


def write_records(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        fieldnames = [
            "date",
            "actual_dim",
            "actual_milking_count",
            "actual_forced_dim_limit_count",
            "predicted_dim",
            "predicted_milking_count",
            "lower_dim",
            "upper_dim",
            "error",
            "absolute_error",
        ]
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    key: value.isoformat() if isinstance(value, date) else value
                    for key, value in record.items()
                }
            )


def plot_backtest(
    *,
    records: list[dict],
    dataset_name: str,
    cutoff: date,
    metrics: dict,
    confidence: float,
    output_path: Path,
    show: bool,
) -> None:
    comparable = [row for row in records if row["actual_dim"] is not None and row["predicted_dim"] is not None]
    dates = [row["date"] for row in comparable]
    actual = [row["actual_dim"] for row in comparable]
    predicted = [row["predicted_dim"] for row in comparable]
    lower = [row["lower_dim"] for row in comparable]
    upper = [row["upper_dim"] for row in comparable]
    errors = [row["error"] for row in comparable]

    fig, (ax_main, ax_error) = plt.subplots(
        2,
        1,
        figsize=(13, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    ax_main.plot(
        dates,
        actual,
        color="#202020",
        linewidth=2.3,
        marker="o",
        label="Восстановленный фактический DIM",
    )
    ax_main.plot(dates, predicted, color="#256d3b", linewidth=2.3, marker="o", label="Прогноз DIM (P50)")

    if all(value is not None for value in lower + upper):
        ax_main.fill_between(
            dates,
            lower,
            upper,
            color="#77b77d",
            alpha=0.3,
            label=f"Доверительный интервал {confidence:.0%}",
        )

    mae = metrics.get("mae_days")
    rmse = metrics.get("rmse_days")
    metric_line = f"MAE: {mae:.2f} дня · RMSE: {rmse:.2f} дня" if mae is not None and rmse is not None else ""
    ax_main.set_title(
        "Диагностическая ретроспективная оценка прогноза дней лактации (DIM)\n"
        f"{dataset_name} · откат к {cutoff:%d.%m.%Y} · {metric_line}",
        fontsize=14,
        pad=14,
    )
    ax_main.set_ylabel("Среднее число дней лактации (DIM)")
    ax_main.grid(True, alpha=0.25)
    ax_main.legend(loc="best")

    colors = ["#b53a3a" if value > 0 else "#3b68a0" for value in errors]
    ax_error.bar(dates, errors, width=12, color=colors, alpha=0.8)
    ax_error.axhline(0, color="#202020", linewidth=1)
    ax_error.set_ylabel("Ошибка, дней")
    ax_error.set_xlabel("Дата проверки")
    ax_error.grid(True, axis="y", alpha=0.25)
    ax_error.xaxis.set_major_locator(mdates.MonthLocator(interval=max(1, len(dates) // 12)))
    ax_error.xaxis.set_major_formatter(mdates.DateFormatter("%m.%Y"))
    fig.autofmt_xdate(rotation=45, ha="right")
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=170, bbox_inches="tight")
    if show:
        plt.show()
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ретроспективная оценка прогноза DIM по исторически восстанавливаемой части датасета."
    )
    parser.add_argument("--dataset", help="Путь к CSV. Без аргумента будет показан список датасетов.")
    parser.add_argument("--datasets-dir", type=Path, default=DEFAULT_DATASETS_DIR)
    parser.add_argument("--backtest-months", type=int, default=6, help="Глубина отката в месяцах (1–24).")
    parser.add_argument("--mc-runs", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mode", choices=("empirical", "theoretical"), default="empirical")
    parser.add_argument(
        "--purchase-policy",
        choices=("manual",),
        default="manual",
        help="Когортный backtest поддерживает только manual без закупок.",
    )
    parser.add_argument("--confidence", type=float, default=0.90)
    parser.add_argument("--processes", type=int, default=1)
    parser.add_argument(
        "--max-dim-days",
        type=int,
        default=DEFAULT_MAX_DIM_DAYS,
        help="Максимальное допустимое число дней лактации; после лимита животное не считается дойным.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--show", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not 1 <= args.backtest_months <= 24:
        raise ValueError("--backtest-months должен быть от 1 до 24 для когортной проверки по одному снимку.")
    if not 200 <= args.max_dim_days <= 1000:
        raise ValueError("--max-dim-days должен быть от 200 до 1000.")

    dataset_path = resolve_dataset(args.dataset, args.datasets_dir.expanduser().resolve())
    fieldnames, source_rows = read_dataset(dataset_path)
    source_bytes = dataset_path.read_bytes()
    source_snapshot_date = resolve_dataset_start_date(source_bytes)
    evaluation_end = source_snapshot_date.replace(day=1)
    cutoff = shift_month(evaluation_end, -args.backtest_months)

    safe_name = "".join(char if char.isalnum() else "_" for char in dataset_path.stem).strip("_")
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{safe_name}_backtest_{args.backtest_months}m"
    rollback_path = output_dir / f"{base_name}_rollback.csv"
    records_path = output_dir / f"{base_name}_comparison.csv"
    metrics_path = output_dir / f"{base_name}_metrics.json"
    chart_path = output_dir / f"{base_name}.png"

    rolled_rows, cohort_ids, rollback_stats = rollback_dataset(
        fieldnames=fieldnames,
        source_rows=source_rows,
        cutoff=cutoff,
        max_dim_days=args.max_dim_days,
    )
    write_dataset(rollback_path, fieldnames, rolled_rows)
    rollback_bytes = rollback_path.read_bytes()
    resolved_cutoff = resolve_dataset_start_date(rollback_bytes)
    if resolved_cutoff != cutoff:
        raise RuntimeError(f"Дата отката определилась неверно: {resolved_cutoff}, ожидалась {cutoff}")

    params = ScenarioParams(
        dataset_id=f"backtest-{dataset_path.stem}",
        report_date=cutoff,
        horizon_months=args.backtest_months,
        seed=args.seed,
        mc_runs=args.mc_runs,
        mode=args.mode,
        purchase_policy=args.purchase_policy,
        confidence_central=args.confidence,
        model={"max_days_in_milk": args.max_dim_days},
        purchases=[],
    )

    print(f"\nИсходный датасет: {dataset_path.name}")
    print(f"Дата исходного среза: {source_snapshot_date:%d.%m.%Y}")
    print(f"Дата отката: {cutoff:%d.%m.%Y}")
    print(f"Проверка до: {evaluation_end:%d.%m.%Y}")
    print(f"Восстанавливаемая когорта: {len(cohort_ids)} животных")
    print(f"Покрытие потенциально активной когорты: {rollback_stats['active_cohort_coverage_percent']:.1f}%")
    print(
        "Исключено из-за отсутствия предыдущей лактации: "
        f"{rollback_stats['excluded_missing_previous_lactation']}"
    )
    print(
        "Исключено из-за невосстанавливаемой первой стельности: "
        f"{rollback_stats['excluded_missing_first_pregnancy']}"
    )
    print(f"Исключено со статусом «Перемещена» без даты: {rollback_stats['excluded_moved_without_date']}")
    print(f"Исключено нестельных с DIM выше {args.max_dim_days}: {rollback_stats['excluded_dim_above_limit']}")
    print(
        "Исключено из-за осеменения после лимита DIM: "
        f"{rollback_stats['excluded_conception_after_dim_limit']}"
    )
    print(
        f"Переведено в сухостой по лимиту DIM: {rollback_stats['transitioned_to_dry_at_dim_limit']}"
    )
    print(f"Исключено с невосстанавливаемой беременностью: {rollback_stats['excluded_overdue_pregnancy']}")
    print(f"Исключено сухостойных без даты успешного осеменения: {rollback_stats['excluded_dry_without_conception']}")
    print("Выполняется ретроспективный прогноз...")

    last_reported = {"percent": -10}

    def report_progress(completed: int, total: int, _partial_result) -> None:
        percent = int(completed / max(1, total) * 100)
        if percent == 100 or percent >= last_reported["percent"] + 10:
            print(f"  Прогресс: {completed}/{total} ({percent}%)")
            last_reported["percent"] = percent

    result = run_forecast_herd_m5(
        rollback_bytes,
        params,
        parallel_enabled=args.processes > 1,
        max_processes=max(1, args.processes),
        batch_size=max(1, min(10, args.mc_runs)),
        simulation_version="1.1.0-backtest",
        progress_callback=report_progress,
    )

    records = build_records(
        result,
        source_rows,
        cohort_ids,
        max_dim_days=args.max_dim_days,
    )
    metrics = calculate_metrics(records[1:])  # The cutoff point is initialization, not a forecast.
    write_records(records_path, records)

    forced_dim_total = sum(int(row["actual_forced_dim_limit_count"]) for row in records[1:])
    quality_warnings = build_quality_warnings(rollback_stats, forced_dim_total)

    report = {
        "dataset": str(dataset_path),
        "source_snapshot_date": source_snapshot_date.isoformat(),
        "cutoff_date": cutoff.isoformat(),
        "evaluation_end": evaluation_end.isoformat(),
        "backtest_months": args.backtest_months,
        "mc_runs": args.mc_runs,
        "mode": args.mode,
        "purchase_policy": args.purchase_policy,
        "confidence": args.confidence,
        "max_dim_days": args.max_dim_days,
        "rollback": rollback_stats,
        "metrics": metrics,
        "evaluation_status": "diagnostic" if quality_warnings else "passed",
        "quality_warnings": quality_warnings,
        "actual_forced_dim_limit_total": forced_dim_total,
        "limitations": [
            "Исходный CSV содержит один актуальный срез, а не полную продольную историю лактаций.",
            "Животные, для которых нельзя восстановить предыдущую лактацию, исключены и из отката, и из фактической когорты.",
            "Фактический DIM восстановлен по датам текущей лактации для той же когорты животных.",
            f"Единое бизнес-ограничение DIM={args.max_dim_days} применено к откату, симуляции и фактической кривой без числового обрезания значений.",
            "Статус «Перемещена» без даты перемещения исключён как состояние с неизвестным моментом выхода.",
            "Это ретроспективный когортный бэктест, а не независимая проверка на отдельном будущем срезе.",
        ],
    }
    metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    plot_backtest(
        records=records[1:],
        dataset_name=dataset_path.name,
        cutoff=cutoff,
        metrics=metrics,
        confidence=args.confidence,
        output_path=chart_path,
        show=args.show,
    )

    print("\nМетрики:")
    print(f"  MAE: {metrics['mae_days']:.3f} дня" if metrics["mae_days"] is not None else "  MAE: нет данных")
    print(f"  RMSE: {metrics['rmse_days']:.3f} дня" if metrics["rmse_days"] is not None else "  RMSE: нет данных")
    print(f"  MAPE: {metrics['mape_percent']:.3f}%" if metrics["mape_percent"] is not None else "  MAPE: нет данных")
    print(f"  Смещение: {metrics['bias_days']:.3f} дня" if metrics["bias_days"] is not None else "  Смещение: нет данных")
    print(
        f"  Покрытие интервала: {metrics['interval_coverage_percent']:.1f}%"
        if metrics["interval_coverage_percent"] is not None
        else "  Покрытие интервала: нет данных"
    )
    if quality_warnings:
        print("\nПредупреждения качества:")
        for warning in quality_warnings:
            print(f"  - {warning}")
    print(f"\nГрафик: {chart_path}")
    print(f"Сравнение по датам: {records_path}")
    print(f"Отчёт с метриками: {metrics_path}")
    print(f"Датасет после отката: {rollback_path}")
    print("\nВажно: результаты относятся к восстанавливаемой когорте, а не ко всему исходному стаду.")


if __name__ == "__main__":
    main()
