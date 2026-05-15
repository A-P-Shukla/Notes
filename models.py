from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


note_shares = Table(
    "note_shares",
    Base.metadata,
    Column("note_id", ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    notes: Mapped[list["Note"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    shared_notes: Mapped[list["Note"]] = relationship(
        secondary=note_shares,
        back_populates="shared_with",
    )


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    owner: Mapped[User] = relationship(back_populates="notes")
    shared_with: Mapped[list[User]] = relationship(
        secondary=note_shares,
        back_populates="shared_notes",
    )
    revisions: Mapped[list["NoteRevision"]] = relationship(
        back_populates="note",
        cascade="all, delete-orphan",
    )


class NoteRevision(Base):
    __tablename__ = "note_revisions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    note: Mapped[Note] = relationship(back_populates="revisions")
