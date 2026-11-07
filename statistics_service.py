"""账单统计模块：所有金额均使用整数分。"""

from collections import defaultdict


def calculate_stats(records):
    """
    统计传入的全部账单。

    records 应为已经过查询模块筛选的记录。
    本函数不截取最近10条，避免统计结果遗漏数据。
    """
    income = 0
    expense = 0

    category_totals = defaultdict(
        lambda: {"income": 0, "expense": 0}
    )
    month_totals = defaultdict(
        lambda: {"income": 0, "expense": 0}
    )

    for record in records:
        record_type = record["type"]
        amount = record["amount"]
        category = record["category"]
        month = record["date"][:7]

        if record_type not in ("income", "expense"):
            raise ValueError("账单类型必须是 income 或 expense")

        # bool 在 Python 中属于 int 的子类，需要单独排除。
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError("账单金额必须是整数分")

        if amount <= 0:
            raise ValueError("账单金额必须大于零")

        if record_type == "income":
            income += amount
        else:
            expense += amount

        category_totals[category][record_type] += amount
        month_totals[month][record_type] += amount

    by_category = [
        {
            "category": category,
            "income": totals["income"],
            "expense": totals["expense"],
        }
        for category, totals in sorted(category_totals.items())
    ]

    by_month = [
        {
            "month": month,
            "income": totals["income"],
            "expense": totals["expense"],
        }
        for month, totals in sorted(month_totals.items())
    ]

    return {
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "by_category": by_category,
        "by_month": by_month,
    }


def run_self_test():
    """使用虚构账单验证统计结果。"""
    import json

    records = [
        {
            "id": "demo-1",
            "date": "2026-11-07",
            "type": "income",
            "amount": 10000,
            "category": "生活费",
            "note": "演示收入",
        },
        {
            "id": "demo-2",
            "date": "2026-11-07",
            "type": "expense",
            "amount": 1250,
            "category": "饮食",
            "note": "演示午餐",
        },
        {
            "id": "demo-3",
            "date": "2026-10-31",
            "type": "expense",
            "amount": 500,
            "category": "饮食",
            "note": "演示早餐",
        },
    ]

    # 验证 README 中的例子：100元 - 12.50元 = 87.50元。
    basic = calculate_stats(records[:2])
    assert basic["income"] == 10000
    assert basic["expense"] == 1250
    assert basic["balance"] == 8750

    # 验证跨月份和相同类别的累加。
    result = calculate_stats(records)
    assert result["income"] == 10000
    assert result["expense"] == 1750
    assert result["balance"] == 8250

    categories = {
        item["category"]: item
        for item in result["by_category"]
    }
    assert categories["饮食"]["expense"] == 1750

    assert result["by_month"] == [
        {"month": "2026-10", "income": 0, "expense": 500},
        {"month": "2026-11", "income": 10000, "expense": 1250},
    ]

    # 验证空数据。
    assert calculate_stats([]) == {
        "income": 0,
        "expense": 0,
        "balance": 0,
        "by_category": [],
        "by_month": [],
    }

    # 验证统计不会被默认列表的10条限制。
    assert calculate_stats([records[0]] * 11)["income"] == 110000

    print("全部自测通过")
    print("示例：收入100.00元，支出12.50元，结余87.50元")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_self_test()