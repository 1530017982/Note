"""应用入口：组装各业务模块，提供主页和统一的 JSON 错误响应。"""

from __future__ import annotations

import importlib
import logging

from flask import Flask, jsonify, render_template
from jinja2 import TemplateNotFound
from werkzeug.exceptions import HTTPException

from errors import AppError


# 将框架产生的 HTTP 错误映射为前端统一识别的错误码和提示。
HTTP_ERRORS = {
    400: ("INVALID_JSON", "请求体必须是合法的 JSON 对象"),
    404: ("NOT_FOUND", "请求的接口或页面不存在"),
    405: ("METHOD_NOT_ALLOWED", "该接口不支持此请求方法"),
    415: ("UNSUPPORTED_MEDIA_TYPE", "请使用 application/json 提交请求"),
}


def create_app(test_config: dict | None = None) -> Flask:
    """创建独立应用实例；测试可通过 test_config 覆盖配置。"""
    app = Flask(__name__)
    app.json.ensure_ascii = False
    if test_config:
        app.config.update(test_config)

    # 仅跳过缺失的模块本身；模块内部依赖出错必须继续抛出，避免掩盖故障。
    missing_modules = []
    for module_name, blueprint_name in (
        ("records", "records_bp"),
        ("queries", "queries_bp"),
        ("statistics_service", "stats_bp"),
    ):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
            missing_modules.append(module_name)
        else:
            app.register_blueprint(getattr(module, blueprint_name))
    app.extensions["note_missing_modules"] = missing_modules
    for module_name in missing_modules:
        app.logger.warning("Module not delivered yet: %s", module_name)

    @app.get("/")
    def index():
        """渲染主页面，仅在首页文件缺失时显示临时联调页。"""
        try:
            return render_template("index.html")
        except TemplateNotFound as exc:
            if exc.name != "index.html":
                raise
            return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
                    "<title>Note</title><h1>Note 个人记账本</h1>"
                    "<p>主页面尚未交付，当前可验证已接入的后端接口。</p>"
                    "<ul><li><a href='/api/records'>最近记录</a></li>"
                    "<li><a href='/api/stats'>收支统计</a></li></ul></html>")

    @app.errorhandler(AppError)
    def handle_app_error(error):
        """业务模块只描述错误，由入口统一设置响应体和 HTTP 状态。"""
        return jsonify(error.to_dict()), error.status

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        code, message = HTTP_ERRORS.get(
            error.code, ("HTTP_ERROR", "请求无法处理")
        )
        # 替换默认 HTML 错误页，同时保留405的 Allow 等标准响应头。
        response = error.get_response()
        response.set_data(app.json.dumps({"error": message, "code": code}))
        response.content_type = "application/json; charset=utf-8"
        return response

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        # 详细堆栈只写日志，前端不暴露内部路径或异常内容。
        app.logger.exception("Unhandled application error")
        return jsonify(error="服务内部错误，请稍后重试", code="INTERNAL_ERROR"), 500

    return app


if __name__ == "__main__":
    # 直接运行时启动本机单进程服务；导入工厂用于测试时不启动端口。
    logging.basicConfig(level=logging.INFO)
    create_app().run(host="127.0.0.1", port=5000, debug=False, threaded=True)
