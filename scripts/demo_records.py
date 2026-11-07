"""成员02 现场演示脚本：新增 → 落盘 → 删除 → 重启读取。

全程走真实 Flask 路由（含公共错误处理器），只把数据文件重定向到系统临时目录，
不污染仓库里的 ``data/records.json``。

用法（在 note-app 目录下执行）::

    python scripts/demo_records.py                 # 第一次运行：新增两笔并演示校验/删除
    python scripts/demo_records.py --read-only     # 新起进程：证明重启后仍能读取
    python scripts/demo_records.py --data-file D:\\tmp\\demo.json   # 指定数据文件

对应项目 README §3.10 的联调样例步骤 2、3、9、10、12。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

# 允许直接以脚本方式运行：把项目根（note-app）加入模块搜索路径。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import storage  # noqa: E402  - 必须在 sys.path 调整之后导入


DEFAULT_DATA_FILE = Path(tempfile.gettempdir()) / "note-demo" / "records.json"

INCOME = {
    "date": "2026-11-07",
    "type": "income",
    "amount": 10000,
    "category": "工资",
    "note": "",
}
EXPENSE = {
    "date": "2026-11-07",
    "type": "expense",
    "amount": 1250,
    "category": "饮食",
    "note": "午餐",
}


def show(title: str) -> None:
    print(f"\n=== {title} ===")


def show_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def show_response(label: str, response) -> None:
    print(f"{label} -> HTTP {response.status_code}")
    show_json(response.get_json())


def print_file(data_file: Path) -> None:
    show(f"数据文件内容：{data_file}")
    if data_file.exists():
        print(data_file.read_text(encoding="utf-8").rstrip())
    else:
        print("（文件尚不存在）")


def run_read_only(data_file: Path) -> int:
    """模拟「重启程序后读取」：本进程从未写过数据，只从磁盘读。"""
    show(f"只读模式：从磁盘读取 {data_file}")
    try:
        records = storage.load_records()
    except Exception as exc:  # noqa: BLE001 - 演示脚本需要直接展示错误
        print(f"读取失败：{exc}")
        return 1
    print(f"读到 {len(records)} 条记录：")
    show_json(records)
    if records:
        print("\n结论：程序重启后仍能从本地 JSON 读出账单（README §3.8）。")
    return 0


def run_demo(data_file: Path) -> int:
    from app import create_app  # 延迟导入：确保 storage.DATA_FILE 已重定向

    client = create_app().test_client()

    show(f"演示用数据文件：{data_file}")
    print_file(data_file)

    show("步骤 2：新增收入 100.00 元（工资）")
    income = client.post("/api/records", json=INCOME)
    show_response("POST /api/records", income)

    show("步骤 3：新增支出 12.50 元（饮食）")
    expense = client.post("/api/records", json=EXPENSE)
    show_response("POST /api/records", expense)
    expense_id = expense.get_json()["data"]["id"]

    show("步骤 9：金额 12.5（小数）应被拒绝")
    show_response(
        "POST /api/records", client.post("/api/records", json={**EXPENSE, "amount": 12.5})
    )

    show("步骤 10：日期 2026-02-30 应被拒绝")
    show_response(
        "POST /api/records", client.post("/api/records", json={**EXPENSE, "date": "2026-02-30"})
    )

    show("步骤 9 补充：金额用字符串 \"1250\" 也应被拒绝")
    show_response(
        "POST /api/records", client.post("/api/records", json={**EXPENSE, "amount": "1250"})
    )

    print_file(data_file)

    show("步骤 12：删除「饮食」，再重复删除同一个 id")
    show_response(f"DELETE /api/records/{expense_id}", client.delete(f"/api/records/{expense_id}"))
    show_response(f"DELETE /api/records/{expense_id}", client.delete(f"/api/records/{expense_id}"))

    print_file(data_file)

    show("当前存储层快照（3、4 号模块读到的就是这个列表）")
    show_json(storage.load_records())

    print(
        "\n下一步：新起一个进程执行 `python scripts/demo_records.py --read-only "
        f"--data-file {data_file}`，验证重启后读取。"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="成员02 记账业务演示")
    parser.add_argument(
        "--data-file",
        type=Path,
        default=DEFAULT_DATA_FILE,
        help=f"演示用数据文件（默认 {DEFAULT_DATA_FILE}）",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="只读模式：不新增也不删除，只验证重启后能否读出既有数据",
    )
    args = parser.parse_args()

    data_file = args.data_file.resolve()
    # 两种模式都必须先把数据文件指向演示路径，绝不能读写仓库里的真实账单。
    storage.DATA_FILE = data_file

    if args.read_only:
        return run_read_only(data_file)
    return run_demo(data_file)


if __name__ == "__main__":
    raise SystemExit(main())
