# Note · 个人记账本

软件工程现场编程项目，用于记录日常收入与支出、查看账单并进行收支统计。

> 当前状态：开发计划与六人任务分配。以下目录、接口及功能为约定方案，尚未实现；运行说明、截图和演示视频在联调完成后补充。
> 成员按1—6号认领任务；已填写的信息予以保留，其余姓名、学号及GitHub账号请各成员补充。

## 一、项目目标与技术方案

- 基础记账：记录日期、金额、收支类型、类别及备注。
- 数据保存：使用本地 JSON 文件，重启程序后数据仍可读取。
- 查看记录：展示最近账单，并支持日期、类别、金额和收支类型筛选。
- 收支统计：按筛选条件计算总收入、总支出、结余，并按类别、月份汇总。
- 用户界面：采用本地 Web 页面，提供录入表单、账单列表和统计看板。
- 可选加分项：分类支出图、月度收支图；先保证基础功能可演示。

建议技术栈：Python 3.10+、Flask、HTML/CSS、原生 JavaScript、本地 JSON。图表可使用 Chart.js；如使用，应将依赖保存在本地，方便离线演示。

## 二、六人任务分配

每人必须独立完成一个实际代码模块，并使用本人 GitHub 账号提交。博客、测试、录视频是附加职责，不能替代代码模块。

| 成员 | 独立负责模块 | 具体开发任务 | 负责文件（计划） | 验收标准 | 附加职责 |
| --- | --- | --- | --- | --- | --- |
| 1号（组长） | 数据存储与项目入口 | 搭建 Flask 入口；实现 JSON 初始化、读取、保存、唯一 ID；处理空文件和损坏文件，避免静默覆盖；整合路由 | `app.py`、`storage.py`、`errors.py`、`requirements.txt`、`.gitignore` | 首次启动可初始化；新增后重启仍可读取；损坏数据有明确提示 | 维护运行说明，组织联调，发布 Release，核查提交链接 |
| 2号 | 记账业务 | 实现新增收入/支出、删除记录；校验日期、金额、类型、类别和备注；调用存储模块保存 | `records.py` | 合法记录可保存；非法日期、非正金额和超过两位小数被拒绝；删除不存在记录返回明确错误 | 整理记账关键代码及注释，协助录入端联调 |
| 3号 | 查询与筛选 | 实现最近 N 条记录；按日期区间、类别、类型、金额区间筛选；日期倒序排列；供统计模块复用筛选逻辑 | `queries.py` | 默认返回最近记录；多个条件可组合；边界日期和金额可正确命中；无结果返回空列表 | 整理查询关键代码，记录筛选联调中的真实问题 |
| 4号 | 统计计算 | 基于筛选结果计算总收入、总支出、结余；按类别、月份汇总；提供图表所需数据 | `statistics_service.py` | 与人工核算一致；无数据返回零值及空汇总；统计结果与同条件列表一致 | 整理统计关键代码、计算规则及功能亮点 |
| 5号 | 页面框架与录入界面 | 编写主页面、整体样式和录入表单；收入/支出切换；默认日期；输入提示；提交成功后通知其他视图刷新 | `templates/index.html`、`static/css/main.css`、`static/js/entry.js` | 页面可正常打开；手机宽度基本可用；可完成收入/支出录入；失败显示原因；成功后列表和统计更新 | 整理录入截图、页面操作说明与博客版式 |
| 6号 | 账单列表与统计展示 | 编写最近记录列表、组合筛选、删除确认；收入/支出/结余卡片；对接分类及月度图表；处理加载、空数据和请求失败状态 | `static/js/list.js`、`static/js/dashboard.js`、`static/css/views.css` | 列表与筛选正常；删除后刷新；统计卡片与后端一致；基础功能完成后补图表 | 录制演示视频，整理列表/统计截图与演示流程 |

### 成员信息（认领后填写）

| 编号 | 姓名 | 学号 | GitHub 账号 |
| --- | --- | --- | --- |
| 1号 | 包学丰 | 102401434 | tw1l1ghtcc |
| 2号 | 冯玄 | 102401436 | otto2-5-8 |
| 3号 | 秦文贵 | 102401615 | vg666-NiKo |
| 4号 | 乔震宇 | 102401435 | 1530017982 |
| 5号 | 吴圣洲 | 102401622 | drkalerq |
| 6号 | 郑瀚 | 102401111 | Kerical |

## 三、完整接口与模块对接约定（开发合同 v1）

本节为六人共同遵守的实现约定，尚未代表接口已实现或通过测试。修改字段、函数或事件前，先与调用方确认，并同步本节。

### 3.1 通用规则与数据模型

- 计划本地地址：`http://127.0.0.1:5000`；页面与 API 同源，通过相对路径调用，无需跨域配置。
- `GET /` 返回 HTML；`/static/...` 提供静态资源。以下 `/api/*` 接口返回 UTF-8 JSON。
- POST 请求使用 `Content-Type: application/json`。成功体含 `data`；错误体统一含 `error`、`code`，字段校验错误额外含 `field`。
- 日期为真实的 `YYYY-MM-DD`，允许补记历史及未来日期；“今天”由浏览器本地年月日生成，避免 UTC 日期偏移。
- 所有 API、JSON 文件中的金额都使用整数“分”，前端输入、展示为“元”，显示两位小数。
- 第一版不含登录、多账户、编辑记录及分页；需要完整列表时使用下文 `limit=all`。
- 类别采用非空自由文本，可给出“饮食、交通、购物、工资、其他”快捷选项，无需额外类别接口。

单条记录固定包含以下六个字段：

```json
{
  "id": "7fb7d372-9bd9-4bd6-a3cb-c9de6079893a",
  "date": "2026-11-07",
  "type": "expense",
  "amount": 1250,
  "category": "饮食",
  "note": "午餐"
}
```

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| id | string | 服务端生成 UUID4 字符串，全局唯一，客户端新增时不得传入 |
| date | string | 必填，严格为10字符的真实日期 |
| type | string | 必填，仅 `income` 或 `expense` |
| amount | integer | 必填，范围1—999999999分；不接受字符串、小数、布尔值或负数 |
| category | string | 必填，去首尾空白后1—20个字符，区分大小写并精确匹配 |
| note | string | 可省略，默认空字符串；去首尾空白后最多200个字符 |

字符长度按 Unicode 码点计算；后端为最终校验依据。任何字段均不接受 null。POST 出现未知字段时返回400，帮助发现拼写错误。

### 3.2 新增记录：POST /api/records（2号）

请求示例：

```json
{
  "date": "2026-11-07",
  "type": "expense",
  "amount": 1250,
  "category": "饮食",
  "note": "午餐"
}
```

成功返回 **201 Created**，`data` 是完整的已保存记录：

```json
{
  "data": {
    "id": "7fb7d372-9bd9-4bd6-a3cb-c9de6079893a",
    "date": "2026-11-07",
    "type": "expense",
    "amount": 1250,
    "category": "饮食",
    "note": "午餐"
  }
}
```

- 先校验，再生成 ID，保存成功后才响应201。
- 必填字段缺失或字段不合法返回400；Content-Type不支持返回415；存储失败返回500。
- 相同内容允许记为多笔；前端提交期间禁用提交按钮，减少重复点击。

### 3.3 删除记录：DELETE /api/records/<id>（2号）

示例：`DELETE /api/records/7fb7d372-9bd9-4bd6-a3cb-c9de6079893a`。无请求体。

成功返回 **200 OK**：

```json
{
  "data": {
    "id": "7fb7d372-9bd9-4bd6-a3cb-c9de6079893a",
    "deleted": true
  }
}
```

未找到该 ID（包括重复删除或格式不匹配）返回404，不修改文件。删除必须保存成功后才返回成功。

### 3.4 列表与筛选：GET /api/records（3号）

示例：

```text
/api/records
/api/records?limit=all
/api/records?start_date=2026-11-01&end_date=2026-11-30&type=expense&category=饮食&min_amount=100&max_amount=5000&limit=10
```

前端必须使用 `URLSearchParams` 编码参数，包括中文类别。

| 参数 | 类型/取值 | 默认值与规则 |
| --- | --- | --- |
| start_date | YYYY-MM-DD | 无下限，包含当天 |
| end_date | YYYY-MM-DD | 无上限，包含当天 |
| type | income / expense | 不限收支类型 |
| category | string | 去首尾空白后精确匹配，不限类别 |
| min_amount | 非负整数字符串 | 无金额下限，单位分 |
| max_amount | 非负整数字符串 | 无金额上限，单位分 |
| limit | 1—100的整数字符串或 all | 默认10；all表示返回全部匹配记录 |

- 可选参数为空字符串或仅空白时视为未传。非空参数先去首尾空白。
- 金额参数范围为0—999999999，不接受小数或正负号；实际记录金额仍须大于0。
- 所有筛选条件按 AND 组合；先筛选，再排序，最后截取条数。
- 日期倒序；同一天按存储数组中的位置倒序，即后追加记录优先。第一版没有额外创建时间字段。
- 开始日期晚于结束日期、最小金额大于最大金额、非法日期、未知参数、重复同名参数、非法 limit 均返回400。
- 有效但未命中的类别正常返回空数组，不报错。

成功返回 **200 OK**：

```json
{
  "data": [
    {
      "id": "7fb7d372-9bd9-4bd6-a3cb-c9de6079893a",
      "date": "2026-11-07",
      "type": "expense",
      "amount": 1250,
      "category": "饮食",
      "note": "午餐"
    }
  ],
  "meta": {
    "total": 1,
    "returned": 1,
    "limit": 10
  }
}
```

`total` 为截取前匹配总数；`returned` 为实际返回条数；`limit` 为整数或字符串 `"all"`。无记录时 `data: []`，两个计数均为0。

### 3.5 收支统计：GET /api/stats（4号）

接受与列表相同的六个筛选参数：日期起止、类型、类别、金额起止；校验规则相同。**不接受 limit 参数**，统计全部符合条件的记录。前端构造统计请求时须去掉列表的 limit。

示例：`/api/stats?start_date=2026-11-01&end_date=2026-11-30`。

假设匹配到工资收入100.00元、饮食支出12.50元，成功返回 **200 OK**：

```json
{
  "data": {
    "income": 10000,
    "expense": 1250,
    "balance": 8750,
    "count": 2,
    "by_category": [
      {"category": "工资", "income": 10000, "expense": 0},
      {"category": "饮食", "income": 0, "expense": 1250}
    ],
    "by_month": [
      {"month": "2026-11", "income": 10000, "expense": 1250}
    ]
  }
}
```

- `balance = income - expense`，可为负数；`count` 为匹配记录数。
- 分类汇总按类别 Unicode 字典序升序；月份按 YYYY-MM 升序。
- 仅输出有匹配记录的类别及月份，不自动补齐无数据月份。
- 所有汇总都在筛选后计算。选择 type=expense 时收入为0，结余为负支出；看板需明确提示统计跟随当前筛选。
- 分类支出图读取 `by_category[].expense`，绘制时跳过零值；月度图读取 `by_month`。
- 无匹配记录时：income、expense、balance、count均为0，两个汇总数组均为空。

### 3.6 统一错误响应（1号定义，2—4号使用）

字段校验错误示例：

```json
{
  "error": "金额必须为1—999999999之间的整数分",
  "code": "VALIDATION_ERROR",
  "field": "amount"
}
```

| HTTP状态 | code | 使用场景 |
| --- | --- | --- |
| 400 | INVALID_JSON | JSON语法错误或请求体不是对象 |
| 400 | VALIDATION_ERROR | 必填字段缺失、字段值错误、未知字段/参数、重复参数、区间冲突 |
| 404 | RECORD_NOT_FOUND | 指定记录不存在 |
| 404 | NOT_FOUND | 未知API路径 |
| 405 | METHOD_NOT_ALLOWED | API路径存在但HTTP方法不支持 |
| 415 | UNSUPPORTED_MEDIA_TYPE | POST没有使用 application/json |
| 500 | STORAGE_ERROR | 读写失败、JSON文件损坏、已有记录格式不合法 |
| 500 | INTERNAL_ERROR | 其他未处理异常 |

`error` 必须可直接展示给用户，`code` 供程序判断。字段错误给出 `field`，例如 `start_date`；范围冲突指向 `end_date` 或 `max_amount`。非字段错误省略 `field`。不向前端暴露堆栈和本地绝对路径。

1号在 `errors.py` 定义公共异常：
`AppError(status: int, code: str, message: str, field: str | None = None)`，
并在 Flask 注册 JSON 错误处理器；业务模块抛出该异常，入口统一序列化。

### 3.7 Python模块边界与函数签名

以下为签名约定，不是已实现代码。记录用 `dict`，筛选条件用已校验的 `dict`，避免额外框架依赖。

| 文件/负责人 | 对外接口 | 行为 |
| --- | --- | --- |
| storage.py / 1号 | `new_record_id() -> str` | 生成UUID4，供2号使用 |
| storage.py / 1号 | `load_records() -> list[dict]` | 读取并验证完整记录数组，每次返回独立对象 |
| storage.py / 1号 | `save_records(records: list[dict]) -> None` | 验证后保存，失败抛STORAGE_ERROR |
| storage.py / 1号 | `records_lock` | 进程内共享RLock；每次读、写均使用，新增和删除须覆盖整个读改写过程 |
| records.py / 2号 | `create_record(payload: dict) -> dict` | 校验、加锁读改写，返回完整新记录 |
| records.py / 2号 | `delete_record(record_id: str) -> dict` | 加锁读改写，返回id/deleted对象；不存在抛404 |
| queries.py / 3号 | `parse_query(args, *, allow_limit: bool) -> tuple[dict, int | str | None]` | 接收Flask request.args，校验参数和重复键；返回规范化筛选字典及limit；统计时allow_limit=False且返回None |
| queries.py / 3号 | `filter_records(records: list[dict], filters: dict) -> list[dict]` | 返回全部匹配项，不截断，不修改原数组 |
| queries.py / 3号 | `query_records(filters: dict, limit: int | str = 10) -> dict` | 读取、筛选、排序、截取，返回data/meta结构 |
| statistics_service.py / 4号 | `summarize_records(records: list[dict]) -> dict` | 纯汇总，返回income/expense/balance/count及两个汇总数组 |
| statistics_service.py / 4号 | `get_statistics(filters: dict) -> dict` | 读取一次快照，调用filter_records及summarize_records，返回统计对象 |

规范化筛选字典固定包含六个键：`start_date`、`end_date`、`type`、`category`、`min_amount`、`max_amount`。未指定值为None；日期仍为标准字符串，金额转为整数。limit单独返回，不放入该字典。

路由归属：
- 1号在 `app.py` 创建应用、注册 `records_bp`、`queries_bp`、`stats_bp`，处理主页面及公共异常。
- 2号在 `records.py` 导出 `records_bp`，实现POST和DELETE路由。
- 3号在 `queries.py` 导出 `queries_bp`，实现GET列表路由。
- 4号在 `statistics_service.py` 导出 `stats_bp`，实现GET统计路由。
- Blueprint 路径直接写完整 `/api/...`，注册时不再加 url_prefix。
- 路由负责解析HTTP及包装响应；查询函数已返回data/meta，不重复包data；新增、删除、统计函数的返回对象由路由包入data。
- 依赖方向：app → 各Blueprint；records → storage/errors；statistics_service → queries/storage；queries → storage/errors；storage → errors。业务模块不得导入app，避免循环导入。

### 3.8 本地文件保存约定（1号、2号）

- 使用项目根目录下 `data/records.json`，由代码文件位置解析绝对路径，不能依赖启动工作目录。
- 文件不存在时初始化为 `[]`；已有空文件、损坏JSON、非数组内容、重复ID或非法记录均报STORAGE_ERROR，保留原文件。
- 数据按插入顺序存放，新记录追加到末尾；查询不能原地重排存储数据。
- UTF-8读写，中文保持可读。先写同目录临时文件再原子替换；保存失败保留旧文件并返回错误。
- 新增/删除用同一把records_lock覆盖“读取→修改→保存”。第一版仅单服务进程本地运行；进程内锁不支持多个服务进程同时写同一文件。
- 实际账单文件与临时文件加入.gitignore；演示数据使用虚构信息。

### 3.9 前端DOM、脚本与事件约定（5号、6号）

5号提供以下容器，6号在其中渲染内容：

| ID | 元素/用途 | 负责人 |
| --- | --- | --- |
| record-form | form，新增记录表单 | 5号 |
| record-message | div，录入结果提示，设置aria-live | 5号 |
| filter-panel | div，6号挂载筛选控件 | 5号提供容器，6号实现内容 |
| record-list | div，6号渲染表格或空状态 | 同上 |
| list-message | div，列表加载及错误提示 | 同上 |
| stats-panel | div，6号挂载汇总卡片与筛选说明 | 同上 |
| stats-message | div，统计加载及错误提示 | 同上 |
| category-chart | canvas，分类支出图，可选 | 同上 |
| monthly-chart | canvas，月度收支图，可选 | 同上 |

- 表单name统一为date、type、amount、category、note。amount输入为元文本；5号校验最多两位小数，以字符串拆分换算为整数分，不能直接浮点乘100取整。
- 所有脚本采用ES module。主页面仅载入 `<script type="module" src="/static/js/entry.js"></script>` 和 `<script type="module" src="/static/js/list.js"></script>`。
- list.js导入dashboard.js的 `refreshDashboard(filters)`，dashboard.js不在HTML中重复载入，不自行初始化请求。
- dashboard.js导出 `async function refreshDashboard(filters)`；filters为六个可选查询键，缺失或空值不发送，金额为整数分；函数负责加载及错误展示。
- list.js维护唯一筛选状态；初次加载、筛选提交/重置、收到records-changed事件时，同时刷新列表与看板。列表的limit单独保存，不传给统计。
- 新增成功后5号在document上触发 `new CustomEvent("records-changed", { detail: { action: "created", id } })`。
- 删除成功后6号同样触发该事件，action为deleted；刷新保持当前筛选条件，并只通过事件触发一次。
- 切换筛选过快时，列表和统计各自通过AbortController或请求序号防止旧响应覆盖新结果。
- 请求失败保留已填写表单并显示后端error；禁止显示“保存成功”后才写文件。
- 类别、备注等用户内容使用textContent渲染，避免直接拼接到innerHTML。
- 图表无数据时显示提示；每次更新复用或销毁旧实例，避免重复绘制。

### 3.10 联调样例与预期结果

在空数据文件下执行以下场景，由各模块负责人共同核对；这里列的是预期，不表示已经通过：

| 步骤 | 操作 | 预期 |
| --- | --- | --- |
| 1 | GET /api/records | 200，data=[]，total=0 |
| 2 | POST：2026-11-07，income，10000，工资 | 201，返回id |
| 3 | POST：2026-11-07，expense，1250，饮食 | 201，返回另一个id |
| 4 | GET /api/stats | income=10000，expense=1250，balance=8750，count=2 |
| 5 | GET /api/records?type=expense&min_amount=1250&max_amount=1250 | 恰好返回饮食记录，验证金额端点包含 |
| 6 | GET /api/stats?category=饮食 | income=0，expense=1250，balance=-1250，count=1 |
| 7 | GET /api/records?limit=1 | total=2，returned=1，返回后新增的同日支出 |
| 8 | GET /api/stats?limit=1 | 400，VALIDATION_ERROR，field=limit |
| 9 | POST amount=12.5、"1250"或true | 均400，field=amount，数据不增加 |
| 10 | POST date=2026-02-30 | 400，field=date |
| 11 | GET列表，start_date晚于end_date | 400，field=end_date |
| 12 | DELETE饮食记录，再次DELETE同一ID | 先200，再404 RECORD_NOT_FOUND |
| 13 | 重启后GET统计 | 工资收入仍在，expense=0，balance=10000 |
| 14 | 无匹配条件请求列表及统计 | 列表为空，汇总金额/计数均0，汇总数组为空 |


## 四、GitHub 协作规范

1. 本仓库专用于本次现场编程；组长将其他成员添加为协作者。
2. 每人建立自己的功能分支，例如 `feature/storage`、`feature/records`、`feature/query`、`feature/stats`、`feature/entry-ui`、`feature/dashboard`。
3. 各成员独立编写并提交本人模块，提交信息说明实际变更，例如 `feat: 新增按日期区间筛选账单`。不伪造作者、不由他人代替完成个人模块。
4. 每个模块通过 Pull Request 合入 `main`，描述功能、验证结果及依赖；合并时保留各成员的真实提交记录。
5. 公共接口、页面容器和数据格式先确认再开发；优先修改自己负责的文件，避免同时改动公共文件。
6. 每人提交模块关键代码说明和本人编程体验；截图、讨论及复审事件据实记录。
7. 文档中的任务分配提交不作为六位成员的模块开发成果。

## 五、开发与交付时间

以下均为 2026 年 11 月 7 日北京时间。若启动较晚，应压缩开发阶段，优先完成基础功能和联调。

| 时间 | 安排 |
| --- | --- |
| 14:00—14:20 | 六人认领任务；确认数据格式、接口及页面容器；搭建项目骨架 |
| 14:20—15:30 | 各自开发模块并提交；接口先用简单样例对接 |
| 15:30—16:15 | 合并联调，跑通录入→查看→筛选→统计→重启读取 |
| 16:15—16:45 | 修复问题；准备演示数据、截图和视频；有余力再完善图表 |
| 16:45—17:00 | 查看公布的演示要求；发布可运行的 Release；核查并提交 GitHub 链接 |
| 17:00—17:15 | 按课程安排进行现场演示 |
| 演示后—23:00前 | 完成博客并提交；同时核查 GitHub 与博客链接可访问 |

## 六、联调验收清单

- [ ] 可新增收入与支出，包含日期、金额、类别和备注。
- [ ] 无效金额、无效日期及缺少必填字段均有明确提示。
- [ ] 最近记录按日期倒序显示。
- [ ] 日期、类别、类型及金额筛选可组合使用。
- [ ] 同条件列表与收支统计一致，空数据状态正常。
- [ ] 记入 100.00 元收入和 12.50 元支出后，结余为 87.50 元。
- [ ] 删除记录后，列表与统计同步更新。
- [ ] 重启服务后，JSON 中的数据仍可正常读取。
- [ ] 依照补充后的运行说明，在另一台组员电脑上完成启动验证。
- [ ] Release 包含可运行代码与运行说明，仓库及博客链接可访问。

## 七、博客材料分工与提交要求

博客开头按课程要求填写：

| 项目 | 内容 |
| --- | --- |
| 作业所属课程 | 班级链接，待填写 |
| 作业要求 | 本次作业要求链接，待填写 |
| 作业的目标 | 实现个人记账本，练习模块设计、GitHub 协作与现场交付 |
| 团队名称 | 待填写 |
| 团队成员名字-学号 | 六位成员分别填写 |

- 1号：汇总职责分工、运行环境、仓库地址、Release 地址及真实 commit 记录。
- 2—4号：各提供本人模块关键函数片段与注释，并提出有事实依据的实现亮点。
- 5号：汇总录入截图、操作说明与博客排版。
- 6号：汇总账单和统计截图，录制软件操作视频。
- 全体：每人撰写本人团队编程体验；共同选取至少3项真实发生、耗时较长且有收获的编码、讨论或复审事件，说明问题、处理过程及收获。
- 全体：据实际实现选取1—3项亮点，不将计划功能写成已完成成果。
- 组长：按实际贡献评分，满足“个人分数总和＝小组分数×6，六人分数不能完全相同”的要求。

## 八、运行说明与演示材料

待实现及联调后补充：依赖安装命令、启动命令、访问地址、数据文件位置、软件截图、视频链接、Release 链接及团队博客链接。
