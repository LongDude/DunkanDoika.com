import io

from app.simulator.loader import (
    COL_ANIMAL_ID,
    COL_ARCHIVE_DATE,
    COL_BIRTH_DATE,
    COL_DAYS_IN_MILK,
    COL_DRYOFF_DATE,
    COL_LACTATION,
    COL_LACTATION_START,
    COL_STATUS,
    load_dataset_with_quality,
)


def test_dataset_quality_issues_are_detected() -> None:
    csv = f"""{COL_ANIMAL_ID};{COL_BIRTH_DATE};{COL_STATUS};{COL_LACTATION};{COL_LACTATION_START};{COL_DAYS_IN_MILK};{COL_ARCHIVE_DATE};{COL_DRYOFF_DATE}
1;01.01.2023;ok;1;01.12.2025;70;;
1;01.01.2022;ok;1;bad-date;120;01.01.2020;
3;01.02.2025;ok;0;01.02.2026;0;;
"""
    loaded = load_dataset_with_quality(io.BytesIO(csv.encode("utf-8")))
    codes = {issue["code"] for issue in loaded.quality_issues}

    assert "duplicate_animal_id" in codes
    assert "invalid_date_values" in codes
    assert "inconsistent_lactation" in codes
    assert "archive_outside_730_days" in codes
