"""账单数据存储层：本地 JSON 文件读写（项目 README §3.7、§3.8）。

设计参考 CoinTrack 的 ``helpers.py``：把「数据怎么落盘」从业务路由里抽出来，
业务模块 / 路由只调本模块的函数，不直接碰文件系统和 JSON。
CoinTrack 原实现在该层有三处隐患，这里逐条修正：

===================  ==================================  ==========================
CoinTrack helpers.py  问题                                 本模块的做法
===================  ==================================  ==========================
读失败 ``print`` 后   异常被吞成 ``False``，调用方拿到      统一抛 AppError(500,
返回 ``False``        假值继续跑，故障被静默掩盖             STORAGE_ERROR)，前端有明确提示
事务式写缺失          ``INSERT`` 直接落盘，中途失败留下       先写同目录临时文件再
                      半份数据                               ``os.replace`` 原子替换
数据校验缺失          任何脏数据都能写进库                   读、写两侧都校验六字段，
                                                             非法数据不落盘、不覆盖
===================  ==================================  ==========================

对外接口（§3.7 签名的子集，全部可被 2—4 号复用）：

- :func:`new_record_id` 生成 UUID4 字符串
- :func:`load_records` 读取并校验完整记录数组，每次返回独立对象
- :func:`save_records` 校验后保存，失败抛 STORAGE_ERROR 且保留旧文件
- :data:`records_lock` 进程内共享 RLock，读、写都使用（可重入）
- :func:`is_valid_*` 一组纯函数校验器，供业务层拼装面向用户的错误信息

并发边界：只保证单服务进程内安全。RLock 不跨进程，
第一版按 §3.8 只在本地单进程运行。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path

from errors import storage_error

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径：由代码文件位置解析绝对路径，不依赖启动时的工作目录（§3.8）
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "records.json"

# ---------------------------------------------------------------------------
# 数据模型常量（§3.1）：金额全部为整数分
# ---------------------------------------------------------------------------

RECORD_FIELDS = ("id", "date", "type", "amount", "category", "note")
RECORD_TYPES = ("income", "expense")
DATE_LENGTH = 10
MIN_AMOUNT = 1
MAX_AMOUNT = 999_999_999
MAX_CATEGORY_LENGTH = 20
MAX_NOTE_LENGTH = 200
MAX_RECORD_ID_LENGTH = 64

# 读、写共用同一把可重入锁：业务层可以在锁内完成「读取 → 修改 → 保存」，
# 内层 load_records / save_records 再次取锁不会自锁（RLock 语义）。
records_lock = threading.RLock()


# ---------------------------------------------------------------------------
# 纯函数校验器：不抛异常、不读文件，业务层据此拼装面向用户的提示
# ---------------------------------------------------------------------------


def is_valid_record_id(value) -> bool:
    """存储记录的 id：非空文本、无首尾空白、长度受控。

    生产数据由 :func:`new_record_id` 生成（UUID4，36 字符）；
    允许 ``demo-1`` 这类长度受控的文本，便于演示数据与 4 号自测数据复用。
    """
    return (
        isinstance(value, str)
        and value == value.strip()
        and 0 < len(value) <= MAX_RECORD_ID_LENGTH
    )


def is_valid_date(value) -> bool:
    """严格 ``YYYY-MM-DD``：10 个字符，且是真实存在的日期。"""
    if not isinstance(value, str) or len(value) != DATE_LENGTH:
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    # 反向格式化，排除 "2026-1-1"、"2026-02-30" 这类非法或补零不规范的值。
    return parsed.strftime("%Y-%m-%d") == value


def is_valid_record_type(value) -> bool:
    """收支类型只能是 ``income`` 或 ``expense``（区分大小写）。"""
    return isinstance(value, str) and value in RECORD_TYPES


def is_valid_amount(value) -> bool:
    """金额为 1—999999999 的整数分；排查 bool/float/str 与负数。

    ``bool`` 是 ``int`` 的子类，必须单独排除，否则 ``True`` 会被当成 1 分。
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return MIN_AMOUNT <= value <= MAX_AMOUNT


def is_valid_category(value) -> bool:
    """类别为已去首尾空白、1—20 个 Unicode 码点的文本。"""
    return (
        isinstance(value, str)
        and value == value.strip()
        and 1 <= len(value) <= MAX_CATEGORY_LENGTH
    )


def is_valid_note(value) -> bool:
    """备注为已去首尾空白、最多 200 个 Unicode 码点的文本（可为空串）。"""
    return (
        isinstance(value, str)
        and value == value.strip()
        and len(value) <= MAX_NOTE_LENGTH
    )


# ---------------------------------------------------------------------------
# 记录的整表校验：读、写两侧共用，脏数据既不落盘也不被静默忽略
# ---------------------------------------------------------------------------


def validate_stored_record(record, position: int) -> dict:
    """校验一条已存储记录，返回独立的六字段字典副本。

    ``position`` 为面向用户的 1 起序号，便于在错误提示里定位问题记录。
    与业务层的请求校验不同：这里要求字段既完整又已归一化
    （类别、备注无首尾空白），因为文件只应由 :func:`save_records` 写入。
    """
    if not isinstance(record, dict):
        raise storage_error(f"账单数据第 {position} 项不是 JSON 对象")

    missing = [field for field in RECORD_FIELDS if field not in record]
    if missing:
        raise storage_error(f"账单数据第 {position} 项缺少字段：{missing[0]}")

    unknown = [field for field in record if field not in RECORD_FIELDS]
    if unknown:
        raise storage_error(f"账单数据第 {position} 项含有未知字段：{unknown[0]}")

    if not is_valid_record_id(record["id"]):
        raise storage_error(f"账单数据第 {position} 项的 id 不合法")
    if not is_valid_date(record["date"]):
        raise storage_error(f"账单数据第 {position} 项的日期不是合法的 YYYY-MM-DD")
    if not is_valid_record_type(record["type"]):
        raise storage_error(f"账单数据第 {position} 项的收支类型不合法")
    if not is_valid_amount(record["amount"]):
        raise storage_error(f"账单数据第 {position} 项的金额不是合法的整数分")
    if not is_valid_category(record["category"]):
        raise storage_error(
            f"账单数据第 {position} 项的类别必须是1—{MAX_CATEGORY_LENGTH}个字符且已去首尾空白"
        )
    if not is_valid_note(record["note"]):
        raise storage_error(
            f"账单数据第 {position} 项的备注最多{MAX_NOTE_LENGTH}个字符且已去首尾空白"
        )

    # 逐字段取值重建：既固定键序，又保证与源对象完全独立（§3.7「每次返回独立对象」）。
    return {field: record[field] for field in RECORD_FIELDS}


def _assert_unique_ids(records: list[dict]) -> None:
    """重复 id 视为文件损坏，直接报错而不是取其一。"""
    seen: set[str] = set()
    for record in records:
        record_id = record["id"]
        if record_id in seen:
            raise storage_error(f"账单数据存在重复 id：{record_id}")
        seen.add(record_id)


# ---------------------------------------------------------------------------
# 文件读写
# ---------------------------------------------------------------------------


def new_record_id() -> str:
    """生成全局唯一 UUID4 字符串，供 2 号新增记录使用（§3.7）。"""
    return str(uuid.uuid4())


def _read_text(path: Path) -> str:
    """读取 UTF-8 文本；``utf-8-sig`` 兼容 Windows 编辑器写入的 BOM。"""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        logger.warning("账单数据文件不是 UTF-8 编码：%s", exc)
        raise storage_error("账单数据文件不是 UTF-8 编码，可能已损坏") from exc
    except OSError as exc:
        logger.warning("账单数据文件读取失败：%s", exc)
        raise storage_error("账单数据文件读取失败，请检查文件是否存在且可读") from exc


def _remove_quietly(path: Path) -> None:
    """清理临时文件；清理失败不影响给用户的主错误。"""
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - 仅极端权限场景
        logger.warning("临时文件清理失败：%s", path)


def _write_atomically(target: Path, text: str) -> None:
    """先写同目录临时文件再原子替换，保存失败保留旧文件（§3.8）。"""
    temp_path = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except OSError as exc:
        logger.warning("账单数据写入失败：%s", exc)
        _remove_quietly(temp_path)
        raise storage_error("账单数据保存失败，旧文件已保留") from exc


def _initialize_file(path: Path) -> None:
    """首次启动把不存在的文件初始化为 ``[]``（§3.8）。

    使用独占创建（``x`` 模式）：若刚好有别的进程建好了文件就放弃写入，
    交由调用方读取真实内容，不会静默覆盖。
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "x", encoding="utf-8", newline="\n") as handle:
            handle.write("[]\n")
    except FileExistsError:
        return
    except OSError as exc:
        logger.warning("账单数据文件初始化失败：%s", exc)
        raise storage_error("账单数据文件初始化失败，请检查数据目录权限") from exc


def load_records() -> list[dict]:
    """读取并校验完整记录数组，返回按插入顺序排列的独立对象列表。

    文件不存在时初始化为 ``[]``；已有空文件、损坏 JSON、非数组内容、
    重复 id 或非法记录一律抛 STORAGE_ERROR，**保留原文件不修改**。
    """
    with records_lock:
        path = Path(DATA_FILE)
        if not path.exists():
            _initialize_file(path)

        text = _read_text(path)
        # 注意：新初始化的文件内容是 "[]"，与「已有空文件」区分开。
        # 已有但 0 字节的文件属于损坏，必须报错而不是当成空账本（§3.8）。
        if not text.strip():
            raise storage_error("账单数据文件为空，可能已损坏；请修复或删除该文件后重试")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("账单数据文件不是合法 JSON：%s", exc)
            raise storage_error("账单数据文件不是合法 JSON，可能已损坏") from exc

        if not isinstance(payload, list):
            raise storage_error("账单数据文件的顶层结构必须是数组")

        records = [
            validate_stored_record(item, index + 1)
            for index, item in enumerate(payload)
        ]
        _assert_unique_ids(records)
        return records


def save_records(records: list[dict]) -> None:
    """校验后保存全部记录；校验或写盘失败抛 STORAGE_ERROR 并保留旧文件。

    先整体校验再动文件：任何一条不合法都不会产生半份新数据。
    """
    with records_lock:
        if not isinstance(records, list):
            raise storage_error("账单数据保存失败：记录集合必须是数组")

        validated = [
            validate_stored_record(record, index + 1)
            for index, record in enumerate(records)
        ]
        _assert_unique_ids(validated)
        text = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"
        _write_atomically(Path(DATA_FILE), text)
