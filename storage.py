"""JSON persistence for one local service process; amounts are integer cents."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from datetime import date
from uuid import UUID, uuid4

from errors import AppError


DATA_FILE = Path(__file__).resolve().parent / "data" / "records.json"
records_lock = RLock()
FIELDS = {"id", "date", "type", "amount", "category", "note"}
MAX_AMOUNT = 999999999


def new_record_id() -> str:
    return str(uuid4())


def _storage_error() -> AppError:
    return AppError(500, "STORAGE_ERROR", "账单数据读写失败或格式损坏，原文件已保留")


def _validate_records(records: list[dict]) -> None:
    if not isinstance(records, list):
        raise ValueError("Expected a record array")
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != FIELDS:
            raise ValueError("Invalid record fields")
        record_id = record["id"]
        if not isinstance(record_id, str):
            raise ValueError("Invalid ID")
        parsed_id = UUID(record_id)
        if parsed_id.version != 4 or str(parsed_id) != record_id or record_id in seen:
            raise ValueError("Invalid or duplicate UUID4")
        seen.add(record_id)
        day = record["date"]
        if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
            raise ValueError("Invalid date format")
        date.fromisoformat(day)
        if record["type"] not in ("income", "expense"):
            raise ValueError("Invalid record type")
        if type(record["amount"]) is not int or not 1 <= record["amount"] <= MAX_AMOUNT:
            raise ValueError("Invalid integer cents")
        for key, minimum, maximum in (("category", 1, 20), ("note", 0, 200)):
            value = record[key]
            if (not isinstance(value, str) or value != value.strip()
                    or not minimum <= len(value) <= maximum):
                raise ValueError("Invalid text field")


def _read_existing() -> list[dict]:
    with DATA_FILE.open("r", encoding="utf-8") as stream:
        records = json.load(stream)
    _validate_records(records)
    return records


def load_records() -> list[dict]:
    """Initialize only missing files; never silently reset damaged data."""
    with records_lock:
        try:
            if not DATA_FILE.exists():
                save_records([])
            return _read_existing()
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            raise _storage_error() from exc


def save_records(records: list[dict]) -> None:
    """Callers doing read/modify/write must hold records_lock throughout."""
    with records_lock:
        temporary_path = None
        try:
            _validate_records(records)
            # Refuse to replace an existing corrupt file even on a direct save.
            if DATA_FILE.exists():
                _read_existing()
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=DATA_FILE.parent,
                prefix="records-", suffix=".tmp", delete=False
            ) as stream:
                temporary_path = Path(stream.name)
                json.dump(records, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, DATA_FILE)
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            raise _storage_error() from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
