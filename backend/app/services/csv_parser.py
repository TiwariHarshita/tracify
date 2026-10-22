"""Deterministic, conservative CSV parsing. Raw input is never rewritten."""
import csv
import hashlib
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

PARSER_VERSION = "trace-csv-v1"
MAX_BYTES = 5 * 1024 * 1024
MAX_RECORDS = 50_000
MAX_COLUMNS = 100
MAX_PHYSICAL_LINES = 100_000
csv.field_size_limit(1_000_000)
NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?$")
DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:$|[T ])")
LEADING_ZERO = re.compile(r"^[+-]?0\d+$")


class CsvRejected(ValueError):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def is_number(value: str) -> bool:
    if not NUMBER.fullmatch(value) or len(value) > 100:
        return False
    try:
        return Decimal(value).is_finite()
    except InvalidOperation:
        return False


def is_date(value: str) -> bool:
    try:
        if DATE.fullmatch(value):
            date.fromisoformat(value)
            return True
        if TIMESTAMP.fullmatch(value):
            datetime.fromisoformat(value)
            return True
        return False
    except ValueError:
        return False


def column_profile(index: int, name: str, values: list[str], total: int) -> dict:
    # Only empty/whitespace cells are missing. Labels like NA remain values.
    observed = [value for value in values if value.strip()]
    trimmed = [value.strip() for value in observed]
    distinct = len(set(observed))
    missing = total - len(observed)
    warnings = []
    if not observed:
        kind, reason = "text", "No non-missing values; type cannot be inferred."
    elif any(LEADING_ZERO.fullmatch(value) for value in trimmed):
        kind = "category" if distinct <= 20 else "text"
        reason = "Leading-zero identifiers are preserved as labels, not numbers."
    elif all(is_number(value) for value in trimmed):
        kind, reason = "number", "Every non-missing value is a finite decimal number."
    elif all(is_date(value) for value in trimmed):
        kind, reason = "date", "Every non-missing value is an ISO date or timestamp. Original strings and time zones are preserved."
    elif any(is_number(value) for value in trimmed):
        kind, reason = "text", "Mixed numeric and nonnumeric values; no values were coerced."
        warnings.append(reason)
    elif any(DATE_LIKE.match(value) for value in trimmed):
        kind, reason = "text", "Date-like values are inconsistent or invalid; kept as text."
        warnings.append(reason)
    elif max(map(len, observed)) <= 80 and not any("\n" in value or "\r" in value for value in observed) and (
        distinct <= 20 or (distinct <= 100 and distinct / len(observed) <= 0.2)
    ):
        kind, reason = "category", "Short text with low cardinality."
    else:
        kind, reason = "text", "Free-form or high-cardinality text."
    return {
        "key": f"c{index}", "name": name, "type": kind,
        "missing_count": missing, "non_missing_count": len(observed),
        "distinct_count": distinct, "reason": reason, "warnings": warnings,
        "examples": [value[:100] for value in list(dict.fromkeys(observed))[:3]],
    }


def parse_csv(data: bytes, delimiter: str = ",") -> tuple[dict, list[dict], list[dict]]:
    if len(data) > MAX_BYTES:
        raise CsvRejected("CSV exceeds the 5 MiB limit. No dataset was saved.", 413)
    if delimiter not in {",", ";", "\t"}:
        raise CsvRejected("Choose comma, semicolon, or tab as the delimiter.")
    if not data:
        raise CsvRejected("The CSV is empty. A header row is required.")
    if b"\x00" in data:
        raise CsvRejected("NUL bytes are not accepted. Export a UTF-8 text CSV.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvRejected(f"Invalid UTF-8 near byte {exc.start}. Export as UTF-8 CSV; no bytes were replaced.") from None
    if text.count("\n") + text.count("\r") > MAX_PHYSICAL_LINES * 2:
        raise CsvRejected("Too many source lines. No partial dataset was saved.", 413)
    lines = io.StringIO(text, newline="").readlines()
    if len(lines) > MAX_PHYSICAL_LINES:
        raise CsvRejected("CSV exceeds 100,000 physical lines. No partial dataset was saved.", 413)
    reader = csv.reader(iter(lines), delimiter=delimiter, strict=True)
    try:
        header = next(reader)
    except StopIteration:
        raise CsvRejected("The CSV has no header.") from None
    except csv.Error as exc:
        raise CsvRejected(f"Header cannot be parsed: {exc}") from None
    if not header or len(header) > MAX_COLUMNS:
        raise CsvRejected("Header must contain 1–100 columns.")
    names = [name.strip() for name in header]
    if any(not name for name in names):
        raise CsvRejected("Blank column names are not accepted. Name every column.")
    if len(set(names)) != len(names):
        raise CsvRejected("Duplicate column names are not accepted (including whitespace-only differences).")
    # Display names and cell strings are preserved exactly as supplied.
    rows, errors = [], []
    physical_end = reader.line_num
    header_end = physical_end
    record_number = 0
    unknown_tail = False
    while True:
        start = physical_end + 1
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            raw = "".join(lines[start - 1:])
            errors.append({
                "record_number": None, "line_start": start, "line_end": len(lines),
                "code": "unparsed_range",
                "reason": f"CSV syntax error: {exc}. Parsing stopped because subsequent record boundaries cannot be trusted; this entire remaining line range is unparsed.",
                "raw_excerpt": raw[:500], "excerpt_truncated": len(raw) > 500,
            })
            unknown_tail = True
            break
        physical_end = reader.line_num
        record_number += 1
        if record_number > MAX_RECORDS:
            raise CsvRejected("CSV exceeds 50,000 records. No partial dataset was saved.", 413)
        if len(cells) != len(header):
            raw = "".join(lines[start - 1:physical_end])
            errors.append({
                "record_number": record_number, "line_start": start, "line_end": physical_end,
                "code": "column_count",
                "reason": f"Expected {len(header)} fields, found {len(cells)}." + (" Blank records are counted as unreadable." if not cells else ""),
                "raw_excerpt": raw[:500], "excerpt_truncated": len(raw) > 500,
            })
        else:
            rows.append({"record_number": record_number, "line_start": start, "line_end": physical_end, "cells": cells})
    rejected = sum(error["code"] == "column_count" for error in errors)
    profile = {
        "parser_version": PARSER_VERSION, "sha256": hashlib.sha256(data).hexdigest(),
        "encoding": "UTF-8", "delimiter": delimiter,
        "physical_lines": len(lines), "header_line_end": header_end,
        "total_records": None if unknown_tail else record_number,
        "known_records": record_number,
        "readable_rows": len(rows), "unreadable_rows": rejected,
        "unparsed_lines": sum(error["line_end"] - error["line_start"] + 1 for error in errors if error["code"] == "unparsed_range"),
        "error_count": len(errors), "analysis_ready": not errors,
        "missing_policy": "Empty or whitespace-only cells. NA, N/A, null, and similar labels remain values.",
        "inference_scope": "All readable records; never a sample. Original cells are preserved.",
        "columns": [column_profile(i, name, [row["cells"][i] for row in rows], len(rows)) for i, name in enumerate(header)],
    }
    return profile, rows, errors
