"""
File upload API endpoints.
"""
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from ..auth import get_current_user
from ..config import settings

router = APIRouter()

# Allowed image extensions
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Upload directory (relative to static serving path)
UPLOAD_DIR = "/var/www/shadow-api/uploads/broadcasts"


def get_upload_dir():
    """Get or create upload directory."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    return UPLOAD_DIR


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    _=Depends(get_current_user),
):
    """
    Upload an image file for broadcast.
    Returns the public URL of the uploaded file.
    """
    # Validate file extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Validate content type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="File must be an image"
        )

    # Read and validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // 1024 // 1024}MB"
        )

    # Generate unique filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    safe_filename = f"{timestamp}_{unique_id}{ext}"

    # Save file
    upload_dir = get_upload_dir()
    file_path = os.path.join(upload_dir, safe_filename)

    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {str(e)}"
        )

    # Return public URL
    public_url = f"https://shadow-api.ru/uploads/broadcasts/{safe_filename}"

    return {"url": public_url, "filename": safe_filename}


@router.delete("/image/{filename}")
async def delete_image(
    filename: str,
    _=Depends(get_current_user),
):
    """Delete an uploaded image."""
    # Validate filename (prevent path traversal)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = os.path.join(UPLOAD_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        os.remove(file_path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete file: {str(e)}"
        )

    return {"status": "deleted", "filename": filename}
