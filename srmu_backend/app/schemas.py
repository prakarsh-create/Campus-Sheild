from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- Auth ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=6, max_length=100)
    student_id: Optional[str] = Field(default=None, max_length=30)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    student_id: Optional[str]
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Items ----------
class ItemOut(BaseModel):
    id: int
    type: str
    title: str
    category: str
    description: str
    location: str
    event_time: datetime
    reward: Optional[str]
    status: str
    image_url: Optional[str]
    reporter_id: int
    reporter_name: str
    created_at: datetime
    # sirf owner aur admin ko dikhta hai, baaki sab ke liye None
    secret_identifier: Optional[str] = None


class MatchOut(BaseModel):
    score: int          # 0-100
    image_similarity_percent: Optional[int] = None  # CNN cosine similarity; None if images unavailable
    reasons: list[str]  # kyun match laga
    item: ItemOut


# ---------- Claims ----------
class ClaimIn(BaseModel):
    proof_answer: str = Field(min_length=3, max_length=500)


class ClaimOut(BaseModel):
    id: int
    item_id: int
    item_title: str
    status: str
    admin_note: Optional[str]
    created_at: datetime


class AdminClaimOut(ClaimOut):
    proof_answer: str
    item_secret_identifier: Optional[str]  # admin isko proof_answer se match karega
    claimer_name: str
    claimer_email: str
    claimer_student_id: Optional[str]


class ReviewIn(BaseModel):
    approve: bool
    note: Optional[str] = Field(default=None, max_length=255)