import os
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, inspect, or_, select, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from . import models, schemas
from .auth import (create_token, get_current_user, get_optional_user,
                   hash_password, require_admin, verify_password)
from .database import Base, engine, get_db
from .image_features import ImageModelError, InvalidImageError, extract_embedding
from .matching import find_matches

Base.metadata.create_all(engine)  # tables apne aap ban jayenge
if "image_embedding" not in {column["name"] for column in inspect(engine).get_columns("items")}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE items ADD COLUMN image_embedding TEXT"))

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
logger = logging.getLogger(__name__)

# Ye emails register karte hi admin ban jayengi, e.g. ADMIN_EMAILS="security@srmu.ac.in,proctor@srmu.ac.in"
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}

ItemType = Literal["lost", "found"]
Category = Literal["gadgets", "id_cards", "keys_bags", "other"]

app = FastAPI(title="SRMU Campus Recover API")

app.add_middleware(
    CORSMiddleware,
    # Dev ke liye localhost / 127.0.0.1 ka koi bhi port allowed (Live Server 5500, Live Preview 3000, Vite 5173...)
    # Deploy karte waqt isko hatake apna frontend URL allow_origins mein daalo.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ---------------------------------------------------------------- helpers
def item_to_out(item: models.Item, viewer: Optional[models.User] = None) -> schemas.ItemOut:
    can_see_secret = viewer is not None and (viewer.id == item.reporter_id or viewer.role == "admin")
    return schemas.ItemOut(
        id=item.id,
        type=item.type,
        title=item.title,
        category=item.category,
        description=item.description,
        location=item.location,
        event_time=item.event_time,
        reward=item.reward,
        status=item.status,
        image_url=f"/uploads/{item.image_path}" if item.image_path else None,
        reporter_id=item.reporter_id,
        reporter_name=item.reporter.name,
        created_at=item.created_at,
        secret_identifier=item.secret_identifier if can_see_secret else None,
    )


def claim_to_out(c: models.Claim) -> schemas.ClaimOut:
    return schemas.ClaimOut(id=c.id, item_id=c.item_id, item_title=c.item.title,
                            status=c.status, admin_note=c.admin_note, created_at=c.created_at)


async def save_image(image: UploadFile) -> tuple[str, str]:
    ext = Path(image.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Only jpg, jpeg, png, webp images are allowed")
    data = await image.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image must be under 5 MB")
    try:
        embedding = await run_in_threadpool(extract_embedding, data)
    except InvalidImageError as exc:
        raise HTTPException(400, "Uploaded file is not a valid image") from exc
    except ImageModelError as exc:
        logger.exception("Could not generate image embedding")
        raise HTTPException(503, "Image matching model is unavailable") from exc
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / name).write_bytes(data)
    return name, json.dumps(embedding)


# ---------------------------------------------------------------- auth
@app.post("/auth/register", response_model=schemas.TokenOut, status_code=201, tags=["auth"])
def register(body: schemas.RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise HTTPException(400, "Email already registered")
    user = models.User(
        name=body.name,
        email=email,
        student_id=body.student_id,
        password_hash=hash_password(body.password),
        role="admin" if email in ADMIN_EMAILS else "student",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return schemas.TokenOut(access_token=create_token(user.id), user=schemas.UserOut.model_validate(user))


@app.post("/auth/login", response_model=schemas.TokenOut, tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 form mein field ka naam "username" hota hai, yahan us mein email bhejna hai
    user = db.scalar(select(models.User).where(models.User.email == form.username.lower()))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return schemas.TokenOut(access_token=create_token(user.id), user=schemas.UserOut.model_validate(user))


@app.get("/auth/me", response_model=schemas.UserOut, tags=["auth"])
def me(user: models.User = Depends(get_current_user)):
    return user


# ---------------------------------------------------------------- items
@app.post("/items", response_model=schemas.ItemOut, status_code=201, tags=["items"])
async def create_item(
    type: ItemType = Form(...),
    title: str = Form(..., min_length=3, max_length=150),
    category: Category = Form(...),
    location: str = Form(..., min_length=2, max_length=150),
    event_time: datetime = Form(...),
    description: str = Form("", max_length=1000),
    secret_identifier: Optional[str] = Form(None, max_length=255),
    reward: Optional[str] = Form(None, max_length=100),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    image_name, image_embedding = (
        await save_image(image) if image and image.filename else (None, None)
    )
    item = models.Item(
        type=type, title=title, category=category, location=location,
        event_time=event_time, description=description,
        secret_identifier=secret_identifier or None, reward=reward or None,
        image_path=image_name, image_embedding=image_embedding, reporter_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item_to_out(item, user)


@app.get("/items", response_model=list[schemas.ItemOut], tags=["items"])
def list_items(
    type: Optional[ItemType] = None,
    category: Optional[Category] = None,
    status: Optional[Literal["open", "claimed"]] = None,
    location: Optional[str] = None,
    q: Optional[str] = Query(None, description="title / description / location mein search"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    viewer: Optional[models.User] = Depends(get_optional_user),
):
    query = select(models.Item).order_by(models.Item.created_at.desc())
    if type:
        query = query.where(models.Item.type == type)
    if category:
        query = query.where(models.Item.category == category)
    if status:
        query = query.where(models.Item.status == status)
    if location:
        query = query.where(models.Item.location.ilike(f"%{location}%"))
    if q:
        like = f"%{q}%"
        query = query.where(or_(models.Item.title.ilike(like),
                                models.Item.description.ilike(like),
                                models.Item.location.ilike(like)))
    items = db.scalars(query.offset(skip).limit(limit)).all()
    return [item_to_out(i, viewer) for i in items]


# NOTE: "/items/mine" ko "/items/{item_id}" se pehle rakhna zaroori hai
@app.get("/items/mine", response_model=list[schemas.ItemOut], tags=["items"])
def my_items(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    items = db.scalars(select(models.Item).where(models.Item.reporter_id == user.id)
                       .order_by(models.Item.created_at.desc())).all()
    return [item_to_out(i, user) for i in items]


@app.get("/items/{item_id}", response_model=schemas.ItemOut, tags=["items"])
def get_item(item_id: int, db: Session = Depends(get_db),
             viewer: Optional[models.User] = Depends(get_optional_user)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item_to_out(item, viewer)


@app.get("/items/{item_id}/matches", response_model=list[schemas.MatchOut], tags=["items"])
def item_matches(item_id: int, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    """Smart matching: is item se milte-julte opposite type ke open items (sirf owner/admin ke liye)."""
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if item.reporter_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not allowed")
    if item.status != "open":
        return []
    try:
        matches = find_matches(db, item)
    except ImageModelError as exc:
        logger.exception("Could not generate image embeddings for matching")
        raise HTTPException(503, "Image matching model is unavailable") from exc
    return [
        schemas.MatchOut(
            score=score,
            image_similarity_percent=image_similarity,
            reasons=reasons,
            item=item_to_out(m, user),
        )
        for m, score, reasons, image_similarity in matches
    ]


@app.delete("/items/{item_id}", status_code=204, tags=["items"])
def delete_item(item_id: int, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if item.reporter_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not allowed")
    if item.image_path:
        (UPLOAD_DIR / item.image_path).unlink(missing_ok=True)
    db.delete(item)
    db.commit()


# ---------------------------------------------------------------- claims
# "Claim Item" (found item par) aur "I Found This" (lost item par) dono isi endpoint se chalte hain.
@app.post("/items/{item_id}/claim", response_model=schemas.ClaimOut, status_code=201, tags=["claims"])
def create_claim(item_id: int, body: schemas.ClaimIn, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if item.status != "open":
        raise HTTPException(400, "Item is already resolved")
    if item.reporter_id == user.id:
        raise HTTPException(400, "You cannot claim your own item")
    already = db.scalar(select(models.Claim).where(
        models.Claim.item_id == item_id,
        models.Claim.claimer_id == user.id,
        models.Claim.status == "pending"))
    if already:
        raise HTTPException(400, "You already have a pending claim on this item")
    claim = models.Claim(item_id=item_id, claimer_id=user.id, proof_answer=body.proof_answer)
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return claim_to_out(claim)


@app.get("/claims/mine", response_model=list[schemas.ClaimOut], tags=["claims"])
def my_claims(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    claims = db.scalars(select(models.Claim).where(models.Claim.claimer_id == user.id)
                        .order_by(models.Claim.created_at.desc())).all()
    return [claim_to_out(c) for c in claims]


# ---------------------------------------------------------------- admin (security desk)
@app.get("/admin/claims", response_model=list[schemas.AdminClaimOut], tags=["admin"])
def admin_list_claims(status: Literal["pending", "approved", "rejected"] = "pending",
                      db: Session = Depends(get_db), _: models.User = Depends(require_admin)):
    claims = db.scalars(select(models.Claim).where(models.Claim.status == status)
                        .order_by(models.Claim.created_at)).all()
    return [
        schemas.AdminClaimOut(
            **claim_to_out(c).model_dump(),
            proof_answer=c.proof_answer,
            item_secret_identifier=c.item.secret_identifier,
            claimer_name=c.claimer.name,
            claimer_email=c.claimer.email,
            claimer_student_id=c.claimer.student_id,
        )
        for c in claims
    ]


@app.post("/admin/claims/{claim_id}/review", response_model=schemas.ClaimOut, tags=["admin"])
def admin_review_claim(claim_id: int, body: schemas.ReviewIn, db: Session = Depends(get_db),
                       _: models.User = Depends(require_admin)):
    claim = db.get(models.Claim, claim_id)
    if not claim:
        raise HTTPException(404, "Claim not found")
    if claim.status != "pending":
        raise HTTPException(400, "Claim already reviewed")
    claim.admin_note = body.note
    if body.approve:
        claim.status = "approved"
        claim.item.status = "claimed"
        # is item ke baaki pending claims apne aap reject
        for other in claim.item.claims:
            if other.id != claim.id and other.status == "pending":
                other.status = "rejected"
                other.admin_note = "Item was handed over to another verified claimant"
    else:
        claim.status = "rejected"
    db.commit()
    db.refresh(claim)
    return claim_to_out(claim)


# ---------------------------------------------------------------- stats (homepage ke counters)
@app.get("/stats", tags=["stats"])
def stats(db: Session = Depends(get_db)):
    def count(*conds):
        return db.scalar(select(func.count()).select_from(models.Item).where(*conds))

    return {
        "reunited": count(models.Item.status == "claimed"),
        "lost_open": count(models.Item.type == "lost", models.Item.status == "open"),
        "found_open": count(models.Item.type == "found", models.Item.status == "open"),
        "total_open": count(models.Item.status == "open"),
    }