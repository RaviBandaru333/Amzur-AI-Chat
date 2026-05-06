"""Pydantic schemas for uploaded files."""

from pydantic import BaseModel


class UploadedFileOut(BaseModel):
    filename: str
    content_type: str
    size: int
    url: str


class UploadFilesResponse(BaseModel):
    files: list[UploadedFileOut]
