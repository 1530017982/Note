"""对接测试：驱动 3 号 ``queries.py`` 与 4 号 ``statistics_service.py``。

目的不是重复测别人的逻辑，而是证明：**成员02 新增/删除后的数据，
能被 3 号筛选、4 号统计原样消费并算对**（§3.10 联调样例），
且三个 Blueprint 能挂在同一应用上协同工作。

模块查找顺序（本文件位于 ``tests/``）：

1. 仓库根目录 ``../statistics_service.py`` —— 正式项目布局（3 号/4 号已合入）；
2. ``../.reference/Note-main/statistics_service.py`` —— 本地参考目录。

3 号 ``queries.py`` 优先用真实实现；未交付时注入最小替身，
保证 2 号模块与数据层始终可以独立验证。
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import storage
from records import create_record, delete_record
from tests.support import DataFileTestCase

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

STATS_CANDIDATES = (
    REPO_ROOT / "statistics_service.py",
    WORKSPACE_ROOT / ".reference" / "Note-main" / "statistics_service.py",
)

NULL_FILTERS = dict.fromkeys(
    ("start_date", "end_date", "type", "category", "min_amount", "max_amount")
)

INCOME_PAYLOAD = {
    "date": "2026-11-07",
    "type": "income",
    "amount": 10000,
    "category": "工资",
    "note": "",
}
EXPENSE_PAYLOAD = {
    "date": "2026-11-07",
    "type": "expense",
    "amount": 1250,
    "category": "饮食",
    "note": "午餐",
}

try:  # 3 号已交付时直接使用真实实现
    import queries  # noqa: F401

    HAS_REAL_QUERIES = True
except ImportError:  # pragma: no cover - 仅 3 号未交付时走到
    HAS_REAL_QUERIES = False


def fake_filter_records(records: list[dict], filters: dict) -> list[dict]:
    """3号 ``queries.filter_records`` 的最小替身：只做类型与类别精确匹配。"""
    matched = []
    for record in records:
        if filters.get("type") and record["type"] != filters["type"]:
            continue
        if filters.get("category") and record["category"] != filters["category"]:
            continue
        matched.append(record)
    return matched


def ensure_queries_module():
    """3 号未交付时注入替身；返回需要回收的 patcher 或 None。"""
    if HAS_REAL_QUERIES:
        return None
    stub = types.ModuleType("queries")
    stub.filter_records = fake_filter_records
    patcher = patch.dict(sys.modules, {"queries": stub})
    patcher.start()
    return patcher


def find_statistics_source() -> Path | None:
    for candidate in STATS_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def load_statistics_module():
    """按文件路径载入 4 号模块，避免依赖它是否在 sys.path 上。

    载入期间关闭字节码缓存：参考目录是只读资料，
    不能在 ``.reference/Note-main/`` 里留下 ``__pycache__``。
    """
    source = find_statistics_source()
    if source is None:  # pragma: no cover - 4 号缺失时跳过
        raise unittest.SkipTest("未找到 statistics_service.py")

    spec = importlib.util.spec_from_file_location("note_statistics_under_test", source)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class ReferenceStatisticsContractTests(DataFileTestCase):
    """成员02 的数据 → 3 号筛选 → 4 号统计，数值必须与 README 样例一致。"""

    def setUp(self) -> None:
        super().setUp()
        self.statistics = load_statistics_module()
        patcher = ensure_queries_module()
        if patcher is not None:
            self.addCleanup(patcher.stop)

    def stats(self, **filters) -> dict:
        merged = dict(NULL_FILTERS)
        merged.update(filters)
        return self.statistics.get_statistics(merged)

    def test_readme_steps_2_to_4_income_expense_balance(self):
        """§3.10 步骤 2—4：收入 100.00 元、支出 12.50 元，结余 87.50 元。"""
        income = create_record(INCOME_PAYLOAD)
        expense = create_record(EXPENSE_PAYLOAD)
        self.assertNotEqual(income["id"], expense["id"])

        self.assertEqual(
            self.stats(),
            {
                "income": 10000,
                "expense": 1250,
                "balance": 8750,
                "count": 2,
                "by_category": [
                    {"category": "工资", "income": 10000, "expense": 0},
                    {"category": "饮食", "income": 0, "expense": 1250},
                ],
                "by_month": [{"month": "2026-11", "income": 10000, "expense": 1250}],
            },
        )

    def test_readme_step_6_category_filter(self):
        """§3.10 步骤 6：只看「饮食」时收入为 0、结余为负支出。"""
        create_record(INCOME_PAYLOAD)
        create_record(EXPENSE_PAYLOAD)

        result = self.stats(category="饮食")
        self.assertEqual(result["income"], 0)
        self.assertEqual(result["expense"], 1250)
        self.assertEqual(result["balance"], -1250)
        self.assertEqual(result["count"], 1)

    def test_readme_steps_12_to_13_delete_then_restart(self):
        """§3.10 步骤 12—13：删除后再统计，重启后 JSON 仍可读。"""
        create_record(INCOME_PAYLOAD)
        expense = create_record(EXPENSE_PAYLOAD)
        self.assertEqual(
            delete_record(expense["id"]), {"id": expense["id"], "deleted": True}
        )

        # 磁盘上的数据已经变成只剩工资一笔（模拟重启前落盘结果）。
        on_disk = json.loads(self.read_raw())
        self.assertEqual([item["category"] for item in on_disk], ["工资"])

        # 重新加载数据层模块 + 重建 4 号模块实例 ≈ 进程重启后的全新状态。
        reloaded_storage = importlib.reload(storage)
        data_file_patcher = patch.object(reloaded_storage, "DATA_FILE", self.data_file)
        data_file_patcher.start()
        self.addCleanup(data_file_patcher.stop)
        restarted_statistics = load_statistics_module()

        merged = dict(NULL_FILTERS)
        result = restarted_statistics.get_statistics(merged)
        self.assertEqual(result["income"], 10000)
        self.assertEqual(result["expense"], 0)
        self.assertEqual(result["balance"], 10000)
        self.assertEqual(result["count"], 1)

    def test_same_records_reach_statistics_as_returned_by_api(self):
        """2号返回的记录必须与 4 号读到的记录完全一致（同条件同口径）。"""
        created = create_record(EXPENSE_PAYLOAD)
        loaded = storage.load_records()
        self.assertEqual(loaded, [created])
        self.assertEqual(self.statistics.summarize_records(loaded)["count"], 1)

    def test_empty_data_returns_zero_summary(self):
        """§3.10 步骤 14：无数据时金额与计数均为 0，汇总数组为空。"""
        self.assertEqual(
            self.stats(),
            {
                "income": 0,
                "expense": 0,
                "balance": 0,
                "count": 0,
                "by_category": [],
                "by_month": [],
            },
        )


@unittest.skipUnless(HAS_REAL_QUERIES, "3号 queries.py 未交付，无法验证路由整合")
class EndToEndApiTests(DataFileTestCase):
    """§3.10 步骤 1—8：records + queries + stats 三个 Blueprint 挂同一应用跑通。"""

    def setUp(self) -> None:
        super().setUp()
        from flask import Flask

        from errors import register_error_handlers
        from records import records_bp

        self.statistics = load_statistics_module()
        self.queries = sys.modules["queries"]

        app = Flask(__name__)
        app.json.ensure_ascii = False
        app.json.sort_keys = False
        register_error_handlers(app)
        app.register_blueprint(records_bp)
        app.register_blueprint(self.queries.queries_bp)
        app.register_blueprint(self.statistics.stats_bp)
        app.testing = True
        self.client = app.test_client()

    def test_readme_steps_1_to_8(self):
        # 步骤 1：空数据文件
        first = self.client.get("/api/records").get_json()
        self.assertEqual(first["data"], [])
        self.assertEqual(first["meta"]["total"], 0)
        self.assertEqual(first["meta"]["returned"], 0)
        self.assertEqual(first["meta"]["limit"], 10)

        # 步骤 2、3：新增收入与支出
        income = self.client.post("/api/records", json=INCOME_PAYLOAD)
        self.assertEqual(income.status_code, 201)
        expense = self.client.post("/api/records", json=EXPENSE_PAYLOAD)
        self.assertEqual(expense.status_code, 201)
        self.assertNotEqual(
            income.get_json()["data"]["id"], expense.get_json()["data"]["id"]
        )

        # 步骤 4：统计三个金额与计数
        stats = self.client.get("/api/stats").get_json()["data"]
        self.assertEqual(
            (stats["income"], stats["expense"], stats["balance"], stats["count"]),
            (10000, 1250, 8750, 2),
        )

        # 步骤 5：金额端点包含（min=max=1250 恰好命中饮食）
        listed = self.client.get(
            "/api/records?type=expense&min_amount=1250&max_amount=1250"
        ).get_json()
        self.assertEqual(len(listed["data"]), 1)
        self.assertEqual(listed["data"][0]["category"], "饮食")

        # 步骤 6：类别筛选后统计
        filtered = self.client.get("/api/stats?category=饮食").get_json()["data"]
        self.assertEqual(
            (filtered["income"], filtered["expense"], filtered["balance"],
             filtered["count"]),
            (0, 1250, -1250, 1),
        )

        # 步骤 7：同日记录按插入位置倒序，后追加优先
        latest = self.client.get("/api/records?limit=1").get_json()
        self.assertEqual(latest["meta"]["total"], 2)
        self.assertEqual(latest["meta"]["returned"], 1)
        self.assertEqual(latest["data"][0]["category"], "饮食")

        # 步骤 8：统计接口拒绝 limit
        rejected = self.client.get("/api/stats?limit=1")
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(
            rejected.get_json(),
            {
                "error": "不支持的查询参数：limit",
                "code": "VALIDATION_ERROR",
                "field": "limit",
            },
        )

    def test_delete_then_list_and_stats_follow(self):
        """删除后列表与统计同步收缩（验收清单第 7 条）。"""
        first = self.client.post("/api/records", json=INCOME_PAYLOAD).get_json()["data"]
        second = self.client.post("/api/records", json=EXPENSE_PAYLOAD).get_json()["data"]

        self.assertEqual(
            self.client.delete(f"/api/records/{second['id']}").status_code, 200
        )
        again = self.client.delete(f"/api/records/{second['id']}")
        self.assertEqual(again.status_code, 404)
        self.assertEqual(again.get_json()["code"], "RECORD_NOT_FOUND")

        listed = self.client.get("/api/records?limit=all").get_json()
        self.assertEqual([item["id"] for item in listed["data"]], [first["id"]])

        stats = self.client.get("/api/stats").get_json()["data"]
        self.assertEqual((stats["income"], stats["expense"], stats["count"]),
                         (10000, 0, 1))


if __name__ == "__main__":
    unittest.main()
