"""公共异常与统一 JSON 错误响应（项目 README §3.6，由1号维护）。

本文件是「对接基线」，状态码与 code 严格按契约实现，供 2—4 号共用：

- 业务模块只抛出 :class:`AppError`，绝不各自拼装错误响应；
- 入口 :mod:`app` 调用 :func:`register_error_handlers` 注册处理器，
  由它统一把异常序列化为 ``{"error", "code", "field"}``；
- ``error`` 可直接展示给用户，``code`` 供程序判断，
  不向前端暴露堆栈和本地绝对路径。

1号合并本模块时保持 ``AppError(status, code, message, field=None)`` 签名不变即可，
2—4 号无需改动。
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

# 只有 /api/* 使用 JSON 错误体；页面与静态资源保留 Flask 默认行为（§3.1）。
API_PREFIX = "/api/"

# 契约只规定了 404 / 405 两个纯 HTTP 错误；其它状态码按需兜底。
HTTP_ERROR_DEFAULTS = {
    404: ("NOT_FOUND", "接口不存在"),
    405: ("METHOD_NOT_ALLOWED", "该接口不支持此请求方法"),
}


class AppError(Exception):
    """业务异常：字段错误带 ``field``，非字段错误省略（§3.6）。"""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field

    def to_dict(self) -> dict:
        """序列化为契约错误体；``field`` 为空时不出现该键。"""
        body: dict = {"error": self.message, "code": self.code}
        if self.field is not None:
            body["field"] = self.field
        return body

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return (
            f"AppError(status={self.status}, code={self.code!r}, "
            f"field={self.field!r}, message={self.message!r})"
        )


def validation_error(message: str, field: str | None = None) -> AppError:
    """400 VALIDATION_ERROR：必填缺失、取值非法、未知字段/参数、区间冲突。"""
    return AppError(400, "VALIDATION_ERROR", message, field)


def invalid_json(message: str = "请求体必须是合法的 JSON 对象") -> AppError:
    """400 INVALID_JSON：JSON 语法错误，或请求体不是对象。"""
    return AppError(400, "INVALID_JSON", message)


def record_not_found(record_id: str) -> AppError:
    """404 RECORD_NOT_FOUND：指定记录不存在（含重复删除、id 格式不匹配）。"""
    return AppError(404, "RECORD_NOT_FOUND", f"账单记录不存在：{record_id}")


def storage_error(message: str = "账单数据读写失败，请稍后重试") -> AppError:
    """500 STORAGE_ERROR：读写失败、JSON 损坏、已有记录格式不合法。"""
    return AppError(500, "STORAGE_ERROR", message)


def unsupported_media_type(
    message: str = "请求必须使用 Content-Type: application/json",
) -> AppError:
    """415 UNSUPPORTED_MEDIA_TYPE：POST 没有使用 application/json。"""
    return AppError(415, "UNSUPPORTED_MEDIA_TYPE", message)


def is_api_request() -> bool:
    """当前请求是否属于 /api/*（决定错误体用 JSON 还是交给 Flask 默认处理）。"""
    return request.path.startswith(API_PREFIX)


def register_error_handlers(app: Flask) -> Flask:
    """在应用上注册公共错误处理器，返回同一个 app 便于链式调用。"""

    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify(error.to_dict()), error.status

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        # 页面/静态资源的 404 保留 Flask 默认 HTML，避免影响 5、6 号前端调试。
        if not is_api_request():
            return error
        code, message = HTTP_ERROR_DEFAULTS.get(
            error.code, ("HTTP_ERROR", f"请求失败（{error.code}）")
        )
        return jsonify({"error": message, "code": code}), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        # 细节只进服务端日志，返回体不含堆栈与路径。
        logger.exception("未处理的异常：%s", error)
        return jsonify({"error": "服务器内部错误", "code": "INTERNAL_ERROR"}), 500

    return app
