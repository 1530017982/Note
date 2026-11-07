"""单进程本地 JSON 存储：校验账单、保护并发读写并原子保存，金额单位为分。"""

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


# 使用代码所在目录定位账单，不受终端启动目录影响。
DATA_FILE = Path(__file__).resolve().parent / "data" / "records.json"
# 业务层与读写函数会嵌套获取同一把锁，因此必须可重入。
records_lock = RLock()
FIELDS = {"id", "date", "type", "amount", "category", "note"}
MAX_AMOUNT = 999999999


def new_record_id() -> str:
    """新增账单由服务端生成 UUID4，不使用客户端传入的编号。"""
    return str(uuid4())


def _storage_error() -> AppError:
    """屏蔽底层文件路径和异常细节，交由入口统一返回存储错误。"""
    return AppError(500, "STORAGE_ERROR", "账单数据读写失败或格式损坏，原文件已保留")


def _validate_records(records: list[dict]) -> None:
    """读写共用的整表校验：字段完整、ID唯一、金额及文本符合约定。"""
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
        # 同时检查 UUID 版本、标准表示和整表内的重复编号。
        if parsed_id.version != 4 or str(parsed_id) != record_id or record_id in seen:
            raise ValueError("Invalid or duplicate UUID4")
        seen.add(record_id)
        day = record["date"]
        if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
            raise ValueError("Invalid date format")
        date.fromisoformat(day)  # 格式正确还不够，日期必须真实存在。
        if record["type"] not in ("income", "expense"):
            raise ValueError("Invalid record type")
        # 严格 int 检查同时排除 bool，避免 True 被当作1分。
        if type(record["amount"]) is not int or not 1 <= record["amount"] <= MAX_AMOUNT:
            raise ValueError("Invalid integer cents")
        for key, minimum, maximum in (("category", 1, 20), ("note", 0, 200)):
            value = record[key]
            if (not isinstance(value, str) or value != value.strip()
                    or not minimum <= len(value) <= maximum):
                raise ValueError("Invalid text field")


def _read_existing() -> list[dict]:
    """每次从文件重新解析并校验，返回的对象与之前读取的结果相互独立。"""
    with DATA_FILE.open("r", encoding="utf-8") as stream:
        records = json.load(stream)
    _validate_records(records)
    return records


def load_records() -> list[dict]:
    """文件不存在才初始化；已有空文件或损坏数据报错并保留原内容。"""
    with records_lock:
        try:
            if not DATA_FILE.exists():
                save_records([])
            return _read_existing()
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            raise _storage_error() from exc


def save_records(records: list[dict]) -> None:
    """校验后保存；调用方须用 records_lock 包住完整的读取、修改、保存过程。"""
    with records_lock:
        temporary_path = None
        try:
            _validate_records(records)
            # 即使直接调用保存，也不能覆盖已损坏的原文件。
            if DATA_FILE.exists():
                _read_existing()
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            # 临时文件与正式文件位于同一目录，写完整后再替换。
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=DATA_FILE.parent,
                prefix="records-", suffix=".tmp", delete=False
            ) as stream:
                temporary_path = Path(stream.name)
                json.dump(records, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
                # 先刷新语言缓冲区，再请求操作系统同步文件数据。
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, DATA_FILE)
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            raise _storage_error() from exc
        finally:
            # 保存失败时清理残留文件；成功替换后该临时路径已经不存在。
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
