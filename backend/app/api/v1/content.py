import re
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.errors import not_found
from app.core.permissions import MANAGERS, SCHOOL_WIDE
from app.core.ratelimit import client_ip
from app.models import Role, User
from app.models.enums import MaterialType
from app.schemas.common import Page, PageParams, page_params
from app.schemas.content import DiaryIn, DiaryOut, MaterialOut, SubmissionCheckIn, SubmissionOut, SubmissionRow
from app.services import content as svc
from app.services.storage import StorageBackend, get_storage

router = APIRouter(tags=["diary & materials"])
Writer = Annotated[User, Depends(require_roles(*MANAGERS, Role.TEACHER))]
Staff = Annotated[User, Depends(require_roles(*SCHOOL_WIDE, Role.TEACHER))]
Storage = Annotated[StorageBackend, Depends(get_storage)]


@router.get("/diary", response_model=list[DiaryOut])
async def list_diary(
    user: CurrentUser,
    db: DbSession,
    date_: date = Query(alias="date"),
    class_id: uuid.UUID | None = Query(None),
    section_id: uuid.UUID | None = Query(None),
    student_id: uuid.UUID | None = Query(None, description="Parent: which child"),
):
    return await svc.list_diary(db, user, day=date_, class_id=class_id, section_id=section_id, student_id=student_id)


@router.post("/diary", response_model=DiaryOut, status_code=status.HTTP_201_CREATED)
async def create_diary(body: DiaryIn, request: Request, db: DbSession, actor: Writer):
    return await svc.create_diary(db, actor, body, client_ip(request))


@router.put("/diary/{entry_id}", response_model=DiaryOut)
async def update_diary(entry_id: uuid.UUID, body: DiaryIn, request: Request, db: DbSession, actor: Writer):
    return await svc.update_diary(db, actor, entry_id, body, client_ip(request))


@router.delete("/diary/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_diary(entry_id: uuid.UUID, request: Request, db: DbSession, actor: Writer, storage: Storage):
    await svc.delete_diary(db, actor, entry_id, storage, client_ip(request))


@router.put("/diary/{entry_id}/attachment", response_model=DiaryOut)
async def set_attachment(
    entry_id: uuid.UUID, db: DbSession, actor: Writer, storage: Storage, file: UploadFile | None = File(None)
):
    """Upload replaces the attachment; sending no file removes it."""
    return await svc.set_diary_attachment(db, actor, entry_id, file, storage)


@router.post("/diary/{entry_id}/submission", response_model=SubmissionOut)
async def submit_work(
    entry_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_roles(Role.STUDENT))],
    storage: Storage,
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    return await svc.submit_work(db, actor, entry_id, note, file, storage)


@router.get("/diary/{entry_id}/submissions", response_model=list[SubmissionRow])
async def list_submissions(entry_id: uuid.UUID, db: DbSession, actor: Staff):
    return await svc.list_submissions(db, actor, entry_id)


@router.put("/diary/submissions/{submission_id}", response_model=SubmissionOut)
async def check_submission(submission_id: uuid.UUID, body: SubmissionCheckIn, db: DbSession, actor: Writer):
    return await svc.check_submission(db, actor, submission_id, body)


@router.get("/materials", response_model=Page[MaterialOut])
async def list_materials(
    user: CurrentUser,
    db: DbSession,
    params: Annotated[PageParams, Depends(page_params)],
    class_id: uuid.UUID | None = Query(None),
    subject_id: uuid.UUID | None = Query(None),
    type: MaterialType | None = Query(None),
    student_id: uuid.UUID | None = Query(None, description="Parent: which child"),
):
    return await svc.list_materials(
        db, user, params, class_id=class_id, subject_id=subject_id, type_=type, student_id=student_id
    )


@router.post("/materials", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
async def create_material(
    request: Request,
    db: DbSession,
    actor: Writer,
    storage: Storage,
    title: str = Form(...),
    type: MaterialType = Form(...),
    class_id: uuid.UUID = Form(...),
    section_id: uuid.UUID | None = Form(None),
    subject_id: uuid.UUID | None = Form(None),
    description: str | None = Form(None, max_length=2000),
    external_link: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    return await svc.create_material(
        db,
        actor,
        title=title,
        description=description,
        type_=type,
        class_id=class_id,
        section_id=section_id,
        subject_id=subject_id,
        external_link=external_link,
        file=file,
        storage=storage,
        ip=client_ip(request),
    )


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(material_id: uuid.UUID, request: Request, db: DbSession, actor: Writer, storage: Storage):
    await svc.delete_material(db, actor, material_id, storage, client_ip(request))


_STORED_NAME = re.compile(r"[0-9a-f]{32}\.[a-z]{3,4}")  # storage writes uuid4().hex + extension


@router.get(
    settings.upload_url_prefix.removeprefix("/api/v1") + "/{folder}/{name}",
    response_class=FileResponse,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def download_file(folder: str, name: str, db: DbSession, user: CurrentUser):
    """Diary attachments, homework and materials at their stored URL: login + row scope, else 404.
    Photos and logos never get here; they are public static mounts registered first (main.py)."""
    if not _STORED_NAME.fullmatch(name):
        raise not_found("File")
    await svc.assert_can_download(db, user, folder, f"{settings.upload_url_prefix}/{folder}/{name}")
    path = Path(settings.upload_dir) / folder / name
    if not path.is_file():
        raise not_found("File")
    return FileResponse(
        path,
        filename=name,  # Content-Disposition: attachment
        headers={
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",  # shared computers: keep it out of the disk cache
        },
    )
