"""测试公共支撑：把数据文件重定向到临时目录，绝不碰真实账单。"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import storage
from errors import AppError


def storage_error():
    """Construct a simulated failure using only the public AppError contract."""
    return AppError(500, "STORAGE_ERROR", "账单数据读写失败")


class DataFileTestCase(unittest.TestCase):
    """每个用例独立的临时数据文件；结束自动清理。"""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="note-test-", dir=Path(__file__).resolve().parents[1]))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.data_file = self.temp_dir / "records.json"

        patcher = patch.object(storage, "DATA_FILE", self.data_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def read_raw(self) -> str:
        return self.data_file.read_text(encoding="utf-8")

def build_test_app():
    """用真实入口工厂构建测试客户端所属应用。"""
    from app import create_app

    app = create_app()
    app.testing = True
    return app
