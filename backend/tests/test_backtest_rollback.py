from __future__ import annotations

from datetime import date, timedelta

import pytest

from scripts.evaluate_milk_days_forecast import (
    COL_ARCHIVE,
    COL_BIRTH,
    COL_CALVING,
    COL_DAYS_PREGNANT,
    COL_DIM,
    COL_DRY,
    COL_EXPECTED_CALVING,
    COL_EXPECTED_DRY,
    COL_ID,
    COL_INSEM,
    COL_LACTATION,
    COL_STATUS,
    COL_SUCCESS_INSEM,
    actual_dim_snapshot,
    build_parser,
    build_quality_warnings,
    rollback_dataset,
)


FIELDS = [
    COL_ID,
    COL_BIRTH,
    COL_ARCHIVE,
    COL_LACTATION,
    COL_CALVING,
    COL_DIM,
    COL_STATUS,
    COL_INSEM,
    COL_SUCCESS_INSEM,
    COL_DAYS_PREGNANT,
    COL_DRY,
    COL_EXPECTED_DRY,
    COL_EXPECTED_CALVING,
]


def _fmt(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value is not None else ""


def _row(
    animal_id: str,
    *,
    birth: date,
    lactation: int = 1,
    calving: date | None = None,
    status: str = "Дойная",
    archive: date | None = None,
    conception: date | None = None,
    dry: date | None = None,
) -> dict[str, str]:
    return {
        COL_ID: animal_id,
        COL_BIRTH: _fmt(birth),
        COL_ARCHIVE: _fmt(archive),
        COL_LACTATION: str(lactation),
        COL_CALVING: _fmt(calving),
        COL_DIM: "999",
        COL_STATUS: status,
        COL_INSEM: _fmt(conception),
        COL_SUCCESS_INSEM: _fmt(conception),
        COL_DAYS_PREGNANT: "",
        COL_DRY: _fmt(dry),
        COL_EXPECTED_DRY: "01.01.2030",
        COL_EXPECTED_CALVING: "01.03.2030",
    }


def test_rollback_excludes_moved_and_dim_above_limit() -> None:
    cutoff = date(2025, 8, 1)
    rows = [
        _row("valid", birth=date(2020, 1, 1), calving=cutoff - timedelta(days=100)),
        _row("edge", birth=date(2020, 1, 1), calving=cutoff - timedelta(days=350)),
        _row("too-long", birth=date(2020, 1, 1), calving=cutoff - timedelta(days=351)),
        _row(
            "too-long-pregnant",
            birth=date(2020, 1, 1),
            calving=cutoff - timedelta(days=351),
            conception=cutoff - timedelta(days=100),
        ),
        _row("moved", birth=date(2023, 1, 1), lactation=0, calving=None, status="Перемещена"),
    ]

    rolled, cohort, stats = rollback_dataset(
        fieldnames=FIELDS,
        source_rows=rows,
        cutoff=cutoff,
        max_dim_days=350,
    )

    by_id = {row[COL_ID]: row for row in rolled}
    assert cohort == {"valid", "edge", "too-long-pregnant"}
    assert by_id["valid"][COL_DIM] == "100"
    assert by_id["edge"][COL_DIM] == "350"
    assert "too-long" not in by_id
    assert by_id["too-long-pregnant"][COL_STATUS] == "Сухостой"
    assert by_id["too-long-pregnant"][COL_DIM] == "0"
    assert by_id["too-long-pregnant"][COL_DRY] == _fmt(cutoff)
    assert "moved" not in by_id
    assert stats["excluded_dim_above_limit"] == 1
    assert stats["transitioned_to_dry_at_dim_limit"] == 1
    assert stats["excluded_moved_without_date"] == 1


def test_actual_snapshot_uses_same_dim_and_exit_rules() -> None:
    target = date(2025, 8, 1)
    rows = [
        _row("valid", birth=date(2020, 1, 1), calving=target - timedelta(days=100)),
        _row("too-long", birth=date(2020, 1, 1), calving=target - timedelta(days=351)),
        _row("moved", birth=date(2023, 1, 1), calving=target - timedelta(days=50), status="Перемещена"),
    ]

    snapshot = actual_dim_snapshot(
        rows,
        {"valid", "too-long", "moved"},
        target,
        max_dim_days=350,
    )

    assert snapshot["average_dim"] == 100.0
    assert snapshot["milking_count"] == 1
    assert snapshot["forced_dim_limit_count"] == 1


def test_rollback_excludes_conception_after_dim_exit() -> None:
    cutoff = date(2025, 8, 1)
    row = _row(
        "late-conception",
        birth=date(2020, 1, 1),
        calving=cutoff - timedelta(days=400),
        conception=cutoff - timedelta(days=20),
    )
    valid = _row(
        "valid",
        birth=date(2020, 1, 1),
        calving=cutoff - timedelta(days=100),
    )

    rolled, cohort, stats = rollback_dataset(
        fieldnames=FIELDS,
        source_rows=[row, valid],
        cutoff=cutoff,
        max_dim_days=350,
    )

    assert [item[COL_ID] for item in rolled] == ["valid"]
    assert cohort == {"valid"}
    assert stats["excluded_conception_after_dim_limit"] == 1


def test_rollback_keeps_only_pre_cutoff_facts_and_clears_expected_dates() -> None:
    cutoff = date(2025, 8, 1)
    conception = cutoff - timedelta(days=50)
    row = _row(
        "pregnant",
        birth=date(2020, 1, 1),
        calving=cutoff - timedelta(days=150),
        conception=conception,
    )
    row[COL_DRY] = _fmt(cutoff + timedelta(days=100))

    rolled, cohort, _stats = rollback_dataset(
        fieldnames=FIELDS,
        source_rows=[row],
        cutoff=cutoff,
    )

    assert cohort == {"pregnant"}
    assert rolled[0][COL_SUCCESS_INSEM] == _fmt(conception)
    assert rolled[0][COL_DRY] == ""
    assert rolled[0][COL_EXPECTED_DRY] == ""
    assert rolled[0][COL_EXPECTED_CALVING] == ""


def test_rollback_does_not_invent_missing_first_pregnancy() -> None:
    cutoff = date(2025, 8, 1)
    due_soon = _row(
        "due-soon",
        birth=date(2023, 1, 1),
        lactation=1,
        calving=cutoff + timedelta(days=100),
    )
    safely_open = _row(
        "safely-open",
        birth=date(2024, 1, 1),
        lactation=1,
        calving=cutoff + timedelta(days=300),
    )

    rolled, cohort, stats = rollback_dataset(
        fieldnames=FIELDS,
        source_rows=[due_soon, safely_open],
        cutoff=cutoff,
    )

    assert cohort == {"safely-open"}
    assert [row[COL_ID] for row in rolled] == ["safely-open"]
    assert rolled[0][COL_LACTATION] == "0"
    assert rolled[0][COL_CALVING] == ""
    assert stats["excluded_missing_first_pregnancy"] == 1


def test_rollback_rejects_duplicate_animal_ids() -> None:
    cutoff = date(2025, 8, 1)
    row = _row("duplicate", birth=date(2020, 1, 1), calving=cutoff - timedelta(days=100))

    with pytest.raises(ValueError, match="повторяющиеся"):
        rollback_dataset(
            fieldnames=FIELDS,
            source_rows=[row, dict(row)],
            cutoff=cutoff,
        )


@pytest.mark.parametrize("policy", ["auto_counter", "auto_forecast"])
def test_backtest_parser_rejects_auto_purchase_policies(policy: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--purchase-policy", policy])


def test_single_snapshot_quality_is_always_diagnostic() -> None:
    stats = {
        "excluded_missing_previous_lactation": 0,
        "active_cohort_coverage_percent": 100.0,
    }

    warnings = build_quality_warnings(stats, forced_dim_total=0)

    assert warnings
    assert "одному конечному срезу" in warnings[0]
    assert ("diagnostic" if warnings else "passed") == "diagnostic"
