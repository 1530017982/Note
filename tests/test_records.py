"""成员02 记账业务测试：字段校验、新增、删除与路由契约（README §3.2、§3.3）。"""

from __future__ import annotations

import json
import threading
import unittest
import uuid
from unittest.mock import patch

import storage
from errors import AppError
from records import create_record, delete_record, validate_payload
from tests.support import DataFileTestCase, build_test_app, storage_error


def payload(**overrides) -> dict:
    """构造一份合法的 POST 请求体。"""
    data = {
        "date": "2026-11-07",
        "type": "expense",
        "amount": 1250,
        "category": "饮食",
        "note": "午餐",
    }
    data.update(overrides)
    return data


def without(field: str) -> dict:
    data = payload()
    del data[field]
    return data


class ValidatePayloadTests(unittest.TestCase):
    def test_valid_payload_is_normalized(self):
        result = validate_payload(
            payload(category="  饮食  ", note="  午餐  ", amount=1250)
        )
        self.assertEqual(
            result,
            {
                "date": "2026-11-07",
                "type": "expense",
                "amount": 1250,
                "category": "饮食",
                "note": "午餐",
            },
        )

    def test_note_is_optional_and_defaults_to_empty(self):
        result = validate_payload(without("note"))
        self.assertEqual(result["note"], "")

    def test_rejections_report_the_offending_field(self):
        cases = {
            "缺少日期": without("date"),
            "缺少类型": without("type"),
            "缺少金额": without("amount"),
            "缺少类别": without("category"),
            "日期不存在": payload(date="2026-02-30"),
            "日期未补零": payload(date="2026-11-7"),
            "日期换成斜杠": payload(date="2026/11/07"),
            "日期带空白": payload(date="2026-11-07 "),
            "日期不是文本": payload(date=20261107),
            "类型大小写不符": payload(type="INCOME"),
            "类型不支持": payload(type="transfer"),
            "金额为小数": payload(amount=12.5),
            "金额为字符串": payload(amount="1250"),
            "金额为布尔": payload(amount=True),
            "金额为零": payload(amount=0),
            "金额为负数": payload(amount=-1),
            "金额超上限": payload(amount=1_000_000_000),
            "类别全为空白": payload(category="   "),
            "类别超长": payload(category="饮" * 21),
            "类别不是文本": payload(category=1),
            "备注超长": payload(note="备" * 201),
            "备注不是文本": payload(note=["x"]),
            "备注显式 null": payload(note=None),
            "未知字段": payload(foo="bar"),
        }
        expected_fields = {
            "缺少日期": "date",
            "缺少类型": "type",
            "缺少金额": "amount",
            "缺少类别": "category",
            "日期不存在": "date",
            "日期未补零": "date",
            "日期换成斜杠": "date",
            "日期带空白": "date",
            "日期不是文本": "date",
            "类型大小写不符": "type",
            "类型不支持": "type",
            "金额为小数": "amount",
            "金额为字符串": "amount",
            "金额为布尔": "amount",
            "金额为零": "amount",
            "金额为负数": "amount",
            "金额超上限": "amount",
            "类别全为空白": "category",
            "类别超长": "category",
            "类别不是文本": "category",
            "备注超长": "note",
            "备注不是文本": "note",
            "备注显式 null": "note",
            "未知字段": "foo",
        }
        self.assertEqual(set(cases), set(expected_fields))
        for name, data in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(AppError) as caught:
                    validate_payload(data)
                error = caught.exception
                self.assertEqual(error.status, 400)
                self.assertEqual(error.code, "VALIDATION_ERROR")
                self.assertEqual(error.field, expected_fields[name])

    def test_rejects_client_supplied_id(self):
        with self.assertRaises(AppError) as caught:
            validate_payload(payload(id="7fb7d372-9bd9-4bd6-a3cb-c9de6079893a"))
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(caught.exception.code, "VALIDATION_ERROR")
        self.assertEqual(caught.exception.field, "id")

    def test_rejects_non_object_payload(self):
        for value in ([], "x", 1, None):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as caught:
                    validate_payload(value)
                self.assertEqual(caught.exception.code, "INVALID_JSON")

    def test_amount_boundaries_accepted(self):
        for amount in (1, 999_999_999):
            with self.subTest(amount=amount):
                self.assertEqual(validate_payload(payload(amount=amount))["amount"], amount)

    def test_category_and_note_boundaries_accepted(self):
        result = validate_payload(payload(category="饮" * 20, note="备" * 200))
        self.assertEqual(len(result["category"]), 20)
        self.assertEqual(len(result["note"]), 200)


class CreateRecordTests(DataFileTestCase):
    def test_creates_record_with_generated_id_and_contract_field_order(self):
        record = create_record(payload())

        self.assertEqual(
            set(record), {"id", "date", "type", "amount", "category", "note"}
        )
        self.assertEqual(uuid.UUID(record["id"]).version, 4)
        self.assertEqual(record["amount"], 1250)
        self.assertEqual(record["note"], "午餐")

        self.assertEqual(storage.load_records(), [record])

    def test_appends_to_end_preserving_insertion_order(self):
        first = create_record(payload(date="2026-11-05", category="交通", amount=500))
        second = create_record(payload(date="2026-11-07", category="饮食"))
        self.assertEqual([item["id"] for item in storage.load_records()],
                         [first["id"], second["id"]])

    def test_identical_content_is_allowed_multiple_times(self):
        first = create_record(payload())
        second = create_record(payload())
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(storage.load_records()), 2)

    def test_income_and_expense_both_supported(self):
        income = create_record(payload(type="income", amount=10000, category="工资"))
        expense = create_record(payload(type="expense", amount=1250))
        self.assertEqual(income["type"], "income")
        self.assertEqual(expense["type"], "expense")

    def test_invalid_payload_does_not_write_anything(self):
        with self.assertRaises(AppError):
            create_record(payload(amount=12.5))
        self.assertEqual(storage.load_records(), [])

    def test_storage_failure_propagates(self):
        with patch("records.save_records", side_effect=storage_error()):
            with self.assertRaises(AppError) as caught:
                create_record(payload())
        self.assertEqual(caught.exception.code, "STORAGE_ERROR")

    def test_concurrent_creates_do_not_lose_records(self):
        total = 10
        errors: list[BaseException] = []

        def worker():
            try:
                create_record(payload())
            except BaseException as exc:  # pragma: no cover - 失败时用于定位
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(total)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        records = storage.load_records()
        self.assertEqual(len(records), total)
        self.assertEqual(len({item["id"] for item in records}), total)


class DeleteRecordTests(DataFileTestCase):
    def test_deletes_existing_record(self):
        record = create_record(payload())
        result = delete_record(record["id"])

        self.assertEqual(result, {"id": record["id"], "deleted": True})
        self.assertEqual(storage.load_records(), [])

    def test_deleting_twice_returns_404(self):
        record = create_record(payload())
        delete_record(record["id"])
        with self.assertRaises(AppError) as caught:
            delete_record(record["id"])
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(caught.exception.code, "RECORD_NOT_FOUND")

    def test_unknown_id_does_not_modify_file(self):
        keeper = create_record(payload())
        before = self.read_raw()
        with self.assertRaises(AppError) as caught:
            delete_record(str(uuid.uuid4()))
        self.assertEqual(caught.exception.code, "RECORD_NOT_FOUND")
        self.assertEqual(self.read_raw(), before)
        self.assertEqual(storage.load_records(), [keeper])

    def test_malformed_id_returns_404(self):
        create_record(payload())
        for value in ("", "   ", "not-a-uuid", None, 123):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as caught:
                    delete_record(value)
                self.assertEqual(caught.exception.status, 404)
                self.assertEqual(caught.exception.code, "RECORD_NOT_FOUND")

    def test_storage_failure_propagates(self):
        record = create_record(payload())
        with patch("records.save_records", side_effect=storage_error()):
            with self.assertRaises(AppError) as caught:
                delete_record(record["id"])
        self.assertEqual(caught.exception.code, "STORAGE_ERROR")


class RecordsRouteTests(DataFileTestCase):
    def setUp(self):
        super().setUp()
        self.client = build_test_app().test_client()

    def test_post_returns_201_with_full_record(self):
        response = self.client.post("/api/records", json=payload())
        self.assertEqual(response.status_code, 201)

        body = response.get_json()
        self.assertEqual(list(body), ["data"])
        record = body["data"]
        self.assertEqual(
            set(record), {"id", "date", "type", "amount", "category", "note"}
        )
        self.assertEqual(record["amount"], 1250)
        self.assertEqual(len(storage.load_records()), 1)

    def test_post_requires_json_content_type(self):
        response = self.client.post(
            "/api/records", data=json.dumps(payload()), content_type="text/plain"
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.get_json()["code"], "UNSUPPORTED_MEDIA_TYPE")

    def test_post_broken_json_returns_invalid_json(self):
        response = self.client.post(
            "/api/records", data='{"date": ', content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "INVALID_JSON")

    def test_post_non_object_json_returns_invalid_json(self):
        response = self.client.post("/api/records", json=[payload()])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "INVALID_JSON")

    def test_post_validation_error_body_has_field(self):
        response = self.client.post("/api/records", json=payload(amount=12.5))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {
                "error": "金额必须为1—999999999之间的整数分",
                "code": "VALIDATION_ERROR",
                "field": "amount",
            },
        )
        self.assertEqual(storage.load_records(), [])

    def test_delete_returns_200_with_id_and_flag(self):
        record = self.client.post("/api/records", json=payload()).get_json()["data"]
        response = self.client.delete(f"/api/records/{record['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"data": {"id": record["id"], "deleted": True}},
        )

    def test_delete_unknown_id_returns_404(self):
        response = self.client.delete(f"/api/records/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)
        body = response.get_json()
        self.assertEqual(body["code"], "RECORD_NOT_FOUND")
        self.assertNotIn("field", body)

    def test_get_list_uses_delivered_queries_module(self):
        response = self.client.get("/api/records")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"], [])

    def test_unknown_api_path_returns_404_json(self):
        response = self.client.get("/api/unknown")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["code"], "NOT_FOUND")

    def test_storage_failure_returns_500_without_leaking_path(self):
        with patch("records.save_records", side_effect=storage_error()):
            response = self.client.post("/api/records", json=payload())
        self.assertEqual(response.status_code, 500)
        body = response.get_json()
        self.assertEqual(body["code"], "STORAGE_ERROR")
        self.assertNotIn(str(self.temp_dir), response.get_data(as_text=True))

    def test_unexpected_error_returns_internal_error(self):
        with patch("records.save_records", side_effect=RuntimeError("boom")):
            response = self.client.post("/api/records", json=payload())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["code"], "INTERNAL_ERROR")
        self.assertNotIn("boom", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
