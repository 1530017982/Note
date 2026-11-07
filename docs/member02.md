# Note · 个人记账本 —— 成员02 交付（记账业务 + 数据存储）

本目录是「Note · 个人记账本」的可运行工程根，按项目 `README.md`
第三、四节约定的**开发合同 v1** 实现。当前交付范围是**成员02（记账业务）**
与它依赖的**数据存储层**；5、6 号负责的前端文件尚未创建。

> 所有代码严格对齐合同字段与错误码，接口未做任何「我方自定义」的改动，
> 3—6 号可按下文《对接清单》直接接入。

---

## 一、目录与文件归属

```text
项目根/
├── app.py                    # 项目入口：创建应用、注册 Blueprint、注册错误处理器（对接基线，待1号接管）
├── errors.py                 # 公共异常 AppError + 统一 JSON 错误处理器（合同 §3.6，待1号接管）
├── storage.py                # 数据存储层：JSON 读写、校验、原子替换、进程内锁（合同 §3.8）★
├── records.py                # 成员02：新增/删除账单 + records_bp（合同 §3.2 §3.3）★
├── requirements.txt           # 运行依赖（仅 Flask；测试用标准库 unittest）
├── .gitignore                # 忽略真实账单数据与原子写入临时文件
├── data/
│   └── .gitkeep              # 数据目录占位；records.json 运行时生成且不提交
├── tests/                    # 55 个测试（见《四、验证》）
│   ├── support.py            #   测试基类：数据文件重定向到临时目录
│   ├── test_storage.py       #   存储层：初始化/校验/损坏保护/原子写/并发
│   ├── test_records.py       #   业务层：字段校验/新增/删除/路由错误码
│   └── test_note_contract.py #   对接 3 号 queries + 4 号 statistics 的契约与全链路测试
└── scripts/
    └── demo_records.py       # 现场演示：新增 → 落盘 → 删除 → 重启读取
```

★ = 成员02 交付的核心文件。其余三个（`app.py`、`errors.py`、`storage.py`）是
**成员02 运行所必需的依赖**，已按合同实现为「对接基线」：
接口签名与合同完全一致，1号 合并时可直接沿用或替换，2—4 号代码无需改动。
3 号 `queries.py` 与 4 号 `statistics_service.py` 已按同一契约接入并通过全链路测试。


---

## 二、交付内容

### 2.1 成员02：`records.py`（合同 §3.2、§3.3、§3.7）

| 对外接口 | 行为 |
| --- | --- |
| `create_record(payload: dict) -> dict` | 校验 → 生成 UUID4 → 加锁读改写 → 保存成功后返回完整记录 |
| `delete_record(record_id: str) -> dict` | 加锁读改写，返回 `{"id", "deleted": True}`；不存在抛 404 |
| `validate_payload(payload: dict) -> dict` | 单独暴露的请求校验入口，供录入端联调和测试复用 |
| `records_bp` | `POST /api/records`（201）、`DELETE /api/records/<id>`（200） |

请求字段与校验规则（金额全为**整数分**，字符长度按 Unicode 码点计）：

| 字段 | 规则 | 错误指向 |
| --- | --- | --- |
| `date` | 必填，严格 10 字符且真实存在的 `YYYY-MM-DD` | `date` |
| `type` | 必填，仅 `income` / `expense`（区分大小写） | `type` |
| `amount` | 必填，`1—999999999` 的整数；拒绝字符串、小数、布尔、负数 | `amount` |
| `category` | 必填，去首尾空白后 1—20 字符 | `category` |
| `note` | 可省略（默认 `""`），去首尾空白后 ≤200 字符 | `note` |
| `id` | **不得传入**，由服务端生成 | `id` |
| 其它字段 | 未知字段一律拒绝，帮助发现拼写错误 | 该字段名 |

补充约束：任何字段都不接受 `null`；同一内容允许记为多笔（不去重）；
校验顺序固定为 `date → type → amount → category → note`，保证同一份错误请求
每次返回同一个字段错误。

### 2.2 数据存储：`storage.py`（合同 §3.7、§3.8）

| 对外接口 | 行为 |
| --- | --- |
| `new_record_id() -> str` | 生成 UUID4 字符串 |
| `load_records() -> list[dict]` | 读取并校验完整数组，每次返回**独立对象**，保持插入顺序 |
| `save_records(records) -> None` | **先整体校验**再原子替换写盘；失败保留旧文件 |
| `records_lock` | 进程内共享 `RLock`，读、写都使用，业务层可在锁内完成读改写 |
| `is_valid_date/amount/...` | 一组纯函数校验器，业务层据此拼装面向用户的提示 |

落盘规则：

- 路径为 `data/records.json`，由 `Path(__file__).parent` 解析，**不依赖启动工作目录**；
- 文件不存在 → 初始化为 `[]`（独占创建，绝不覆盖别人刚写好的文件）；
- 已有空文件 / 损坏 JSON / 非数组 / 重复 id / 非法记录 → `500 STORAGE_ERROR`，
  **原文件原样保留**，不静默覆盖；
- UTF-8 读写、`ensure_ascii=False`（中文在文件里可读）、`indent=2`；
- 先写同目录临时文件 → `flush + fsync` → `os.replace` 原子替换，失败清理临时文件并保留旧文件；
- 读、写都在 `records_lock` 内，新增/删除的「读取 → 修改 → 保存」全过程加锁。

---

## 三、对接清单（给 3—6 号）

| 对接方 | 怎么接 | 现状 |
| --- | --- | --- |
| 1号 入口 | `app.py` 已建 `create_app()`，按注释追加 `queries_bp`、`stats_bp`、`GET /` 即可 | 可原样接管 |
| 3号 查询 | `from storage import load_records`；函数返回的列表可直接筛选，**不要原地重排**；`parse_query` 抛 `AppError` 即可 | 待交付 |
| 4号 统计 | `statistics_service.get_statistics()` 直接 `from storage import load_records` + `queries.filter_records`，无需改动 | **已实测通过** |
| 5号 录入 | `POST /api/records`，`Content-Type: application/json`；`amount` 按「元」输入、整数分提交（字符串拆分换算，不要浮点乘 100）；成功后 `document.dispatchEvent(new CustomEvent("records-changed", { detail: { action: "created", id } }))` | 待交付 |
| 6号 列表 | `DELETE /api/records/<id>`；失败时读 `error` 直接展示，按 `code` 判断分支；删除成功后触发 `action: "deleted"` 事件 | 待交付 |

错误码（合同 §3.6，本模块实际会用到的部分）：

| HTTP | code | 场景 |
| --- | --- | --- |
| 400 | `INVALID_JSON` | JSON 语法错误，或请求体不是对象 |
| 400 | `VALIDATION_ERROR` | 必填缺失、取值非法、未知字段，附 `field` |
| 404 | `RECORD_NOT_FOUND` | 指定 id 不存在（含重复删除、id 格式不匹配） |
| 404 | `NOT_FOUND` | 未知 API 路径 |
| 405 | `METHOD_NOT_ALLOWED` | 路径存在但方法不支持（如 3号 未交付时的 `GET /api/records`） |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | POST 未使用 `application/json` |
| 500 | `STORAGE_ERROR` | 读写失败、JSON 损坏、已有记录格式不合法 |
| 500 | `INTERNAL_ERROR` | 其它未处理异常（细节只进服务端日志） |

`/api/*` 返回 JSON 错误体；页面与静态资源的 404/405 保留 Flask 默认 HTML，
不影响 5、6 号前端调试。

---

## 四、验证

```bash
# 全部测试（标准库 unittest，无需额外依赖）
python -m unittest discover -s tests -t .        # Ran 55 tests ... OK

# 现场演示：新增 → 校验拒绝 → 落盘 → 删除 → 重复删除
python scripts/demo_records.py

# 关键一步：新起进程只读，证明重启后仍能读出账单（合同 §3.8）
python scripts/demo_records.py --read-only

# 启动服务
python app.py                                     # http://127.0.0.1:5000
```

已执行的验证与结果：

| 验证项 | 证据 |
| --- | --- |
| 合同 §3.10 步骤 2—4：收入 100.00、支出 12.50 → 结余 87.50 | `tests/test_note_contract.py` 直接驱动 4 号 `statistics_service.py`，数值一致 |
| 合同 §3.10 步骤 6：只看「饮食」→ 收入 0、结余 -1250 | 同上 |
| 合同 §3.10 步骤 1—8：三 Blueprint 协同 | `EndToEndApiTests` 把 `records_bp` + `queries_bp` + `stats_bp` 挂同一应用跑通 |
| 合同 §3.10 步骤 9/10：`12.5`、`"1250"`、`true`、`2026-02-30` 均 400 | `tests/test_records.py` + 演示脚本输出 |
| 合同 §3.10 步骤 12：删除 200，再删同一 id → 404 | 同上 |
| 合同 §3.10 步骤 13：重启后数据仍可读 | 真实**双进程**验证：`demo_records.py` 写入 → 新进程 `--read-only` 读出 |
| 损坏文件不被静默覆盖 | 空文件 / 坏 JSON / 非数组 / 重复 id / 非法记录 均报 STORAGE_ERROR 且文件内容不变 |
| 写盘失败保留旧文件 | mock `os.replace` 抛 `OSError` → 500 + 旧文件不变 + 临时文件已清理 |
| 并发新增不丢数据 | 10 线程并发 POST → 文件 10 条、id 全不相同 |
| 真实 HTTP 服务可用 | `python app.py` 后 POST 201 / DELETE 200 / 重复 DELETE 404 |

---

## 五、参考 CoinTrack 的取舍

CoinTrack（`../.reference/CoinTrack-main`）与本项目同为 Python + Flask，
它的 `helpers.py` 就是把数据访问从路由里抽出来单独成层，本实现沿用了这个分层思路，
但**没有沿用它的存储方式**，原因如下：

| CoinTrack `helpers.py` | 问题 | 本项目的做法 |
| --- | --- | --- |
| 异常 `print` 后 `return False` | 故障被吞成假值，调用方继续跑，问题被静默掩盖 | 统一抛 `AppError(500, STORAGE_ERROR)`，前端有明确提示 |
| SQL 用 f-string 拼接查询条件 | 类别、年份直接拼进 SQL，存在注入面 | 本项目按合同用本地 JSON，根本不过 SQL；筛选在 Python 侧做 |
| 金额用 `NUMERIC` 存浮点 | 浮点误差（0.1+0.2）会污染账目 | 全链路**整数分**，前端展示时再除以 100 |
| `INSERT` 直接落盘 | 无事务，中途失败留下半份数据 | 先整体校验 + 临时文件 + `os.replace` 原子替换 |
| 依赖 `../Database/...` 相对路径 | 换个工作目录就找不到库 | 由 `Path(__file__)` 解析绝对路径 |
| 全局可变状态 `ledger_totals` | 多用户/多请求互相污染 | 数据无进程内缓存，每次从磁盘读快照 |

合同明确「使用本地 JSON」且第一版只单进程本地运行，因此本项目**不引入 SQLite**；
CoinTrack 的分层、命名与「先抽存储再写业务」的工程顺序被保留下来。

---

## 六、已知限制

- `records_lock` 只在单进程内有效；多服务进程同时写同一文件不受保护（合同第一版范围内）。
- 没有登录、多账户、编辑记录与分页；接口未做鉴权（合同第一版范围内）。
- `GET /api/records` 目前返回 405，等 3号 `queries.py` 交付后由 `queries_bp` 接管。
- `expense` 的分类汇总在 4号 `by_category` 里同时给出 `income/expense` 两个键，
  图表的零值跳过由 6号 前端处理。

---

## 七、关键代码说明（博客材料，成员02）

1. **`create_record()` 的顺序就是合同本身**：先 `validate_payload()` 再 `new_record_id()`，
   最后在 `records_lock` 内 `load_records() → append → save_records()`。
   顺序不可交换——先落盘后校验会写出脏数据，先返回后落盘会「提示成功但没存上」。
2. **`bool` 是 `int` 的子类**：`is_valid_amount()` 里必须显式 `isinstance(value, bool)` 先行排除，
   否则 `amount=True` 会被当成 1 分悄悄入库。这是本项目单测里专门覆盖的一条。
3. **RLock 而不是 Lock**：业务层在锁内调用 `load_records()` / `save_records()`，
   它们内部还要再取同一把锁，普通 `Lock` 会自锁死。选 `RLock` 才能既满足
   「每次读、写均使用锁」，又让业务层覆盖整个读改写过程。
4. **先整体校验、再动文件**：`save_records()` 在写盘前把每条记录都校验完，
   任何一条不合法都不会产生半份新数据；写盘用临时文件 + `os.replace`，
   `os.replace` 在 Windows/POSIX 上都是原子替换，失败时旧文件完好。
5. **区分「文件不存在」和「空文件」**：前者是首次启动，初始化成 `[]`；
   后者是损坏（例如某次写入被中断），必须报错而不是当成空账本——
   否则用户会以为账本丢了，下一次保存还会把损坏文件覆盖掉。
