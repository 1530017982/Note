# 成员02模块的集成修复

## 本次调整

- 保留成员02原始新增、删除业务实现与提交历史。
- 合并当前主仓库，保留已有的 app.py、errors.py、storage.py、requirements.txt 和 .gitignore；不覆盖查询、统计、页面和已修复的录入提示。
- records.py 只依赖 errors.AppError，以及约定的 load_records、save_records、new_record_id、records_lock。
- 日期、金额、类型、类别和备注校验移到 records.py 内；错误辅助函数仅构造公共 AppError，不增加公共模块的隐式接口。
- 主仓库入口会自动注册 records_bp，无需再次改动 app.py。
- 测试直接使用主仓库工厂，不再另建缺少查询/统计的应用；GET /api/records 预期为200，JSON对象字段按集合验证。
- 测试不依赖错误文案的内部实现细节，不再从 errors 导入主仓库没有的 storage_error。
- 原独立交付说明保留为历史材料，不能据其旧入口说明覆盖当前应用。

## 验证

Python 3.12、Flask 3.1下，102项测试通过：原有查询/统计/入口存储47项，成员02新增的业务、存储及集成测试55项。

```powershell
python -m unittest -v test_queries
python -m unittest discover -s tests -t . -v
```

测试数据位于每个用例的独立临时目录。已验证三组 Blueprint 在真实入口中共同工作，新增100.00元收入、12.50元支出得到87.50元结余；删除后列表和统计同步更新；非法请求不落盘；并发新增不丢数据。

## 归属与范围

成员02原始代码由其原提交保留。本次对接调整由组长请求 Codex 协助完成，作为独立集成修复提交记录，不冒充成员02的独立开发成果。
尚未验证6号列表/看板的完整浏览器流程；运行方法见根目录 RUNNING.md。
