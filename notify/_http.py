"""Discord REST API 公共 HTTP helper。

设计原则：单一同步实现 + async 薄包装，避免 sync / async 两个版本各自维护。
async 调用方用 run_in_executor 包一层即可，详见 request_async()。
"""

import asyncio
import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger("BabySentinel")

API = "https://discord.com/api/v10"

_BASE_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "User-Agent":   "BabySentinel (https://github.com, 1.0)",
}


def request(
    token: str,
    method: str,
    path: str,
    payload: dict | list | None = None,
    timeout: float = 8,
) -> dict | None:
    """同步发起 Discord REST 请求。
    成功返回响应 JSON（空响应返回 {}）；HTTP 错误或异常返回 None。
    """
    url  = f"{API}{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req  = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bot {token}", **_BASE_HEADERS},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        log.warning(f"[Discord] HTTP {e.code} {path}: {e.read().decode(errors='replace')}")
        return None
    except Exception as e:
        log.warning(f"[Discord] 请求失败 {path}: {e}")
        return None


async def request_async(
    token: str,
    method: str,
    path: str,
    payload: dict | list | None = None,
    timeout: float = 8,
) -> dict | None:
    """request() 的 async 包装；将阻塞的 urlopen 放线程池避免阻塞事件循环。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, request, token, method, path, payload, timeout)
