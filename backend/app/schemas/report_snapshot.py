from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class PublicReportSnapshotV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["1"]
    analysisResultId: str
    result: dict[str, Any]

