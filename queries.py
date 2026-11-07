"""3号：查询参数校验、可复用筛选和 GET /api/records。

金额单位为分；日期、金额区间均包含端点。
依赖1号提供的 errors.AppError 与 storage.load_records。
"""

import re
from datetime import date

from flask import Blueprint, jsonify, request

from errors import AppError
from storage import load_records


queries_bp = Blueprint("queries", __name__)
FILTER_KEYS = (
    "start_date", "end_date", "type", "category", "min_amount", "max_amount"
)
MAX_AMOUNT = 999999999


def _invalid(field: str, message: str) -> None:
    raise AppError(400, "VALIDATION_ERROR", message, field=field)


def _parse_date(value: str, field: str) -> str:
    """验证标准日期字符串，保留可直接比较先后顺序的 YYYY-MM-DD 格式。"""
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        _invalid(field, "日期必须为YYYY-MM-DD格式的真实日期")
    try:
        date.fromisoformat(value)
    except ValueError:
        _invalid(field, "日期必须为YYYY-MM-DD格式的真实日期")
    return value


def _parse_integer(value: str, field: str, lower: int, upper: int) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        _invalid(field, f"{field}必须为{lower}—{upper}之间的整数字符串")
    # 去掉前导零后再比较长度，避免超长整数触发Python的转换限制。
    digits = value.lstrip("0") or "0"
    if len(digits) > len(str(upper)):
        _invalid(field, f"{field}必须在{lower}—{upper}之间")
    number = int(digits)
    if not lower <= number <= upper:
        _invalid(field, f"{field}必须在{lower}—{upper}之间")
    return number


def parse_query(args, *, allow_limit: bool) -> tuple[dict, int | str | None]:
    """解析Flask request.args；列表允许limit，统计拒绝limit。

    返回六键筛选字典和独立的limit；不在这里读取存储。
    普通字典也可用于本地调用，HTTP重复参数通过getlist检测。
    """
    allowed = set(FILTER_KEYS)
    if allow_limit:
        allowed.add("limit")
    values = {}
    for key in args:
        if key not in allowed:
            _invalid(key, f"不支持的查询参数：{key}")
        # HTTP查询同名参数可能重复，必须检查原始列表而非直接取首值。
        items = args.getlist(key) if hasattr(args, "getlist") else [args[key]]
        if len(items) != 1:
            _invalid(key, f"查询参数{key}不能重复")
        if not isinstance(items[0], str):
            _invalid(key, f"查询参数{key}必须为字符串")
        values[key] = items[0].strip() or None

    # 固定六键结构；缺失条件统一为 None，便于查询和统计复用。
    filters = {key: values.get(key) for key in FILTER_KEYS}
    for key in ("start_date", "end_date"):
        if filters[key] is not None:
            filters[key] = _parse_date(filters[key], key)

    if filters["type"] is not None and filters["type"] not in ("income", "expense"):
        _invalid("type", "收支类型只能为income或expense")
    if filters["category"] is not None and len(filters["category"]) > 20:
        _invalid("category", "类别去除首尾空白后最多20个字符")

    for key in ("min_amount", "max_amount"):
        if filters[key] is not None:
            filters[key] = _parse_integer(filters[key], key, 0, MAX_AMOUNT)

    if (filters["start_date"] is not None and filters["end_date"] is not None
            and filters["start_date"] > filters["end_date"]):
        _invalid("end_date", "结束日期不能早于开始日期")
    if (filters["min_amount"] is not None and filters["max_amount"] is not None
            and filters["min_amount"] > filters["max_amount"]):
        _invalid("max_amount", "最大金额不能小于最小金额")

    limit = None
    if allow_limit:
        raw_limit = values.get("limit")
        if raw_limit is None:
            limit = 10
        elif raw_limit == "all":
            limit = "all"
        else:
            limit = _parse_integer(raw_limit, "limit", 1, 100)
    return filters, limit


def filter_records(records: list[dict], filters: dict) -> list[dict]:
    """按已校验的六项条件取交集，不排序、不截断、不修改输入。

    4号统计模块直接复用此函数，确保统计涵盖全部匹配记录。
    返回新的列表；记录字典只读复用。
    """
    start = filters.get("start_date")
    end = filters.get("end_date")
    kind = filters.get("type")
    category = filters.get("category")
    minimum = filters.get("min_amount")
    maximum = filters.get("max_amount")

    def matches(record):
        return (
            (start is None or record["date"] >= start)
            and (end is None or record["date"] <= end)
            and (kind is None or record["type"] == kind)
            and (category is None or record["category"] == category)
            and (minimum is None or record["amount"] >= minimum)
            and (maximum is None or record["amount"] <= maximum)
        )

    return [record for record in records if matches(record)]


def query_records(filters: dict, limit: int | str = 10) -> dict:
    """读取一次快照，先筛选，再按日期/插入位置倒序，最后截取。"""
    if limit != "all" and (type(limit) is not int or not 1 <= limit <= 100):
        _invalid("limit", "limit必须为1—100的整数或all")
    records = load_records()
    matched = filter_records(records, filters)
    # enumerate中的相对顺序保留了原存储顺序；同日后追加记录优先。
    ordered = [record for _, record in sorted(
        enumerate(matched), key=lambda item: (item[1]["date"], item[0]), reverse=True
    )]
    selected = ordered if limit == "all" else ordered[:limit]
    return {
        "data": selected,
        # total 是截取前的匹配数，returned 才是本次响应中的记录数。
        "meta": {"total": len(ordered), "returned": len(selected), "limit": limit},
    }


@queries_bp.get("/api/records")
def list_records():
    filters, limit = parse_query(request.args, allow_limit=True)
    return jsonify(query_records(filters, limit))
