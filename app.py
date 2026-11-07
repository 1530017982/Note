"""项目入口（对接基线，由1号按 README §3.7 维护）。

当前只做三件入口职责：

1. 创建 Flask 应用；
2. 注册公共错误处理器（:func:`errors.register_error_handlers`）；
3. 注册各成员 Blueprint。

3—6 号交付后按契约增加：

- ``app.register_blueprint(queries_bp)``      —— 3号 ``queries.py``
- ``app.register_blueprint(stats_bp)``        —— 4号 ``statistics_service.py``
- ``GET /`` 与 ``templates/``、``static/``     —— 5、6号前端

Blueprint 路径已直接写完整 ``/api/...``，注册时不加 ``url_prefix``。

运行：``python app.py`` → http://127.0.0.1:5000
"""

from __future__ import annotations

from flask import Flask

from errors import register_error_handlers
from records import records_bp


def create_app() -> Flask:
    """应用工厂：便于测试用独立实例，避免相互污染。"""
    app = Flask(__name__)

    # 中文直接输出、保持契约中的字段顺序，方便浏览器与联调工具阅读。
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    register_error_handlers(app)
    app.register_blueprint(records_bp)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
