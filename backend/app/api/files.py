"""/api/files — authenticated upload endpoints."""

from fastapi import APIRouter, Depends, File, UploadFile

from app.core.security import get_current_user
from app.models import User
from app.schemas.file import UploadFilesResponse
from app.services import file_service

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload", response_model=UploadFilesResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    _: User = Depends(get_current_user),
):
    saved = await file_service.upload_files(files)
    return UploadFilesResponse(files=saved)
