"""Score open opposite-type items using metadata and, when available, image similarity."""
import json
import logging
import math
import re
from pathlib import Path

from .image_features import InvalidImageError, extract_embedding

logger = logging.getLogger(__name__)
UPLOAD_DIR = Path("uploads")
IMAGE_ONLY_THRESHOLD = 0.80

STOP = {"a", "an", "the", "of", "in", "on", "at", "with", "and", "or", "for", "to", "near", "by",
        "from", "is", "it", "my", "i", "lost", "found", "item", "has", "have", "was", "are"}

# Milte-julte shabd ek hi maane jayenge (words singular karne ke baad check hote hain)
SYN = {
    "airpod": "earbud", "earphone": "earbud", "bud": "earbud", "headphone": "earbud",
    "mobile": "phone", "smartphone": "phone", "cellphone": "phone", "iphone": "phone",
    "backpack": "bag", "sack": "bag", "handbag": "bag",
    "keychain": "key", "wristwatch": "watch", "calc": "calculator",
    "flask": "bottle", "idcard": "id", "adapter": "charger",
}

# Campus zones: location text mein ye keywords milein to wo zone maana jayega
ZONES = {
    "library": ["library"],
    "admin": ["admin", "fountain"],
    "engineering": ["engineering", "workshop", "lab"],
    "canteen": ["cafeteria", "canteen", "mess"],
    "sports": ["cricket", "gym", "sports", "pavilion", "court", "ground"],
    "hostel": ["hostel"],
    "parking": ["parking", "gate"],
}


def tokens(text):
    out = set()
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if w in STOP or len(w) < 2:
            continue
        if len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        out.add(SYN.get(w, w))
    return out


def zone_of(location):
    text = (location or "").lower()
    for zone, words in ZONES.items():
        if any(k in text for k in words):
            return zone
    return None


def score_pair(a, b):
    """a aur b opposite type ke items hain. Return: (score, reasons, text_ratio)"""
    lost, found = (a, b) if a.type == "lost" else (b, a)
    score, reasons = 0, []

    # 1. Category (30)
    if lost.category == found.category:
        score += 30
        reasons.append("Same category")
    elif "other" in (lost.category, found.category):
        score += 10

    # 2. Title + description words (40)
    ta = tokens(lost.title) | tokens(lost.description)
    tb = tokens(found.title) | tokens(found.description)
    ratio = len(ta & tb) / math.sqrt(len(ta) * len(tb)) if ta and tb else 0.0
    score += round(40 * min(ratio, 1.0))
    if ratio > 0:
        reasons.append("Similar title / description")

    # 3. Campus zone (20)
    za, zb = zone_of(lost.location), zone_of(found.location)
    if za and za == zb:
        score += 20
        reasons.append("Same campus zone")
    elif not za and not zb:
        la, lb = tokens(lost.location), tokens(found.location)
        if la and lb:
            score += round(20 * len(la & lb) / math.sqrt(len(la) * len(lb)))

    # 4. Time (10): found item, lost hone ke baad ke 2 din ke andar mila ho to best
    hours = (found.event_time - lost.event_time).total_seconds() / 3600
    if -6 <= hours <= 48:
        score += 10
        reasons.append("Reported close in time")
    elif 48 < hours <= 168:
        score += 5

    return min(score, 100), reasons, ratio


def _embedding_for(item):
    if item.image_embedding:
        try:
            vector = json.loads(item.image_embedding)
            if isinstance(vector, list) and vector and all(
                isinstance(value, (int, float)) for value in vector
            ):
                return vector
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid stored image embedding for item %s", item.id)

    if not item.image_path:
        return None
    try:
        vector = extract_embedding((UPLOAD_DIR / item.image_path).read_bytes())
    except FileNotFoundError:
        logger.warning("Image file missing for item %s", item.id)
        return None
    except InvalidImageError:
        logger.warning("Image file is invalid for item %s", item.id)
        return None
    item.image_embedding = json.dumps(vector)
    return vector


def _cosine_similarity(a, b):
    if len(a) != len(b):
        return 0.0
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))


def find_matches(db, item, limit=5, min_score=40):
    """Return: (item, overall score, reasons, optional image similarity), best first."""
    from sqlalchemy import select
    from . import models

    opposite = "found" if item.type == "lost" else "lost"
    candidates = db.scalars(
        select(models.Item)
        .where(models.Item.type == opposite,
               models.Item.status == "open",
               models.Item.reporter_id != item.reporter_id)
        .order_by(models.Item.created_at.desc())
        .limit(300)
    ).all()

    results = []
    changed_embeddings = False
    previous_embedding = item.image_embedding
    item_embedding = _embedding_for(item)
    changed_embeddings = item.image_embedding != previous_embedding

    for c in candidates:
        metadata_score, reasons, ratio = score_pair(item, c)
        previous_embedding = c.image_embedding
        candidate_embedding = _embedding_for(c) if item_embedding is not None else None
        if c.image_embedding != previous_embedding:
            changed_embeddings = True

        similarity = (
            _cosine_similarity(item_embedding, candidate_embedding)
            if item_embedding is not None and candidate_embedding is not None
            else None
        )
        if similarity is not None:
            similarity_score = round(max(0.0, similarity) * 100)
            if similarity >= IMAGE_ONLY_THRESHOLD:
                reasons.append("Visually similar image")
            if ratio > 0:
                score = round(metadata_score * 0.6 + similarity_score * 0.4)
                if score >= min_score:
                    results.append((c, score, reasons, similarity_score))
            elif similarity >= IMAGE_ONLY_THRESHOLD:
                results.append((c, similarity_score, reasons, similarity_score))
        elif ratio > 0 and metadata_score >= min_score:
            results.append((c, metadata_score, reasons, None))

    if changed_embeddings:
        db.commit()
    results.sort(key=lambda r: r[1], reverse=True)
    return results[:limit]