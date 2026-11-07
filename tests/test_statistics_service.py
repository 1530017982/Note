"""统计模块单元测试：使用真实 Flask 客户端，以替身隔离查询和存储依赖。"""

import copy
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock, patch

from flask import Flask, jsonify

import statistics_service as stats


class ContractError(Exception):
    """模拟公共 AppError 的状态与响应字段。"""

    def __init__(self, status, code, message, field=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field


class StatisticsTests(unittest.TestCase):
    """检查汇总口径、接口包装及依赖调用，不读写正式账单。"""
    def setUp(self):
        self.records = [
            dict(id="1", date="2026-11-07", type="income",
                 amount=10000, category="工资", note=""),
            dict(id="2", date="2026-11-07", type="expense",
                 amount=1250, category="饮食", note=""),
            dict(id="3", date="2026-10-31", type="expense",
                 amount=500, category="饮食", note=""),
        ]
        self.filters = dict.fromkeys([
            "start_date", "end_date", "type", "category",
            "min_amount", "max_amount",
        ])
        self.storage = ModuleType("storage")
        self.storage.load_records = Mock(return_value=self.records)
        self.queries = ModuleType("queries")
        self.queries.filter_records = Mock(return_value=self.records)
        self.queries.parse_query = Mock(return_value=(self.filters, None))
        dependencies = patch.dict(sys.modules, {
            "storage": self.storage,
            "queries": self.queries,
        })
        dependencies.start()
        self.addCleanup(dependencies.stop)

        app = Flask(__name__)
        app.testing = True
        app.register_blueprint(stats.stats_bp)

        # 入口应注册公共异常处理器；测试只模拟该入口职责。
        @app.errorhandler(ContractError)
        def handle_error(error):
            body = {"error": error.message, "code": error.code}
            if error.field is not None:
                body["field"] = error.field
            return jsonify(body), error.status

        self.client = app.test_client()

    def test_summary_count_groups_and_no_mutation(self):
        before = copy.deepcopy(self.records)
        result = stats.summarize_records(self.records)
        self.assertEqual(result, {
            "income": 10000, "expense": 1750, "balance": 8250,
            "count": 3,
            "by_category": [
                {"category": "工资", "income": 10000, "expense": 0},
                {"category": "饮食", "income": 0, "expense": 1750},
            ],
            "by_month": [
                {"month": "2026-10", "income": 0, "expense": 500},
                {"month": "2026-11", "income": 10000, "expense": 1250},
            ],
        })
        self.assertEqual(self.records, before)
        self.assertEqual(stats.calculate_stats(self.records), result)

    def test_get_statistics_reads_once_and_uses_filtered_records(self):
        self.filters["type"] = "expense"
        self.queries.filter_records.return_value = self.records[1:]
        result = stats.get_statistics(self.filters)
        self.storage.load_records.assert_called_once_with()
        self.queries.filter_records.assert_called_once_with(
            self.records, self.filters
        )
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["income"], 0)
        self.assertEqual(result["balance"], -1750)

    def test_route_wraps_data_and_disables_limit(self):
        self.filters.update(type="expense", min_amount=1250)
        self.queries.filter_records.return_value = [self.records[1]]
        response = self.client.get("/api/stats?type=expense&min_amount=1250")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "data": stats.summarize_records([self.records[1]])
        })
        args, kwargs = self.queries.parse_query.call_args
        self.assertEqual(kwargs, {"allow_limit": False})
        self.assertEqual(args[0].to_dict(), {
            "type": "expense", "min_amount": "1250"
        })
        self.storage.load_records.assert_called_once_with()
        self.queries.filter_records.assert_called_once_with(
            self.records, self.filters
        )

    def test_route_empty_result(self):
        self.queries.filter_records.return_value = []
        response = self.client.get("/api/stats")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"data": {
            "income": 0, "expense": 0, "balance": 0, "count": 0,
            "by_category": [], "by_month": [],
        }})

    def test_route_counts_more_than_ten_records(self):
        self.queries.filter_records.return_value = [self.records[0]] * 11
        result = self.client.get("/api/stats").get_json()["data"]
        self.assertEqual(result["count"], 11)
        self.assertEqual(result["income"], 110000)

    def test_parser_error_uses_public_handler_and_skips_storage(self):
        self.queries.parse_query.side_effect = ContractError(
            400, "VALIDATION_ERROR", "统计接口不接受 limit", "limit"
        )
        response = self.client.get("/api/stats?limit=1")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {
            "error": "统计接口不接受 limit",
            "code": "VALIDATION_ERROR", "field": "limit",
        })
        self.assertFalse(self.queries.parse_query.call_args.kwargs["allow_limit"])
        self.storage.load_records.assert_not_called()
        self.queries.filter_records.assert_not_called()

    def test_duplicate_arguments_reach_shared_parser_unchanged(self):
        self.queries.parse_query.side_effect = ContractError(
            400, "VALIDATION_ERROR", "不接受重复参数", "type"
        )
        response = self.client.get("/api/stats?type=income&type=expense")
        self.assertEqual(response.status_code, 400)
        args = self.queries.parse_query.call_args.args[0]
        self.assertEqual(args.getlist("type"), ["income", "expense"])
        self.storage.load_records.assert_not_called()

    def test_storage_error_uses_public_handler(self):
        self.storage.load_records.side_effect = ContractError(
            500, "STORAGE_ERROR", "账单数据读取失败"
        )
        response = self.client.get("/api/stats")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {
            "error": "账单数据读取失败", "code": "STORAGE_ERROR"
        })
        self.queries.filter_records.assert_not_called()

    def test_post_does_not_run_statistics(self):
        response = self.client.post("/api/stats")
        self.assertEqual(response.status_code, 405)
        self.storage.load_records.assert_not_called()


if __name__ == "__main__":
    unittest.main()
