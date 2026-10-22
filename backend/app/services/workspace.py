import csv
import hashlib
import io
import logging
import re
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.workspace import Dataset

logger = logging.getLogger(__name__)
BACKEND_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_FILE = BACKEND_ROOT / "sample_data" / "tips.csv"
STORAGE_ROOT = BACKEND_ROOT.parent / "storage" / "datasets"
SOURCE_URL = "https://github.com/mwaskom/seaborn-data/blob/master/tips.csv"


def private_path(storage_key: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}\.csv", storage_key):
        raise HTTPException(500, "Invalid stored dataset reference")
    return STORAGE_ROOT / storage_key


def import_sample(db: Session, owner_id: uuid.UUID) -> Dataset:
    if not SAMPLE_FILE.is_file():
        raise HTTPException(503, "Sample dataset is missing. Copy sample_data from the package.")
    data = SAMPLE_FILE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Dataset).where(
        Dataset.owner_id == owner_id, Dataset.sha256 == digest
    ))
    if existing:
        return existing
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    if len(rows) < 2:
        raise HTTPException(503, "Sample dataset is invalid")
    dataset = Dataset(
        owner_id=owner_id, name="Restaurant tips",
        storage_key=uuid.uuid4().hex + ".csv", sha256=digest,
        source_url=SOURCE_URL, row_count=len(rows) - 1, column_count=len(rows[0]),
    )
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    path = private_path(dataset.storage_key)
    path.write_bytes(data)
    try:
        db.add(dataset)
        db.commit()
    except IntegrityError:
        db.rollback()
        path.unlink(missing_ok=True)
        # The unique constraint makes simultaneous sample imports idempotent.
        existing = db.scalar(select(Dataset).where(
            Dataset.owner_id == owner_id, Dataset.sha256 == digest
        ))
        if existing:
            return existing
        raise HTTPException(409, "Could not create dataset. Please try again.") from None
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    db.refresh(dataset)
    return dataset


def remove_private_file(storage_key: str):
    try:
        raw = private_path(storage_key)
        for suffix in [".csv", ".rows.jsonl", ".errors.jsonl", ".profile.json"]:
            raw.with_suffix(suffix).unlink(missing_ok=True)
    except OSError:
        # DB deletion is already committed; an orphan is safer than a false failure.
        logger.warning("Could not remove an unused dataset file")
