from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import UserPresetModel


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class UserPresetRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_for_owner(self, owner_user_id: str) -> list[UserPresetModel]:
        stmt = (
            select(UserPresetModel)
            .where(UserPresetModel.owner_user_id == owner_user_id)
            .where(UserPresetModel.deleted_at.is_(None))
            .order_by(desc(UserPresetModel.updated_at))
        )
        return list(self.session.scalars(stmt).all())

    def create(self, owner_user_id: str, name: str, params_json: dict) -> UserPresetModel:
        row = UserPresetModel(
            owner_user_id=owner_user_id,
            name=name,
            params_json=params_json,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def get_for_owner(self, preset_id: str, owner_user_id: str) -> UserPresetModel | None:
        stmt = (
            select(UserPresetModel)
            .where(UserPresetModel.preset_id == preset_id)
            .where(UserPresetModel.owner_user_id == owner_user_id)
            .where(UserPresetModel.deleted_at.is_(None))
        )
        return self.session.scalar(stmt)

    def update(
        self,
        preset_id: str,
        owner_user_id: str,
        *,
        name: str | None = None,
        params_json: dict | None = None,
    ) -> UserPresetModel | None:
        row = self.get_for_owner(preset_id, owner_user_id)
        if row is None:
            return None
        if name is not None:
            row.name = name
        if params_json is not None:
            row.params_json = params_json
        row.updated_at = now_utc()
        self.session.commit()
        self.session.refresh(row)
        return row

    def soft_delete(self, preset_id: str, owner_user_id: str) -> UserPresetModel | None:
        row = self.get_for_owner(preset_id, owner_user_id)
        if row is None:
            return None
        row.deleted_at = now_utc()
        row.updated_at = now_utc()
        self.session.commit()
        self.session.refresh(row)
        return row

    def bulk_soft_delete(self, preset_ids: Sequence[str], owner_user_id: str) -> tuple[list[str], list[str]]:
        deleted: list[str] = []
        missing: list[str] = []
        for preset_id in preset_ids:
            row = self.soft_delete(preset_id, owner_user_id)
            if row is None:
                missing.append(preset_id)
            else:
                deleted.append(preset_id)
        return deleted, missing
