from typing import Literal

from pydantic import BaseModel, ConfigDict


class RootResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"name": "skinulis", "docs": "/docs"}]}
    )
    name: Literal["skinulis"] = "skinulis"
    docs: Literal["/docs"] = "/docs"


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"status": "ok", "database": "ok"}]}
    )
    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class VersionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"version": "0.1.0", "commit_sha": "0" * 40}]}
    )
    version: str
    commit_sha: str | None
