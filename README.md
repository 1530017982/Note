# Note · 个人记账本

Note 是一个本地运行的网页版个人记账本，支持收入与支出录入、账单筛选、收支统计和图表展示。账单保存在本地 JSON 文件中，关闭程序后重新启动仍可读取。

## 功能

| 功能 | 说明 |
| --- | --- |
| 记录收支 | 填写日期、金额、类别和备注，记录收入或支出 |
| 分类选择 | 收入与支出使用不同类别，切换类型时自动更新选项 |
| 查看账单 | 按日期倒序显示全部匹配记录，同一天后新增的记录优先显示 |
| 组合筛选 | 支持日期范围、收支类型、类别及最低/最高金额组合查询 |
| 删除记录 | 确认后删除账单，列表与统计同步更新 |
| 收支统计 | 展示筛选范围内的总收入、总支出和结余 |
| 图表展示 | 分类支出占比图、月度收入与支出对比图 |
| 本地保存 | JSON 文件持久化，校验数据后通过临时文件原子替换保存 |
| 界面适配 | 支持桌面与手机布局，账单在固定高度的显示框内滚动 |
| 输入提示 | 对非法金额、错误日期、缺少必填项和请求失败显示提示 |

类别设置：

- **收入**：工资、其他。
- **支出**：饮食、交通、购物、住房、其他。

录入和筛选时的金额单位为“元”，最多两位小数；接口与文件中统一使用整数“分”。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 后端 | Python 3.10+、Flask |
| 前端 | HTML、CSS、原生 JavaScript ES Modules |
| 图表 | Chart.js 4.4.0 |
| 数据存储 | 本地 JSON 文件 |
| 测试 | Python unittest |

页面与接口由同一 Flask 服务提供，无需单独启动前端，也无需安装 Node.js 或数据库。图表库通过 CDN 加载，显示图表需要联网。

## 安装与启动

### 环境要求

- Python **3.10或以上版本**，可使用 Python 3.12。
- Git（使用 Git 克隆、更新代码时需要）。
- Chrome、Edge 等支持现代 JavaScript 的浏览器。

Windows 可执行以下命令查看已安装的 Python：

```powershell
py -0p
```

如果没有符合要求的解释器，请先从 [Python 官网](https://www.python.org/downloads/windows/) 安装。`python --version` 没有正常输出时，不要继续创建虚拟环境；先确认实际解释器路径。

### 获取代码

在准备保存项目的目录打开 PowerShell：

```powershell
git clone https://github.com/tw1l1ghtcc/Note.git
Set-Location '.\Note'
```

已有仓库时，进入 Note 目录，确认本地改动已妥善保存，再更新：

```powershell
git switch main
git pull --ff-only origin main
```

### Windows / PowerShell

在项目根目录完整执行：

```powershell
& {
    py -3 -c "import sys; print(sys.version); assert sys.version_info >= (3, 10), '需要 Python 3.10 或以上版本'"
    if ($LASTEXITCODE -ne 0) { throw '请先安装或选择 Python 3.10+ 解释器' }

    if (-not (Test-Path -LiteralPath '.\.venv\Scripts\python.exe')) {
        py -3 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw '虚拟环境创建失败' }
    }

    & '.\.venv\Scripts\python.exe' -c "import sys; assert sys.version_info >= (3, 10), '虚拟环境版本过低'"
    if ($LASTEXITCODE -ne 0) { throw '请使用 Python 3.10+ 重新配置项目虚拟环境' }

    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络及 pip 输出' }

    & '.\.venv\Scripts\python.exe' app.py
}
```

若没有 `py` 命令，但 `python --version` 正常输出3.10以上版本，可将脚本中的 `py -3` 替换为 `python`。以上步骤无需激活虚拟环境或修改 PowerShell 执行策略。

### macOS / Linux

确认 `python3` 为3.10以上版本，在项目根目录执行：

```bash
python3 -m venv .venv && \
.venv/bin/python -m pip install -r requirements.txt && \
.venv/bin/python app.py
```

### 访问与停止

看到 `Running on http://127.0.0.1:5000` 后，打开：

**[http://127.0.0.1:5000](http://127.0.0.1:5000)**

服务默认仅本机可访问。使用时保持终端开启，按 **Ctrl+C** 停止服务。

首次安装后，Windows 每次进入项目目录只需执行：

```powershell
& '.\.venv\Scripts\python.exe' app.py
```

## 使用说明

1. **记一笔**：选择收入或支出，填写日期、金额和对应类别，备注可选，点击“保存这笔”。
2. **查看账单**：列表默认加载全部符合条件的记录，在显示框内上下滚动查看；桌面显示框高440px，手机高360px。
3. **筛选**：填写日期范围、类型、类别或金额范围，点击“筛选”；空条件不参与筛选，点击“重置”恢复全部记录。
4. **查看统计**：收入、支出、结余和图表跟随当前筛选条件更新。
5. **删除**：在目标账单上点击“删除”并确认，删除成功后列表和统计自动刷新。

金额筛选允许0，拒绝超过两位小数、负数、科学计数及超限值。最低金额不能大于最高金额。没有符合条件的记录时，页面显示空数据提示。

## 团队分工

以下为各成员负责的模块和维护范围；代码作者与协作记录见仓库提交历史。

| 成员 | 学号 | GitHub | 负责内容 | 主要文件 |
| --- | --- | --- | --- | --- |
| 包学丰（组长） | 102401434 | [tw1l1ghtcc](https://github.com/tw1l1ghtcc) | 数据存储、公共异常、应用入口、模块整合及项目文档 | `app.py`、`storage.py`、`errors.py`、`requirements.txt`、`.gitignore`、`tests/test_storage_app.py`、`README.md` |
| 冯玄 | 102401436 | [otto2-5-8](https://github.com/otto2-5-8) | 新增与删除账单、业务校验、记账测试及演示脚本 | `records.py`、`tests/test_records.py`、`tests/test_note_contract.py`、`tests/support.py`、`scripts/demo_records.py` |
| 秦文贵 | 102401615 | [vg666-NiKo](https://github.com/vg666-NiKo) | 查询参数校验、组合筛选、排序与列表接口 | `queries.py`、`test_queries.py` |
| 乔震宇 | 102401435 | [1530017982](https://github.com/1530017982) | 收支汇总、分类与月度统计、统计接口 | `statistics_service.py`、`tests/test_statistics_service.py` |
| 吴圣洲 | 102401622 | [drkalerq](https://github.com/drkalerq) | 页面框架、录入表单、收支切换、金额换算与录入交互 | `templates/index.html`、`static/css/main.css`、`static/js/entry.js` |
| 郑瀚 | 102401111 | [Kerical](https://github.com/Kerical) | 账单列表、筛选与删除交互、统计看板、图表及请求封装 | `static/js/list.js`、`static/js/dashboard.js`、`static/js/api.js`、`static/css/views.css` |

`tests/test_storage.py` 由冯玄编写，存储模块相关维护由包学丰协调；页面容器由吴圣洲维护，列表及看板内容由郑瀚对接。

## 项目结构

```text
Note/
├── app.py                       # Flask 应用入口与错误处理
├── errors.py                    # 公共异常 AppError
├── storage.py                   # JSON 存储、校验和读写锁
├── records.py                   # 新增、删除及业务校验
├── queries.py                   # 查询、筛选与排序
├── statistics_service.py        # 收支与分组统计
├── requirements.txt             # Python 依赖
├── data/
│   └── records.json             # 运行时自动生成，不提交到仓库
├── templates/
│   └── index.html               # 主页面
├── static/
│   ├── css/                     # 页面和列表、看板样式
│   └── js/                      # 录入、列表、看板和请求封装
├── scripts/
│   └── demo_records.py          # 记账接口演示
├── test_queries.py              # 查询测试
└── tests/                       # 业务、存储、统计和集成测试
```

## 数据保存

账单文件为项目目录下的 `data/records.json`。路径由代码位置确定，不依赖启动终端的工作目录；文件不存在时自动初始化。

每条记录包含六个字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 服务端生成的 UUID4 |
| `date` | `YYYY-MM-DD` 格式的真实日期 |
| `type` | `income` 或 `expense` |
| `amount` | 整数分，范围1—999999999 |
| `category` | 类别，1—20个字符 |
| `note` | 备注，最多200个字符，可为空字符串 |

读取和保存时均校验数据，发现损坏内容会返回 `STORAGE_ERROR` 并保留原文件。保存使用同目录临时文件及原子替换；新增、删除的读改写过程使用共享可重入锁保护。

备份或恢复账单前先停止服务，再复制或替换 `data/records.json`。实际账单已加入 `.gitignore`，不会随 Git 提交或拉取更新。程序按单服务进程设计，不要同时启动多个进程写同一份文件。

## 接口

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | `/` | 记账主页 |
| POST | `/api/records` | 新增账单，成功返回201 |
| DELETE | `/api/records/<id>` | 删除账单，成功返回200 |
| GET | `/api/records` | 查询账单 |
| GET | `/api/stats` | 收支、分类及月度统计 |

查询与统计共用 `start_date`、`end_date`、`type`、`category`、`min_amount`、`max_amount` 六项筛选参数；日期和金额区间均包含端点，金额参数单位为分。

列表接口支持 `limit=1` 至 `100` 或 `limit=all`，接口默认10条；当前页面使用 `limit=all`。统计接口不接受 `limit`，始终统计全部符合条件的记录。

成功响应使用 `data` 字段，列表额外返回 `meta`。错误响应包含 `error` 和 `code`，字段校验错误另含 `field`。

## 测试

安装依赖后，在项目根目录执行：

```powershell
& {
    & '.\.venv\Scripts\python.exe' -m unittest -v test_queries
    if ($LASTEXITCODE -ne 0) { throw '查询测试失败' }

    & '.\.venv\Scripts\python.exe' -m unittest discover -s tests -t . -v
    if ($LASTEXITCODE -ne 0) { throw '后端及集成测试失败' }
}
```

macOS / Linux 使用 `.venv/bin/python` 执行相同的 unittest 参数。

测试覆盖记录校验、新增删除、组合筛选、日期与金额边界、收支汇总、JSON 持久化、损坏文件保护、并发读改写及模块接口联调。

## 常见问题

| 问题 | 处理方式 |
| --- | --- |
| 找不到 `.venv\Scripts\python.exe` | 确认 Python 版本符合要求，并检查创建虚拟环境是否成功 |
| 提示缺少 Flask | 使用启动服务的同一解释器安装 `requirements.txt` |
| Git 更新提示本地文件会被覆盖 | 先备份并处理本地改动，再更新，不要强制覆盖 |
| 端口5000被占用 | 在原服务终端按 Ctrl+C 停止旧服务，再启动 |
| 页面修改后仍显示旧内容 | 重启服务，再按 Ctrl+Shift+R 强制刷新 |
| 图表未显示 | 检查 CDN 网络连接；没有匹配数据时显示空图提示 |
| 显示存储错误 | 先备份账单，再检查文件格式及字段，不要直接清空数据 |
| 保存时网络异常 | 先刷新账单核对结果，避免重复录入 |
