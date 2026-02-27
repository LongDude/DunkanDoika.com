from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ScenarioParams
from app.db.models import ScenarioModel


class ScenarioRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, name: str, params: ScenarioParams) -> ScenarioModel:
        scenario = ScenarioModel(
            name=name,
            dataset_id=params.dataset_id,
            params_json=params.model_dump(mode="json"),
        )
        self.session.add(scenario)
        self.session.commit()
        self.session.refresh(scenario)
        return scenario

    def get(self, scenario_id: str) -> ScenarioModel | None:
        return self.session.get(ScenarioModel, scenario_id)

    def list(self) -> List[ScenarioModel]:
        stmt = select(ScenarioModel).order_by(ScenarioModel.created_at.desc())
        return list(self.session.scalars(stmt).all())
