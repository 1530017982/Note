"""公共业务异常；由应用入口转换为 HTTP 响应，不依赖 Flask。"""

from __future__ import annotations


class AppError(Exception):
    """携带状态码、错误码、用户提示和可选的出错字段。"""
    def __init__(self, status: int, code: str, message: str,
                 field: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field

    def to_dict(self) -> dict:
        """生成统一错误体；状态码单独交给 HTTP 响应，无字段时省略 field。"""
        body = {"error": self.message, "code": self.code}
        if self.field is not None:
            body["field"] = self.field
        return body
