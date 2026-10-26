from typing import Literal

from pydantic import BaseModel


class RootResponse(BaseModel):
    name: Literal["skinulis"] = "skinulis"
    docs: Literal["/docs"] = "/docs"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class VersionResponse(BaseModel):
    version: str
    commit_sha: str | None
