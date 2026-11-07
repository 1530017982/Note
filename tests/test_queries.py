"""查询模块单元测试，使用隔离的存储和错误依赖。

运行：python -m unittest -v tests.test_queries
真实 JSON 与应用入口的联调由 test_storage_app.py 验证。
"""

import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

from flask import Flask, jsonify
from werkzeug.datastructures import MultiDict


class ContractAppError(Exception):
    def __init__(self, status, code, message, field=None):
        super().__init__(message)
        self.status, self.code, self.message, self.field = status, code, message, field


errors_stub = types.ModuleType("errors")
errors_stub.AppError = ContractAppError
storage_stub = types.ModuleType("storage")
storage_stub.load_records = Mock()
spec = importlib.util.spec_from_file_location(
    "queries_under_test", Path(__file__).resolve().parents[1] / "queries.py"
)
queries = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"errors": errors_stub, "storage": storage_stub}):
    spec.loader.exec_module(queries)


def record(number, day, kind, amount, category):
    return dict(id=str(number), date=day, type=kind, amount=amount,
                category=category, note="测试数据")


class QueryTests(unittest.TestCase):
    """隔离验证参数解析、组合条件、排序、条数限制和路由响应。"""
    def setUp(self):
        self.rows = [
            record(1, "2026-11-07", "income", 10000, "工资"),
            record(2, "2026-11-07", "expense", 1250, "饮食"),
            record(3, "2026-11-01", "expense", 100, "交通"),
            record(4, "2026-11-08", "expense", 5000, "饮食"),
        ]
        storage_stub.load_records.reset_mock(return_value=True, side_effect=True)
        storage_stub.load_records.return_value = self.rows

    def parse(self, pairs=(), allow_limit=True):
        return queries.parse_query(MultiDict(pairs), allow_limit=allow_limit)

    def assert_invalid(self, pairs, field, allow_limit=True):
        with self.assertRaises(ContractAppError) as raised:
            self.parse(pairs, allow_limit=allow_limit)
        error = raised.exception
        self.assertEqual((error.status, error.code, error.field),
                         (400, "VALIDATION_ERROR", field))

    def test_defaults_and_fixed_filter_keys(self):
        filters, limit = self.parse()
        self.assertEqual(filters, dict.fromkeys(queries.FILTER_KEYS))
        self.assertEqual(limit, 10)

    def test_empty_parameters_and_whitespace(self):
        filters, limit = self.parse([(key, "  ") for key in (*queries.FILTER_KEYS, "limit")])
        self.assertTrue(all(value is None for value in filters.values()))
        self.assertEqual(limit, 10)
        filters, limit = self.parse([("category", " 饮食 "), ("min_amount", " 00100 "),
                                     ("type", " expense "), ("limit", " all ")])
        self.assertEqual((filters["category"], filters["min_amount"], filters["type"], limit),
                         ("饮食", 100, "expense", "all"))

    def test_valid_leap_date_and_amount_boundaries(self):
        filters, _ = self.parse([("start_date", "2024-02-29"),
                                ("min_amount", "0"), ("max_amount", "999999999")])
        self.assertEqual(filters["start_date"], "2024-02-29")
        self.assertEqual(filters["min_amount"], 0)
        self.assertEqual(filters["max_amount"], 999999999)

    def test_invalid_dates(self):
        for value in ("2026-02-29", "2026-02-30", "2026-1-01", "0000-01-01",
                      "20261107", "2026-11-07T00:00:00", "２０２６-11-07"):
            with self.subTest(value=value):
                self.assert_invalid([("start_date", value)], "start_date")

    def test_invalid_amounts(self):
        for key in ("min_amount", "max_amount"):
            for value in ("-1", "+1", "1.5", "1e2", "１２", "1000000000", "9" * 5000):
                with self.subTest(key=key, value=value[:20]):
                    self.assert_invalid([(key, value)], key)

    def test_limits(self):
        for raw, expected in (("1", 1), ("100", 100), ("010", 10), ("all", "all")):
            with self.subTest(raw=raw):
                self.assertEqual(self.parse([("limit", raw)])[1], expected)
        for raw in ("0", "101", "-1", "+1", "1.0", "ALL"):
            with self.subTest(raw=raw):
                self.assert_invalid([("limit", raw)], "limit")

    def test_unknown_and_repeated_parameters(self):
        self.assert_invalid([("typo", "")], "typo")
        for key in (*queries.FILTER_KEYS, "limit"):
            with self.subTest(key=key):
                self.assert_invalid([(key, ""), (key, "")], key)

    def test_type_category_and_ranges(self):
        self.assert_invalid([("type", "Expense")], "type")
        self.assert_invalid([("category", "类" * 21)], "category")
        self.assert_invalid([("start_date", "2026-11-08"), ("end_date", "2026-11-07")], "end_date")
        self.assert_invalid([("min_amount", "2"), ("max_amount", "1")], "max_amount")

    def test_statistics_reuses_filters_without_limit(self):
        filters, limit = self.parse([("type", "expense")], allow_limit=False)
        self.assertIsNone(limit)
        self.assertEqual(len(queries.filter_records(self.rows, filters)), 3)
        for value in ("", "all", "1"):
            self.assert_invalid([("limit", value)], "limit", allow_limit=False)

    def test_combined_filters_include_both_endpoints(self):
        filters, _ = self.parse([
            ("start_date", "2026-11-07"), ("end_date", "2026-11-08"),
            ("type", "expense"), ("category", "饮食"),
            ("min_amount", "1250"), ("max_amount", "5000")])
        self.assertEqual([r["id"] for r in queries.filter_records(self.rows, filters)], ["2", "4"])

    def test_each_filter_independently(self):
        cases = [
            ("start_date", "2026-11-08", ["4"]),
            ("end_date", "2026-11-01", ["3"]),
            ("type", "income", ["1"]),
            ("category", "工资", ["1"]),
            ("min_amount", "5000", ["1", "4"]),
            ("max_amount", "1250", ["2", "3"]),
        ]
        for key, value, expected in cases:
            with self.subTest(key=key):
                filters, _ = self.parse([(key, value)])
                self.assertEqual([r["id"] for r in queries.filter_records(self.rows, filters)], expected)

    def test_sort_date_then_reverse_insertion_without_mutation(self):
        before = copy.deepcopy(self.rows)
        filters, _ = self.parse()
        result = queries.query_records(filters, "all")
        self.assertEqual([r["id"] for r in result["data"]], ["4", "2", "1", "3"])
        self.assertEqual(self.rows, before)
        storage_stub.load_records.assert_called_once_with()

    def test_filter_before_limit_and_meta_before_truncation(self):
        filters, _ = self.parse([("type", "income")])
        self.assertEqual(queries.query_records(filters, 1)["data"][0]["id"], "1")
        filters, _ = self.parse()
        result = queries.query_records(filters, 1)
        self.assertEqual(result["meta"], {"total": 4, "returned": 1, "limit": 1})

    def test_default_ten_and_unlimited(self):
        storage_stub.load_records.return_value = [
            record(n, "2026-11-07", "expense", 100, "其他") for n in range(12)]
        filters, _ = self.parse()
        result = queries.query_records(filters)
        self.assertEqual([r["id"] for r in result["data"]], [str(n) for n in range(11, 1, -1)])
        self.assertEqual(result["meta"], {"total": 12, "returned": 10, "limit": 10})
        self.assertEqual(len(queries.query_records(filters, "all")["data"]), 12)

    def test_equal_boundaries_and_case_sensitive_category(self):
        filters, _ = self.parse([("start_date", "2026-11-07"), ("end_date", "2026-11-07"),
                                ("min_amount", "1250"), ("max_amount", "1250")])
        self.assertEqual([r["id"] for r in queries.filter_records(self.rows, filters)], ["2"])
        rows = [record(1, "2026-11-07", "income", 100, "Food")]
        filters, _ = self.parse([("category", "food")])
        self.assertEqual(queries.filter_records(rows, filters), [])

    def test_empty_data_and_no_match(self):
        filters, _ = self.parse([("category", "不存在")])
        self.assertEqual(queries.query_records(filters), {
            "data": [], "meta": {"total": 0, "returned": 0, "limit": 10}})
        storage_stub.load_records.return_value = []
        filters, _ = self.parse()
        self.assertEqual(queries.query_records(filters, "all")["meta"],
                         {"total": 0, "returned": 0, "limit": "all"})

    def make_client(self):
        app = Flask(__name__)
        app.testing = True
        app.register_blueprint(queries.queries_bp)

        @app.errorhandler(ContractAppError)
        def handle(error):
            body = {"error": error.message, "code": error.code}
            if error.field is not None:
                body["field"] = error.field
            return jsonify(body), error.status

        return app.test_client()

    def test_http_success_and_chinese_query(self):
        response = self.make_client().get("/api/records", query_string={"category": "饮食", "limit": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"][0]["id"], "4")
        self.assertEqual(response.get_json()["meta"], {"total": 2, "returned": 1, "limit": 1})

    def test_http_validation_does_not_read_storage(self):
        client = self.make_client()
        for query, field in (("type=income&type=expense", "type"),
                             ("limit=0", "limit"), ("unknown=1", "unknown"),
                             ("start_date=2026-02-30", "start_date")):
            with self.subTest(query=query):
                response = client.get("/api/records?" + query)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["field"], field)
                self.assertEqual(response.get_json()["code"], "VALIDATION_ERROR")
        storage_stub.load_records.assert_not_called()

    def test_storage_error_propagates_to_shared_handler(self):
        storage_stub.load_records.side_effect = ContractAppError(500, "STORAGE_ERROR", "读取账单失败")
        response = self.make_client().get("/api/records")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json(), {"error": "读取账单失败", "code": "STORAGE_ERROR"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
