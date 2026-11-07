"""记账业务模块（成员02）：新增与删除账单。

对应项目 README 的 §3.2（新增记录）、§3.3（删除记录）、§3.7（模块边界）。

本模块职责：

- 校验新增请求的五个可提交字段：日期、收支类型、金额、类别、备注；
- 先校验、再生成 id、保存成功后才允许响应 201；
- 删除指定 id 的账单，删除不存在或 id 不匹配的记录返回 404 且不修改文件；
- 以 Blueprint 暴露 ``POST /api/records`` 与 ``DELETE /api/records/<record_id>``。

分工边界：本模块不碰文件和 JSON，全部通过 :mod:`storage` 完成；
也不自己拼装错误响应，失败一律抛 :class:`errors.AppError`，
由入口注册的公共处理器统一序列化（§3.6）。

函数可直接在无 Flask 请求上下文的场景调用（如测试、脚本、3/4 号复用），
只有路由函数才依赖 ``request``。
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from errors import (
    AppError,
    invalid_json,
    record_not_found,
    unsupported_media_type,
    validation_error,
)
from storage import (
    MAX_AMOUNT,
    MAX_CATEGORY_LENGTH,
    MAX_NOTE_LENGTH,
    MIN_AMOUNT,
    is_valid_amount,
    is_valid_category,
    is_valid_date,
    is_valid_note,
    is_valid_record_type,
    load_records,
    new_record_id,
    records_lock,
    save_records,
)

records_bp = Blueprint("records", __name__)

# 客户端可提交的字段；id 由服务端生成，因此不在其中（§3.1）。
ACCEPTED_FIELDS = ("date", "type", "amount", "category", "note")
REQUIRED_FIELDS = ("date", "type", "amount", "category")


# ---------------------------------------------------------------------------
# 校验（业务层唯一入口，后端为最终校验依据）
# ---------------------------------------------------------------------------


def validate_payload(payload: dict) -> dict:
    """校验新增账单请求，返回可直接保存的字段字典（不含 id）。

    校验顺序固定为 date → type → amount → category → note，
    保证同一份非法请求每次都稳定返回同一个字段错误，便于前端定位。

    通过校验时类别与备注已去首尾空白；备注省略时默认为空字符串。
    """
    if not isinstance(payload, dict):
        raise invalid_json("请求体必须是 JSON 对象")

    if "id" in payload:
        raise validation_error("记录 id 由服务端生成，请求中不得传入", "id")

    unknown_fields = [key for key in payload if key not in ACCEPTED_FIELDS]
    if unknown_fields:
        raise validation_error(f"不支持的字段：{unknown_fields[0]}", unknown_fields[0])

    missing_fields = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing_fields:
        raise validation_error(f"缺少必填字段：{missing_fields[0]}", missing_fields[0])

    # 契约：任何字段均不接受 null；note 允许整个省略，但不允许显式传 null。
    for field in ACCEPTED_FIELDS:
        if field in payload and payload[field] is None:
            raise validation_error(f"字段 {field} 不接受 null", field)

    date_value = payload["date"]
    if not is_valid_date(date_value):
        raise validation_error(
            "日期必须是真实存在的 YYYY-MM-DD 格式（10 个字符）", "date"
        )

    type_value = payload["type"]
    if not is_valid_record_type(type_value):
        raise validation_error("收支类型只能是 income 或 expense", "type")

    amount_value = payload["amount"]
    if not is_valid_amount(amount_value):
        raise validation_error(
            f"金额必须为{MIN_AMOUNT}—{MAX_AMOUNT}之间的整数分", "amount"
        )

    category_value = payload["category"]
    if not isinstance(category_value, str):
        raise validation_error("类别必须是文本", "category")
    category_value = category_value.strip()
    if not is_valid_category(category_value):
        raise validation_error(
            f"类别去掉首尾空白后必须是1—{MAX_CATEGORY_LENGTH}个字符", "category"
        )

    note_value = payload.get("note", "")
    if not isinstance(note_value, str):
        raise validation_error("备注必须是文本", "note")
    note_value = note_value.strip()
    if not is_valid_note(note_value):
        raise validation_error(
            f"备注去掉首尾空白后最多{MAX_NOTE_LENGTH}个字符", "note"
        )

    return {
        "date": date_value,
        "type": type_value,
        "amount": amount_value,
        "category": category_value,
        "note": note_value,
    }


def _clean_record_id(record_id) -> str:
    """规范化路径中的记录 id；空白或非文本同样按「不存在」处理（§3.3）。"""
    if isinstance(record_id, str):
        cleaned = record_id.strip()
        if cleaned:
            return cleaned
    raise AppError(404, "RECORD_NOT_FOUND", "账单记录不存在")


# ---------------------------------------------------------------------------
# 业务函数（供路由、测试与其它模块复用）
# ---------------------------------------------------------------------------


def create_record(payload: dict) -> dict:
    """新增一笔收入或支出，返回已保存的完整记录。

    流程严格按契约：先校验 → 再生成 id → 加锁读改写 → 保存成功后才返回。
    相同内容允许记为多笔，因此不做去重。
    """
    fields = validate_payload(payload)
    record = {"id": new_record_id(), **fields}

    # records_lock 覆盖整个「读取 → 追加 → 保存」，避免并发新增互相覆盖（§3.8）。
    with records_lock:
        records = load_records()
        records.append(record)
        save_records(records)

    return record


def delete_record(record_id: str) -> dict:
    """删除指定 id 的账单，返回 ``{"id": ..., "deleted": True}``。

    记录不存在（含重复删除、id 格式不匹配）抛 404，且不修改文件；
    只有保存成功才返回成功（§3.3）。
    """
    target_id = _clean_record_id(record_id)

    with records_lock:
        records = load_records()
        remaining = [record for record in records if record["id"] != target_id]
        if len(remaining) == len(records):
            raise record_not_found(target_id)
        save_records(remaining)

    return {"id": target_id, "deleted": True}


# ---------------------------------------------------------------------------
# 路由：只负责解析 HTTP 与包装响应，业务异常交给公共处理器
# ---------------------------------------------------------------------------


@records_bp.post("/api/records")
def create_record_route():
    """POST /api/records：成功返回 201，``data`` 为完整记录。"""
    if not request.is_json:
        raise unsupported_media_type()

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        # 覆盖两种 400：JSON 语法错误，以及请求体是合法 JSON 但不是对象。
        raise invalid_json()

    return jsonify({"data": create_record(payload)}), 201


@records_bp.delete("/api/records/<record_id>")
def delete_record_route(record_id: str):
    """DELETE /api/records/<id>：成功返回 200，``data`` 为 id/deleted。"""
    return jsonify({"data": delete_record(record_id)})
