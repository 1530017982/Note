"""Storage failure/recovery tests and real query/statistics integration tests."""

import copy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from uuid import UUID
from unittest.mock import patch

from flask import request
from jinja2 import DictLoader

from app import create_app
from errors import AppError
import storage


def example_record(**changes):
    record = dict(id=storage.new_record_id(), date="2026-11-07", type="expense",
                  amount=1250, category="饮食", note="午餐")
    record.update(changes)
    return record


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "data" / "records.json"
        override = patch.object(storage, "DATA_FILE", self.path)
        override.start()
        self.addCleanup(override.stop)

    def assert_storage_error(self, callback):
        with self.assertRaises(AppError) as caught:
            callback()
        self.assertEqual((caught.exception.status, caught.exception.code),
                         (500, "STORAGE_ERROR"))

    def test_missing_file_initializes(self):
        self.assertEqual(storage.load_records(), [])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), [])

    def test_record_ids_are_unique_uuid4_strings(self):
        identifiers = {storage.new_record_id() for _ in range(200)}
        self.assertEqual(len(identifiers), 200)
        for identifier in identifiers:
            self.assertEqual(UUID(identifier).version, 4)

    def test_save_load_unicode_and_independent_objects(self):
        original = [example_record()]
        storage.save_records(original)
        loaded = storage.load_records()
        self.assertEqual(loaded, original)
        loaded[0]["note"] = "changed"
        self.assertEqual(storage.load_records(), original)
        self.assertIn("午餐", self.path.read_text(encoding="utf-8"))

    def test_fresh_module_reads_persisted_data(self):
        records = [example_record()]
        storage.save_records(records)
        spec = importlib.util.spec_from_file_location("fresh_storage", storage.__file__)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        fresh.DATA_FILE = self.path
        self.assertEqual(fresh.load_records(), records)

    def test_corrupt_existing_file_is_preserved_on_read_and_save(self):
        self.path.parent.mkdir(parents=True)
        for content in (b"", b"   \n\n", b"not json", b"{}", b"[null]", b"\xff"):
            with self.subTest(content=content):
                self.path.write_bytes(content)
                self.assert_storage_error(storage.load_records)
                self.assert_storage_error(lambda: storage.save_records([]))
                self.assertEqual(self.path.read_bytes(), content)

    def test_invalid_records_do_not_replace_valid_data(self):
        original = [example_record()]
        storage.save_records(original)
        bad = [None, {}, [example_record(amount=True)], [example_record(amount=0)],
               [example_record(amount=1000000000)], [example_record(date="2026-02-30")],
               [example_record(id="demo-1")], [example_record(type="other")],
               [example_record(category=" ")], [example_record(note="x" * 201)]]
        for records in bad:
            with self.subTest(records=records):
                self.assert_storage_error(lambda: storage.save_records(records))
                self.assertEqual(storage.load_records(), original)

    def test_duplicate_ids_are_rejected(self):
        row = example_record()
        self.assert_storage_error(lambda: storage.save_records([row, copy.deepcopy(row)]))
        self.assertFalse(self.path.exists())

    def test_invalid_saved_record_is_detected_without_overwrite(self):
        self.path.parent.mkdir(parents=True)
        content = json.dumps([example_record(amount=False)]).encode("utf-8")
        self.path.write_bytes(content)
        self.assert_storage_error(storage.load_records)
        self.assertEqual(self.path.read_bytes(), content)

    def test_replace_failure_preserves_original_and_cleans_temp(self):
        original = [example_record()]
        storage.save_records(original)
        before = self.path.read_bytes()
        with patch.object(storage.os, "replace", side_effect=PermissionError("private path")):
            self.assert_storage_error(lambda: storage.save_records([]))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob("records-*.tmp")), [])

    def test_shared_lock_protects_entire_read_modify_write(self):
        storage.load_records()
        failures = []

        def append_record():
            try:
                with storage.records_lock:
                    records = storage.load_records()
                    records.append(example_record())
                    storage.save_records(records)
            except Exception as exc:
                failures.append(exc)

        threads = [Thread(target=append_record) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(len(storage.load_records()), 12)

    def test_file_path_is_project_relative(self):
        spec = importlib.util.spec_from_file_location("path_storage", storage.__file__)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        self.assertEqual(fresh.DATA_FILE,
                         Path(storage.__file__).resolve().parent / "data" / "records.json")


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "records.json"
        override = patch.object(storage, "DATA_FILE", self.path)
        override.start()
        self.addCleanup(override.stop)
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def test_real_queries_and_stats_share_filters(self):
        storage.save_records([
            example_record(type="income", amount=10000, category="工资", note=""),
            example_record(),
        ])
        listed = self.client.get("/api/records?limit=1").get_json()
        self.assertEqual(listed["meta"], {"total": 2, "returned": 1, "limit": 1})
        stats = self.client.get("/api/stats").get_json()["data"]
        self.assertEqual((stats["income"], stats["expense"], stats["balance"], stats["count"]),
                         (10000, 1250, 8750, 2))
        query = {"type": "expense", "category": "饮食", "min_amount": "1250"}
        listed = self.client.get("/api/records", query_string=query).get_json()
        stats = self.client.get("/api/stats", query_string=query).get_json()["data"]
        self.assertEqual(listed["meta"]["total"], stats["count"])
        self.assertEqual(stats["balance"], -1250)

    def test_create_query_stats_and_delete_use_same_application(self):
        income = self.client.post("/api/records", json={
            "date": "2026-11-07", "type": "income", "amount": 10000,
            "category": "工资", "note": "",
        })
        expense = self.client.post("/api/records", json={
            "date": "2026-11-07", "type": "expense", "amount": 1250,
            "category": "饮食", "note": "",
        })
        self.assertEqual((income.status_code, expense.status_code), (201, 201))
        income_id = income.get_json()["data"]["id"]
        expense_id = expense.get_json()["data"]["id"]
        listed = self.client.get("/api/records?limit=1").get_json()
        self.assertEqual(listed["data"][0]["id"], expense_id)
        self.assertEqual(listed["meta"]["total"], 2)
        stats = self.client.get("/api/stats").get_json()["data"]
        self.assertEqual((stats["income"], stats["expense"], stats["balance"]),
                         (10000, 1250, 8750))
        self.assertEqual(self.client.delete(f"/api/records/{expense_id}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/records/{expense_id}").status_code, 404)
        listed = self.client.get("/api/records?limit=all").get_json()["data"]
        self.assertEqual([row["id"] for row in listed], [income_id])
        stats = self.client.get("/api/stats").get_json()["data"]
        self.assertEqual((stats["income"], stats["expense"], stats["count"]), (10000, 0, 1))

    def test_empty_queries_and_stats_initialize_storage(self):
        self.assertEqual(self.client.get("/api/records").get_json()["data"], [])
        self.assertEqual(self.client.get("/api/stats").get_json()["data"]["count"], 0)

    def test_invalid_parameters_are_json_without_reading_storage(self):
        for path in ("/api/records?type=income&type=expense",
                     "/api/records?start_date=2026-02-30", "/api/stats?limit=1"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["code"], "VALIDATION_ERROR")
                self.assertFalse(self.path.exists())

    def test_storage_errors_are_json_and_hide_paths(self):
        self.path.write_text("broken", encoding="utf-8")
        for path in ("/api/records", "/api/stats"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.get_json()["code"], "STORAGE_ERROR")
            self.assertNotIn(str(self.path), response.get_data(as_text=True))

    def test_unknown_api_and_method_errors_are_json(self):
        self.assertEqual(self.client.get("/api/missing").get_json()["code"], "NOT_FOUND")
        response = self.client.post("/api/stats")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.get_json()["code"], "METHOD_NOT_ALLOWED")
        self.assertIn("GET", response.headers["Allow"])

    def test_framework_json_errors_and_unexpected_errors(self):
        @self.app.post("/api/test-json")
        def parse_json():
            return request.get_json()

        @self.app.get("/api/test-failure")
        def fail():
            raise RuntimeError("secret internal path")

        response = self.client.post("/api/test-json", data="{}", content_type="text/plain")
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.get_json()["code"], "UNSUPPORTED_MEDIA_TYPE")
        response = self.client.post("/api/test-json", data="{", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["code"], "INVALID_JSON")
        with self.assertLogs(self.app.logger, level="ERROR"):
            response = self.client.get("/api/test-failure")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["code"], "INTERNAL_ERROR")
        self.assertNotIn("secret", response.get_data(as_text=True))

    def test_entry_renders_delivered_template(self):
        self.app.jinja_loader = DictLoader({"index.html": "<h1>记账界面</h1>"})
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("记账界面", response.get_data(as_text=True))

    def test_incomplete_delivery_has_explicit_homepage(self):
        self.app.jinja_loader = DictLoader({})
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("主页面尚未交付", response.get_data(as_text=True))

    def test_internal_dependency_errors_are_not_silently_skipped(self):
        missing = ModuleNotFoundError("dependency missing", name="private_dependency")
        with patch("app.importlib.import_module", side_effect=missing):
            with self.assertRaises(ModuleNotFoundError):
                create_app({"TESTING": True})


if __name__ == "__main__":
    unittest.main()
