from __future__ import annotations

import io
import uuid
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import DatasetModel
from app.simulator.loader import COL_STATUS, load_dataset_df, suggest_report_date
from app.storage.object_storage import storage_client


class DatasetRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_dataset(self, original_filename: str, file_bytes: bytes) -> DatasetModel:
        df = load_dataset_df(io.BytesIO(file_bytes))
        status_counts_raw = df[COL_STATUS].value_counts(dropna=False).to_dict()
        status_counts = {str(k): int(v) for k, v in status_counts_raw.items()}
        report_date_suggested: Optional[date] = suggest_report_date(df)

        dataset_id = str(uuid.uuid4())
        object_key = f"datasets/{dataset_id}.csv"
        storage_client.put_bytes(storage_client.datasets_bucket, object_key, file_bytes, "text/csv")

        dataset = DatasetModel(
            dataset_id=dataset_id,
            original_filename=original_filename,
            object_key=object_key,
            n_rows=int(len(df)),
            report_date_suggested=report_date_suggested,
            status_counts_json=status_counts,
        )
        self.session.add(dataset)
        self.session.commit()
        self.session.refresh(dataset)
        return dataset

    def get(self, dataset_id: str) -> DatasetModel | None:
        return self.session.get(DatasetModel, dataset_id)

    def get_csv_bytes(self, dataset_id: str) -> bytes | None:
        dataset = self.get(dataset_id)
        if dataset is None:
            return None
        return storage_client.get_bytes(storage_client.datasets_bucket, dataset.object_key)
