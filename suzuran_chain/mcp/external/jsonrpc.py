import json
import uuid
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field


class JSONRPCError:
    STANDARD_ERRORS = {
        -32700: "Parse error",
        -32600: "Invalid request",
        -32601: "Method not found",
        -32602: "Invalid params",
        -32603: "Internal error",
    }

    def __init__(self, code: int, message: Optional[str] = None, data: Any = None):
        self.code = code
        self.message = message or self.STANDARD_ERRORS.get(code, "Unknown error")
        self.data = data

    def to_dict(self) -> Dict[str, Any]:
        result = {"code": self.code, "message": self.message}
        if self.data is not None:
            result["data"] = self.data
        return result

    @classmethod
    def parse_error(cls, data: Any = None) -> "JSONRPCError":
        return cls(-32700, data=data)

    @classmethod
    def invalid_request(cls, data: Any = None) -> "JSONRPCError":
        return cls(-32600, data=data)

    @classmethod
    def method_not_found(cls, method: str) -> "JSONRPCError":
        return cls(-32601, data={"method": method})

    @classmethod
    def invalid_params(cls, data: Any = None) -> "JSONRPCError":
        return cls(-32602, data=data)

    @classmethod
    def internal_error(cls, data: Any = None) -> "JSONRPCError":
        return cls(-32603, data=data)


@dataclass
class JSONRPCRequest:
    jsonrpc: str = "2.0"
    id: Optional[Union[int, str]] = None
    method: str = ""
    params: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.id is not None:
            result["id"] = self.id
        if self.params is not None:
            result["params"] = self.params
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JSONRPCRequest":
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method", ""),
            params=data.get("params"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "JSONRPCRequest":
        return cls.from_dict(json.loads(raw))

    @property
    def is_notification(self) -> bool:
        return self.id is None


@dataclass
class JSONRPCResponse:
    jsonrpc: str = "2.0"
    id: Optional[Union[int, str]] = None
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            result["id"] = self.id
        if self.error is not None:
            result["error"] = self.error.to_dict()
        else:
            result["result"] = self.result
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def success(cls, request_id: Optional[Union[int, str]], result: Any) -> "JSONRPCResponse":
        return cls(id=request_id, result=result)

    @classmethod
    def error(cls, request_id: Optional[Union[int, str]], err: JSONRPCError) -> "JSONRPCResponse":
        return cls(id=request_id, error=err)


@dataclass
class JSONRPCNotification:
    jsonrpc: str = "2.0"
    method: str = ""
    params: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params is not None:
            result["params"] = self.params
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def tools_changed(cls) -> "JSONRPCNotification":
        return cls(method="notifications/tools/list_changed")

    @classmethod
    def resources_changed(cls) -> "JSONRPCNotification":
        return cls(method="notifications/resources/list_changed")

    @classmethod
    def initialized(cls) -> "JSONRPCNotification":
        return cls(method="notifications/initialized")

    @classmethod
    def progress(cls, progress_token: str, progress: float, total: Optional[float] = None) -> "JSONRPCNotification":
        params: Dict[str, Any] = {"progressToken": progress_token, "progress": progress}
        if total is not None:
            params["total"] = total
        return cls(method="notifications/progress", params=params)

    @classmethod
    def logging(cls, level: str, data: Any, logger_name: Optional[str] = None) -> "JSONRPCNotification":
        params: Dict[str, Any] = {"level": level, "data": data}
        if logger_name is not None:
            params["logger"] = logger_name
        return cls(method="notifications/message", params=params)