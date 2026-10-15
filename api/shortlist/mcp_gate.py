"""ASGI wrapper for the mounted MCP apps.

- Only callers that present the shared secret (the ArmorIQ proxy) get through; with
  no secret configured nothing gets through.
- JSON-RPC bodies are reduced to the fields MCP defines; anything the proxy or an
  SDK adds (top-level IAM context, `_`-prefixed tool arguments) is moved aside into
  `current_extras` so the strict MCP parser never sees it and a second-line
  argument check can read it.
- Every request is recorded in a small ring buffer for diagnostics.
"""

import base64
import hmac
import json
import time
from collections import deque
from contextvars import ContextVar

ALLOWED_TOP = {"jsonrpc", "id", "method", "params"}
MCP_LOG: deque = deque(maxlen=200)
current_extras: ContextVar[dict] = ContextVar("current_extras", default={})


def _strip_message(msg: dict, extras: dict) -> dict:
    out = {}
    for key, value in msg.items():
        if key in ALLOWED_TOP:
            out[key] = value
        else:
            extras[key] = value
    params = out.get("params")
    args = params.get("arguments") if isinstance(params, dict) else None
    if isinstance(args, dict):
        hidden = {k: v for k, v in args.items() if k.startswith("_")}
        if hidden:
            extras["arguments"] = hidden
            out["params"] = {**params, "arguments": {k: v for k, v in args.items() if not k.startswith("_")}}
    return out


def sanitize(raw: bytes) -> tuple[bytes, dict]:
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return raw, {}
    extras: dict = {}
    if isinstance(data, dict):
        data = _strip_message(data, extras)
    elif isinstance(data, list):
        data = [_strip_message(m, extras) if isinstance(m, dict) else m for m in data]
    else:
        return raw, {}
    return json.dumps(data).encode(), extras


def _same(given: str, expected: str) -> bool:
    return bool(given) and hmac.compare_digest(given.encode(), expected.encode())


def _token_from_armoriq_header(value: str) -> str | None:
    try:
        decoded = json.loads(base64.b64decode(value))
    except (ValueError, TypeError):
        return None
    if not isinstance(decoded, dict):
        return None
    return decoded.get("token") or decoded.get("apiKey") or decoded.get("api_key")


class McpGate:
    def __init__(self, app, *, secret: str, name: str, log: deque = MCP_LOG):
        self.app, self.secret, self.name, self.log = app, secret, name, log

    def _authorized(self, headers: dict[str, str]) -> bool:
        if not self.secret:
            return False
        bearer = headers.get("authorization", "")
        if bearer.startswith("Bearer ") and _same(bearer[7:], self.secret):
            return True
        if _same(headers.get("x-api-key", ""), self.secret):
            return True
        packed = headers.get("x-armoriq-mcp-auth")
        return bool(packed) and _same(_token_from_armoriq_header(packed) or "", self.secret)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        body = b""
        more = True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
        clean, extras = sanitize(body) if body else (body, {})
        rpc: object = {}
        try:
            rpc = json.loads(clean) if clean else {}
        except ValueError:
            pass
        authorized = self._authorized(headers)
        self.log.append({
            "at": time.time(), "server": self.name, "method": scope["method"], "path": scope["path"],
            "header_names": sorted(headers), "extras": extras,
            "rpc_method": rpc.get("method") if isinstance(rpc, dict) else "batch",
            "tool": (rpc.get("params") or {}).get("name") if isinstance(rpc, dict) and isinstance(rpc.get("params"), dict) else None,
            "authorized": authorized,
        })
        if not authorized:
            payload = json.dumps({"error": "unauthorized"}).encode()
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]})
            await send({"type": "http.response.body", "body": payload})
            return
        token = current_extras.set(extras)
        new_headers = [(k, v) for k, v in scope["headers"] if k.lower() != b"content-length"]
        new_headers.append((b"content-length", str(len(clean)).encode()))
        sent = False

        async def replay():
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {"type": "http.request", "body": clean, "more_body": False}

        try:
            await self.app({**scope, "headers": new_headers}, replay, send)
        finally:
            current_extras.reset(token)
