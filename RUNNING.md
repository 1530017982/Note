# Note 后端运行与联调

## 环境

- Python 3.10 或更高版本（团队查询模块使用了 Python 3.10 的类型注解语法）。
- 在项目根目录执行以下 PowerShell 命令。先用 `python --version` 确认版本。

```powershell
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' app.py
```

浏览器访问 `http://127.0.0.1:5000`。无需激活虚拟环境，也无需修改 PowerShell 执行策略。按 Ctrl+C 停止服务。

## 模块接入

入口通过 `create_app()` 注册现有的 `records_bp`、`queries_bp`、`stats_bp`，不添加路径前缀。
模块文件尚未交付时会输出警告；已存在模块的内部导入错误不会被忽略。

主页面由5号提供 `templates/index.html`；交付前 `/` 显示临时联调页面。
2号的 `records.py` 未交付时，新增、删除功能尚不可用；不要把后端联调通过写成全部功能完成。

## 数据与错误

- 默认数据文件是项目目录中的 `data/records.json`，不受启动工作目录影响。
- 文件不存在时首次读写自动初始化。已有空文件、损坏 JSON 或非法记录会返回 `STORAGE_ERROR`，保留原数据；修复前先另存备份，不要盲目清空文件。
- 每条持久化记录必须包含六个字段：`id`（UUID4）、`date`、`type`、`amount`（整数分）、`category`、`note`。
- `load_records()` 每次重新读取并返回独立对象；`save_records()` 验证数据后写入同目录临时文件，再原子替换。
- `records_lock` 是可重入锁。2号必须在整个“读取→新增/删除→保存”期间持有此锁；仅分别调用读写函数不能保护完整事务。
- 第一版仅支持单个服务进程访问账单文件，不要同时启动多个进程写同一份数据。
- `AppError(status, code, message, field=None)` 由入口统一返回 JSON；未知接口、错误请求方法和未处理异常同样返回 JSON。内部错误详情只写到服务端日志。
- 实际账单和保存临时文件已加入 `.gitignore`，不要上传个人真实收支。

## 验证

团队测试分布在根目录和 `tests` 目录，需分别执行；上一条命令成功后再执行下一条。

```powershell
& '.\.venv\Scripts\python.exe' -m unittest -v test_queries
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

本次集成验证采用 Python 3.12 与 Flask 3.1，在临时数据目录执行47项测试通过：
查询19项、统计9项、存储及入口19项。
存储/入口测试还覆盖了真实查询/统计模块与 JSON 文件的联合调用。
查询和统计原有单元测试仍包含替身依赖；完整录入、删除与前端演示需待对应模块交付后验证。

可手动检查的只读接口：

```text
GET /api/records
GET /api/records?limit=all
GET /api/stats
GET /api/stats?type=expense
```

无数据时列表为空、统计为零，属于正常结果。`GET /api/stats?limit=1` 应返回400。
