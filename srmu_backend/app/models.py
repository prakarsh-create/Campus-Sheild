from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    student_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="student")  # student | admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(10), index=True)  # lost | found
    title: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(20), index=True)  # gadgets | id_cards | keys_bags | other
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(150))
    event_time: Mapped[datetime] = mapped_column(DateTime)  # kab kho / mila
    reward: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    secret_identifier: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # public nahi hota
    image_path: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    image_embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)  # open | claimed
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    reporter: Mapped[User] = relationship()
    claims: Mapped[list["Claim"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    claimer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    proof_answer: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | approved | rejected
    admin_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    item: Mapped[Item] = relationship(back_populates="claims")
    claimer: Mapped[User] = relationship()
