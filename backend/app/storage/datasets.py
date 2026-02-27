from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd

from app.simulator.loader import load_dataset_df, suggest_report_date

@dataclass
class Dataset:
    dataset_id: str
    filename: str
    df: pd.DataFrame
    status_counts: Dict[str, int]
    report_date_suggested: Optional[date]

    def public_info(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "filename": self.filename,
            "n_rows": int(len(self.df)),
            "status_counts": self.status_counts,
            "report_date_suggested": self.report_date_suggested,
            "columns": list(self.df.columns),
        }

class DatasetStore:
    def __init__(self, base_dir: Optional[str] = None):
        self._items: Dict[str, Dataset] = {}
        self.base_dir = Path(base_dir or (Path(__file__).resolve().parent.parent / "data" / "uploads"))
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # best-effort reload of uploaded files
        for p in self.base_dir.glob("*.csv"):
            try:
                dataset_id = p.stem
                df = load_dataset_df(str(p))
                status_counts = df["Статус коровы"].value_counts(dropna=False).to_dict()
                rep = suggest_report_date(df)
                self._items[dataset_id] = Dataset(
                    dataset_id=dataset_id,
                    filename=p.name,
                    df=df,
                    status_counts={str(k): int(v) for k, v in status_counts.items()},
                    report_date_suggested=rep,
                )
            except Exception:
                continue

    def save_uploaded_csv(self, filename: str, content: bytes):
        dataset_id = str(uuid.uuid4())

        # persist file for quick reuse after restart
        out_path = self.base_dir / f"{dataset_id}.csv"
        out_path.write_bytes(content)

        df = load_dataset_df(io.BytesIO(content))
        status_counts = df["Статус коровы"].value_counts(dropna=False).to_dict()
        rep = suggest_report_date(df)
        ds = Dataset(
            dataset_id=dataset_id,
            filename=filename,
            df=df,
            status_counts={str(k): int(v) for k, v in status_counts.items()},
            report_date_suggested=rep,
        )
        self._items[dataset_id] = ds
        return {
            "dataset_id": dataset_id,
            "n_rows": int(len(df)),
            "report_date_suggested": rep,
            "status_counts": ds.status_counts,
        }

    def get(self, dataset_id: str) -> Optional[Dataset]:
        return self._items.get(dataset_id)

dataset_store = DatasetStore()
