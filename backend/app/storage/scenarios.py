from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Any, List

from app.api.schemas import ScenarioParams


@dataclass
class Scenario:
    scenario_id: str
    name: str
    params: ScenarioParams
    created_at: datetime

    def public_info(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "dataset_id": self.params.dataset_id,
            "report_date": self.params.report_date,
            "horizon_months": self.params.horizon_months,
        }


class ScenarioStore:
    def __init__(self):
        self._items: Dict[str, Scenario] = {}

    def create(self, name: str, params: ScenarioParams) -> Scenario:
        sid = str(uuid.uuid4())
        s = Scenario(scenario_id=sid, name=name, params=params, created_at=datetime.utcnow())
        self._items[sid] = s
        return s

    def get(self, scenario_id: str) -> Optional[Scenario]:
        return self._items.get(scenario_id)

    def list(self) -> List[Scenario]:
        return sorted(self._items.values(), key=lambda x: x.created_at, reverse=True)


scenario_store = ScenarioStore()
