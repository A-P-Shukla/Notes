from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, get_current_user, hash_password, verify_password
from database import get_db
from models import Note, NoteRevision, User, note_shares
from schemas import (
    LoginRequest,
    MessageResponse,
    NoteCreate,
    NoteResponse,
    NoteRevisionResponse,
    NoteShareCreate,
    TokenResponse,
    UserCreate,
    UserResponse,
)


router = APIRouter()

def user_can_access_note(user_id: int):
    shared_note = (
        select(note_shares.c.note_id)
        .where(
            note_shares.c.note_id == Note.id,
            note_shares.c.user_id == user_id,
        )
        .exists()
    )
    return or_(Note.owner_id == user_id, shared_note)


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    user = User(
        email=str(payload.email).lower(),
        hashed_password=hash_password(payload.password),
    )
    db.add(user)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Email already registered"},
        ) from exc

    return MessageResponse(message="User registered successfully")


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str] | JSONResponse:
    result = await db.execute(
        select(User).where(User.email == str(payload.email).lower()),
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"message": "Invalid email or password"},
        )

    return {"access_token": create_access_token(str(user.id))}


@router.get(
    "/notes",
    response_model=list[NoteResponse],
    status_code=status.HTTP_200_OK,
)
async def list_notes(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Note]:
    result = await db.execute(
        select(Note)
        .where(user_can_access_note(current_user.id))
        .order_by(Note.created_at.desc(), Note.id.desc())
        .offset(skip)
        .limit(limit),
    )
    return list(result.scalars().all())


@router.post(
    "/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_note(
    payload: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Note:
    note = Note(
        title=payload.title,
        content=payload.content,
        owner_id=current_user.id,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@router.get(
    "/search",
    response_model=list[NoteResponse],
    status_code=status.HTTP_200_OK,
)
async def search_notes(
    q: str = Query(min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Note]:
    keyword = f"%{q}%"
    result = await db.execute(
        select(Note)
        .where(
            user_can_access_note(current_user.id),
            or_(Note.title.ilike(keyword), Note.content.ilike(keyword)),
        )
        .order_by(Note.created_at.desc(), Note.id.desc()),
    )
    return list(result.scalars().all())


@router.get(
    "/notes/{id}",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
)
async def get_note(
    note_id: int = Path(alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Note:
    result = await db.execute(
        select(Note).where(
            Note.id == note_id,
            user_can_access_note(current_user.id),
        ),
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Note not found"},
        )
    return note


@router.put(
    "/notes/{id}",
    response_model=NoteResponse,
    status_code=status.HTTP_200_OK,
)
async def update_note(
    payload: NoteCreate,
    note_id: int = Path(alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Note:
    note = await db.get(Note, note_id)
    if note is None or note.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Note not found"},
        )

    revision = NoteRevision(
        note_id=note.id,
        title=note.title,
        content=note.content,
    )
    db.add(revision)

    note.title = payload.title
    note.content = payload.content

    await db.commit()
    await db.refresh(note)
    return note


@router.get(
    "/notes/{id}/revisions",
    response_model=list[NoteRevisionResponse],
    status_code=status.HTTP_200_OK,
)
async def list_note_revisions(
    note_id: int = Path(alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NoteRevision]:
    # Owner-only — shared users must NOT see revision history
    note = await db.get(Note, note_id)
    if note is None or note.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Note not found"},
        )

    revisions_result = await db.execute(
        select(NoteRevision)
        .where(NoteRevision.note_id == note_id)
        .order_by(NoteRevision.updated_at.desc(), NoteRevision.id.desc()),
    )
    return list(revisions_result.scalars().all())


@router.post(
    "/notes/{id}/share",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def share_note(
    payload: NoteShareCreate,
    note_id: int = Path(alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    note = await db.get(Note, note_id)
    if note is None or note.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Note not found"},
        )

    result = await db.execute(
        select(User).where(User.email == str(payload.share_with_email).lower()),
    )
    share_with_user = result.scalar_one_or_none()
    if share_with_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "User not found"},
        )

    if share_with_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Cannot share a note with yourself"},
        )

    existing_share = await db.execute(
        select(note_shares).where(
            note_shares.c.note_id == note.id,
            note_shares.c.user_id == share_with_user.id,
        ),
    )
    if existing_share.first() is None:
        await db.execute(
            insert(note_shares).values(
                note_id=note.id,
                user_id=share_with_user.id,
            ),
        )
        await db.commit()

    return MessageResponse(message="Note shared successfully")


@router.delete(
    "/notes/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_note(
    note_id: int = Path(alias="id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    note = await db.get(Note, note_id)
    if note is None or note.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Note not found"},
        )

    await db.delete(note)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
