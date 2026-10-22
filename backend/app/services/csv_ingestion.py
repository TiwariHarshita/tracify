import hashlib
import json
import os
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.workspace import Dataset
from app.services import workspace as storage
from app.services.csv_parser import CsvRejected, PARSER_VERSION, parse_csv


def artifact_path(dataset: Dataset, kind: str) -> Path:
    return storage.private_path(dataset.storage_key).with_suffix("." + kind)


def verified_source(dataset: Dataset) -> bytes:
    raw = storage.private_path(dataset.storage_key)
    if not raw.is_file():
        raise HTTPException(409, "Dataset file is missing. Re-upload the CSV.")
    data = raw.read_bytes()
    if hashlib.sha256(data).hexdigest() != dataset.sha256:
        raise HTTPException(409, "Dataset file changed outside Trace. Re-upload it; the stored version is immutable.")
    return data


def write_atomic(path: Path, content: str):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_artifacts(dataset: Dataset, profile: dict, rows: list[dict], errors: list[dict]):
    # Publish the manifest last, so an incomplete write is never a ready profile.
    for kind, records in [("rows.jsonl", rows), ("errors.jsonl", errors)]:
        write_atomic(artifact_path(dataset, kind), "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records))
    write_atomic(artifact_path(dataset, "profile.json"), json.dumps(profile, ensure_ascii=False))


def ensure_profile(dataset: Dataset) -> dict:
    manifest = artifact_path(dataset, "profile.json")
    data = verified_source(dataset)
    delimiter = ","
    if manifest.exists():
        try:
            profile = json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise HTTPException(409, "Profile metadata is damaged. Delete this unused dataset and re-upload it.") from None
        delimiter = profile.get("delimiter", ",")
        if profile.get("parser_version") == PARSER_VERSION and profile.get("sha256") == dataset.sha256 and all(
            artifact_path(dataset, kind).exists() for kind in ["rows.jsonl", "errors.jsonl"]
        ):
            return profile
    elif not dataset.source_url:
        # Never guess the delimiter again for an uploaded file if its parse
        # configuration has been lost. Legacy bundled samples use comma.
        raise HTTPException(409, "Upload profile is missing. Delete this unused dataset and re-upload it.")
    try:
        profile, rows, errors = parse_csv(data, delimiter)
    except CsvRejected as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    save_artifacts(dataset, profile, rows, errors)
    return profile


def ensure_analyzable(dataset: Dataset):
    profile = ensure_profile(dataset)
    if not profile["analysis_ready"]:
        raise HTTPException(422, "This CSV has unreadable records. Review its profile, fix the source, and upload the corrected file before creating a report.")


def cleanup_files(dataset: Dataset):
    for kind in ["csv", "rows.jsonl", "errors.jsonl", "profile.json"]:
        artifact_path(dataset, kind).unlink(missing_ok=True)


def upload_dataset(db: Session, owner_id, data: bytes, filename: str, delimiter: str) -> Dataset:
    try:
        profile, rows, errors = parse_csv(data, delimiter)
    except CsvRejected as exc:
        raise HTTPException(exc.status_code, exc.detail) from None
    digest = profile["sha256"]
    existing = db.scalar(select(Dataset).where(Dataset.owner_id == owner_id, Dataset.sha256 == digest))
    if existing:
        old = ensure_profile(existing)
        if old["delimiter"] != delimiter:
            raise HTTPException(409, "This file already exists with another delimiter. Delete its unused dataset first or upload a corrected CSV.")
        return existing
    safe_name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = Path(safe_name).stem.strip()[:120] or "Uploaded dataset"
    dataset = Dataset(
        owner_id=owner_id, name=name, storage_key=uuid.uuid4().hex + ".csv",
        sha256=digest, source_url="", row_count=profile["readable_rows"],
        column_count=len(profile["columns"]),
    )
    storage.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        storage.private_path(dataset.storage_key).write_bytes(data)
        save_artifacts(dataset, profile, rows, errors)
        db.add(dataset)
        db.commit()
    except IntegrityError:
        db.rollback()
        cleanup_files(dataset)
        existing = db.scalar(select(Dataset).where(Dataset.owner_id == owner_id, Dataset.sha256 == digest))
        if existing:
            if ensure_profile(existing)["delimiter"] != delimiter:
                raise HTTPException(409, "Concurrent import used a different delimiter.") from None
            return existing
        raise HTTPException(409, "Could not save dataset. Please try again.") from None
    except Exception:
        db.rollback()
        cleanup_files(dataset)
        raise
    db.refresh(dataset)
    return dataset


def read_page(dataset: Dataset, kind: str, offset: int, limit: int) -> dict:
    profile = ensure_profile(dataset)
    total = profile["readable_rows"] if kind == "rows.jsonl" else profile["error_count"]
    items = []
    with artifact_path(dataset, kind).open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if index < offset:
                continue
            if len(items) >= limit:
                break
            items.append(json.loads(line))
    return {"items": items, "total": total, "offset": offset, "limit": limit}
