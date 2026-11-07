"""数据存储层测试：初始化、校验、原子写入、损坏文件保护（README §3.8）。"""

from __future__ import annotations

import importlib
import json
import threading
import unittest
import uuid
from unittest.mock import patch

import storage
from errors import AppError
from tests.support import DataFileTestCase, make_record


class NewRecordIdTests(unittest.TestCase):
    def test_generates_unique_uuid4_strings(self):
        ids = {storage.new_record_id() for _ in range(200)}
        self.assertEqual(len(ids), 200)
        for value in ids:
            self.assertIsInstance(value, str)
            self.assertEqual(uuid.UUID(value).version, 4)


class LoadRecordsTests(DataFileTestCase):
    def test_missing_file_is_initialized_to_empty_array(self):
        self.assertFalse(self.data_file.exists())
        self.assertEqual(storage.load_records(), [])
        self.assertTrue(self.data_file.exists())
        self.assertEqual(json.loads(self.read_raw()), [])

    def test_roundtrip_keeps_order_and_readable_chinese(self):
        first = make_record(category="工资", type="income", amount=10000, note="生活费")
        second = make_record(category="饮食", amount=1250, note="午餐")
        storage.save_records([first, second])

        raw = self.read_raw()
        # ensure_ascii=False：中文在文件里保持可读，便于演示与人工核对。
        self.assertIn("饮食", raw)
        self.assertNotIn("\\u996e", raw)

        self.assertEqual(storage.load_records(), [first, second])

    def test_module_reload_still_reads_saved_data(self):
        """重新加载模块 ≈ 进程重启：数据只应来自磁盘。"""
        record = make_record()
        storage.save_records([record])

        # 重新加载会把 DATA_FILE 重置为真实的代码相对路径，因此重定向要放到 reload 之后。
        reloaded = importlib.reload(storage)
        patcher = patch.object(reloaded, "DATA_FILE", self.data_file)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.assertEqual(reloaded.load_records(), [record])

    def test_empty_file_reports_storage_error_and_keeps_file(self):
        self.write_raw("")
        with self.assertRaises(AppError) as caught:
            storage.load_records()
        self.assertEqual(caught.exception.status, 500)
        self.assertEqual(caught.exception.code, "STORAGE_ERROR")
        self.assertEqual(self.read_raw(), "")

    def test_blank_file_reports_storage_error(self):
        self.write_raw("   \n\n")
        with self.assertRaises(AppError) as caught:
            storage.load_records()
        self.assertEqual(caught.exception.code, "STORAGE_ERROR")

    def test_broken_json_reports_storage_error_and_keeps_file(self):
        broken = '[{"id": "x", "date": "2026-11-07"'
        self.write_raw(broken)
        with self.assertRaises(AppError) as caught:
            storage.load_records()
        self.assertEqual(caught.exception.code, "STORAGE_ERROR")
        self.assertEqual(self.read_raw(), broken)

    def test_non_array_payload_rejected(self):
        self.write_raw(json.dumps({"records": []}, ensure_ascii=False))
        with self.assertRaises(AppError) as caught:
            storage.load_records()
        self.assertEqual(caught.exception.code, "STORAGE_ERROR")

    def test_duplicate_ids_rejected(self):
        record = make_record()
        self.write_raw(json.dumps([record, dict(record)], ensure_ascii=False))
        with self.assertRaises(AppError) as caught:
            storage.load_records()
        self.assertEqual(caught.exception.code, "STORAGE_ERROR")
        self.assertIn("重复 id", caught.exception.message)

    def test_invalid_stored_records_rejected(self):
        def without(field):
            record = make_record()
            del record[field]
            return record

        cases = {
            "金额为零": make_record(amount=0),
            "金额为负数": make_record(amount=-1),
            "金额为布尔": make_record(amount=True),
            "金额为字符串": make_record(amount="1250"),
            "金额超上限": make_record(amount=1_000_000_000),
            "日期不存在": make_record(date="2026-02-30"),
            "日期未补零": make_record(date="2026-11-7"),
            "类型不支持": make_record(type="transfer"),
            "类别带首尾空白": make_record(category=" 饮食 "),
            "类别为空": make_record(category=""),
            "类别超长": make_record(category="饮" * 21),
            "备注超长": make_record(note="备" * 201),
            "备注带首尾空白": make_record(note=" 午餐 "),
            "含有未知字段": {**make_record(), "foo": 1},
            "缺少备注字段": without("note"),
            "缺少 id 字段": without("id"),
        }
        for name, record in cases.items():
            with self.subTest(case=name):
                self.write_raw(json.dumps([record], ensure_ascii=False))
                with self.assertRaises(AppError) as caught:
                    storage.load_records()
                self.assertEqual(caught.exception.code, "STORAGE_ERROR")

    def test_load_returns_independent_objects(self):
        record = make_record()
        storage.save_records([record])

        first = storage.load_records()
        first[0]["amount"] = 999_999
        first.append(make_record())

        second = storage.load_records()
        self.assertEqual(second, [record])
        self.assertEqual(len(second), 1)


class SaveRecordsTests(DataFileTestCase):
    def test_validates_before_touching_file(self):
        original = make_record()
        storage.save_records([original])
        before = self.read_raw()

        broken = make_record(amount=0)
        with self.assertRaises(AppError) as caught:
            storage.save_records([original, broken])

        self.assertEqual(caught.exception.code, "STORAGE_ERROR")
        self.assertEqual(self.read_raw(), before)

    def test_rejects_non_list_payload(self):
        with self.assertRaises(AppError) as caught:
            storage.save_records({"records": []})
        self.assertEqual(caught.exception.code, "STORAGE_ERROR")
        self.assertFalse(self.data_file.exists())

    def test_rejects_duplicate_ids_without_writing(self):
        record = make_record()
        with self.assertRaises(AppError) as caught:
            storage.save_records([record, dict(record)])
        self.assertEqual(caught.exception.code, "STORAGE_ERROR")
        self.assertFalse(self.data_file.exists())

    def test_write_failure_keeps_old_file_and_cleans_temp(self):
        original = make_record()
        storage.save_records([original])
        before = self.read_raw()

        another = make_record(category="交通", amount=500)
        with patch("storage.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(AppError) as caught:
                storage.save_records([original, another])

        self.assertEqual(caught.exception.code, "STORAGE_ERROR")
        self.assertEqual(self.read_raw(), before)
        self.assertEqual(self.temp_files(), [])

    def test_does_not_leak_absolute_path_in_message(self):
        with patch("storage.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(AppError) as caught:
                storage.save_records([make_record()])
        message = caught.exception.message
        self.assertNotIn(str(self.temp_dir), message)
        self.assertNotIn(":\\", message)


class LockTests(DataFileTestCase):
    def test_records_lock_is_reentrant(self):
        """契约要求业务层在锁内完成读改写，因此锁必须可重入。"""
        with storage.records_lock:
            with storage.records_lock:
                storage.save_records([make_record()])
        self.assertEqual(len(storage.load_records()), 1)

    def test_concurrent_saves_do_not_lose_records(self):
        total = 12
        errors: list[BaseException] = []

        def worker():
            try:
                with storage.records_lock:
                    records = storage.load_records()
                    records.append(make_record())
                    storage.save_records(records)
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


if __name__ == "__main__":
    unittest.main()
