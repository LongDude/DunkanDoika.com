from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


if sys.platform == "win32":
    # Keep Russian prompts readable in PowerShell, Windows Terminal and redirected output.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_DATASETS_DIR = PROJECT_DIR / "herd_sim_project_м5"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "Results" / "Graphics"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.schemas import ForecastSeries, ScenarioParams  # noqa: E402
from app.simulator.forecast_herd_m5 import (  # noqa: E402
    resolve_dataset_start_date,
    run_forecast_herd_m5,
)


def discover_datasets(directory: Path) -> list[Path]:
    """Return CSV herd datasets from a directory in a stable order."""
    if not directory.exists():
        raise FileNotFoundError(f"Каталог с датасетами не найден: {directory}")

    datasets = sorted(
        (path for path in directory.glob("*.csv") if path.is_file()),
        key=lambda path: path.name.casefold(),
    )
    if not datasets:
        raise FileNotFoundError(f"В каталоге нет CSV-файлов: {directory}")
    return datasets


def choose_dataset(datasets: Sequence[Path]) -> Path:
    """Ask the user to select one of the discovered herd datasets."""
    print("\nДоступные наборы данных о стаде:")
    for index, path in enumerate(datasets, start=1):
        print(f"  {index}. {path.name}")

    while True:
        try:
            raw_value = input(f"Выберите датасет [1-{len(datasets)}]: ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise SystemExit("\nВыбор датасета отменён.") from exc

        try:
            selected_index = int(raw_value)
        except ValueError:
            print("Введите номер датасета из списка.")
            continue

        if 1 <= selected_index <= len(datasets):
            return datasets[selected_index - 1]
        print(f"Номер должен быть от 1 до {len(datasets)}.")


def resolve_dataset(dataset_arg: str | None, datasets_dir: Path) -> Path:
    if dataset_arg:
        dataset_path = Path(dataset_arg).expanduser().resolve()
        if not dataset_path.is_file():
            raise FileNotFoundError(f"Файл датасета не найден: {dataset_path}")
        if dataset_path.suffix.lower() != ".csv":
            raise ValueError("Для прогноза требуется CSV-файл.")
        return dataset_path
    return choose_dataset(discover_datasets(datasets_dir))


def series_values(series: ForecastSeries) -> tuple[list, list[float]]:
    dates = [point.date for point in series.points]
    dim_values = [
        float(point.avg_days_in_milk) if point.avg_days_in_milk is not None else float("nan")
        for point in series.points
    ]
    return dates, dim_values


def plot_forecast(
    *,
    result,
    dataset_path: Path,
    output_path: Path,
    confidence: float,
    mode: str,
    mc_runs: int,
    show: bool,
) -> None:
    dates, median_dim = series_values(result.series_p50)

    fig, ax = plt.subplots(figsize=(13, 7))
    ax.plot(
        dates,
        median_dim,
        color="#256d3b",
        linewidth=2.4,
        marker="o",
        markersize=3.5,
        label="Медианный прогноз DIM",
        zorder=3,
    )

    if result.series_p10 is not None and result.series_p90 is not None:
        lower_dates, lower_dim = series_values(result.series_p10)
        upper_dates, upper_dim = series_values(result.series_p90)
        if lower_dates == dates and upper_dates == dates:
            lower_q = (1.0 - confidence) / 2.0 * 100.0
            upper_q = 100.0 - lower_q
            ax.fill_between(
                dates,
                lower_dim,
                upper_dim,
                color="#77b77d",
                alpha=0.3,
                label=f"Доверительный интервал {confidence:.0%} (P{lower_q:g}–P{upper_q:g})",
                zorder=2,
            )

    ax.set_title(
        "Прогноз среднего числа дней лактации (DIM)\n"
        f"{dataset_path.name} · режим: {mode} · прогонов: {mc_runs}",
        fontsize=14,
        pad=14,
    )
    ax.set_xlabel("Месяц прогноза")
    ax.set_ylabel("Среднее число дней лактации (DIM)")
    ax.grid(True, alpha=0.25, linewidth=0.8)
    ax.legend(loc="best")
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(1, len(dates) // 12)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m.%Y"))
    fig.autofmt_xdate(rotation=45, ha="right")
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=170, bbox_inches="tight")
    print(f"\nГрафик сохранён: {output_path.resolve()}")

    if show:
        plt.show()
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Построение прогноза среднего числа дней лактации (DIM) по выбранному датасету."
    )
    parser.add_argument(
        "--dataset",
        help="Путь к CSV. Если не указан, скрипт предложит выбрать файл из списка.",
    )
    parser.add_argument(
        "--datasets-dir",
        type=Path,
        default=DEFAULT_DATASETS_DIR,
        help=f"Каталог для интерактивного выбора (по умолчанию: {DEFAULT_DATASETS_DIR}).",
    )
    parser.add_argument("--horizon-months", type=int, default=36, help="Горизонт прогноза, месяцев (1–120).")
    parser.add_argument("--mc-runs", type=int, default=100, help="Количество прогонов Монте-Карло.")
    parser.add_argument("--seed", type=int, default=42, help="Начальное значение генератора случайных чисел.")
    parser.add_argument(
        "--mode",
        choices=("empirical", "theoretical"),
        default="empirical",
        help="Режим распределений модели.",
    )
    parser.add_argument(
        "--purchase-policy",
        choices=("manual", "auto_counter", "auto_forecast"),
        default="auto_counter",
        help="Стратегия закупки нетелей.",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.90,
        help="Центральный доверительный интервал (0.50–0.99).",
    )
    parser.add_argument("--processes", type=int, default=1, help="Число параллельных процессов.")
    parser.add_argument("--output", type=Path, help="Путь для итогового PNG.")
    parser.add_argument("--show", action="store_true", help="Открыть окно с графиком после сохранения.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    dataset_path = resolve_dataset(args.dataset, args.datasets_dir.expanduser().resolve())
    csv_bytes = dataset_path.read_bytes()
    report_date = resolve_dataset_start_date(csv_bytes)

    params = ScenarioParams(
        dataset_id=dataset_path.stem,
        report_date=report_date,
        horizon_months=args.horizon_months,
        seed=args.seed,
        mc_runs=args.mc_runs,
        mode=args.mode,
        purchase_policy=args.purchase_policy,
        confidence_central=args.confidence,
        purchases=[],
    )

    print(f"\nДатасет: {dataset_path}")
    print(f"Дата состояния стада: {report_date:%d.%m.%Y}")
    print(f"Горизонт: {args.horizon_months} мес.; прогонов: {args.mc_runs}")
    print("Выполняется расчёт прогноза...")

    last_reported = {"percent": -10}

    def report_progress(completed: int, total: int, _partial_result) -> None:
        percent = int(completed / max(1, total) * 100)
        if percent == 100 or percent >= last_reported["percent"] + 10:
            print(f"  Прогресс: {completed}/{total} ({percent}%)")
            last_reported["percent"] = percent

    result = run_forecast_herd_m5(
        csv_bytes,
        params,
        parallel_enabled=args.processes > 1,
        max_processes=max(1, args.processes),
        batch_size=max(1, min(10, args.mc_runs)),
        simulation_version="1.1.0",
        progress_callback=report_progress,
    )

    output_path = args.output
    if output_path is None:
        safe_name = "".join(char if char.isalnum() else "_" for char in dataset_path.stem).strip("_")
        output_path = DEFAULT_OUTPUT_DIR / f"dim_forecast_{safe_name}.png"
    else:
        output_path = output_path.expanduser().resolve()

    plot_forecast(
        result=result,
        dataset_path=dataset_path,
        output_path=output_path,
        confidence=args.confidence,
        mode=args.mode,
        mc_runs=args.mc_runs,
        show=args.show,
    )


if __name__ == "__main__":
    main()
