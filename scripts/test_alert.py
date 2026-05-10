#!/usr/bin/env python3
"""
模拟 sense-u-ble 推送一条告警 → server.py 的 /api/internal/sensor。

跳过实际 BLE 设备，直接发 POST 看完整告警链路：
  → server.py 收到 → trigger_alert() → BARK / Discord / WS 弹窗 / 历史日志

用法:
    python scripts/test_alert.py prone
    python scripts/test_alert.py --mode 2                # 等价
    python scripts/test_alert.py --mode 9 --level danger
    python scripts/test_alert.py --list                  # 列所有 mode
    python scripts/test_alert.py --host 192.168.0.170 --port 8080  # 远端

注意:
  - 告警通知开关 (alert_notify_enabled) 在 manager UI 的 global config 里。
    关掉时 server 只 log，不真发推送。
  - 弹窗 / 历史 / WS 广播跟开关无关，永远走全程；前端 alert dialog 应该会弹。
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


# 跟 sense-u-ble protocol.py 的 ALERT_MODES 保持一致。alias 是常用简写。
# level 全部 danger —— sense-u-ble service.py 把所有设备告警都标为 danger
# （见 sense_u_ble/service.py 里 _on_device_alert payload）。设备能上报的事件
# 全是孩子安危相关，BARK 上要 critical 级别绕过静音 + 持续响铃。
MODES: dict[int, tuple[str, str, list[str]]] = {
    #   id: (英文 message,         level,    CLI alias)
    2:  ("prone alert",            "danger", ["prone"]),
    3:  ("temperature high",       "danger", ["temp_high", "hot"]),
    4:  ("temperature low",        "danger", ["temp_low", "cold"]),
    7:  ("cooling reminder",       "danger", ["cool", "cooling"]),
    8:  ("breath fast",            "danger", ["breath_fast", "fast"]),
    9:  ("breath weak",            "danger", ["breath_weak", "weak"]),
    10: ("prone + breath weak",    "danger", ["prone_weak"]),
    11: ("activity alert",         "danger", ["activity"]),
    65: ("prone sleep breath weak","danger", ["prone_sleep_weak"]),
}


def resolve_mode(token: str) -> int | None:
    """'2' / 'prone' / 'prone_weak' 都行 → 返 mode id 或 None"""
    try:
        i = int(token)
        return i if i in MODES else None
    except ValueError:
        pass
    for mid, (_, _, aliases) in MODES.items():
        if token in aliases:
            return mid
    return None


def root_web_port() -> int:
    """从 baby-sentinel 项目根的 config.json 读 web_port，缺省 8080。
    脚本期望从项目根运行。"""
    cfg_path = Path(__file__).resolve().parent.parent / "config.json"
    try:
        return int(json.loads(cfg_path.read_text()).get("web_port", 8080))
    except Exception:
        return 8080


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("token", nargs="?",
                    help="mode id (2/3/9...) 或 alias (prone/weak/...)")
    ap.add_argument("--mode", type=str, help="同位置参数；写哪个都行")
    ap.add_argument("--level", choices=["info", "warning", "danger"],
                    help="覆盖默认 level（参考 MODES 表）")
    ap.add_argument("--host", default="127.0.0.1", help="server 主机（默认本机）")
    ap.add_argument("--port", type=int, default=None, help="server web_port（默认从 config.json 读）")
    ap.add_argument("--list", action="store_true", help="列出所有 mode 后退出")
    args = ap.parse_args()

    if args.list:
        print(f"{'ID':>4}  {'level':<8}  {'message':<28}  aliases")
        print("─" * 70)
        for mid, (msg, lvl, aliases) in MODES.items():
            print(f"{mid:>4}  {lvl:<8}  {msg:<28}  {', '.join(aliases)}")
        return 0

    token = args.token or args.mode
    if not token:
        ap.print_help()
        print("\n至少给一个 mode（id 或 alias）。--list 看可用。", file=sys.stderr)
        return 2

    mid = resolve_mode(token)
    if mid is None:
        print(f"unknown mode: {token!r}（--list 看支持的）", file=sys.stderr)
        return 2

    msg, default_level, _ = MODES[mid]
    level = args.level or default_level
    port  = args.port or root_web_port()
    url   = f"http://{args.host}:{port}/api/internal/sensor"

    payload = {
        "type":      "alert",
        "message":   msg,        # 英文 enum；server 出口翻 zh/ja 给推送 / 弹窗
        "level":     level,
        "mode":      mid,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }

    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    print(f"POST {url}\n     {payload}")
    try:
        # timeout=15s：server 端会同步 await trigger_alert → Discord / BARK 走完才返回；
        # 渠道慢的话 5s 不够，但告警仍已分发，给点冗余避免误报"超时"
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"\n← HTTP {r.status}  {r.read().decode(errors='replace')}")
    except urllib.error.HTTPError as e:
        print(f"\n← HTTP {e.code}  {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n← 请求失败：{type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print("\n✓ 已发送。看效果：")
    print("  - manager UI server 卡片日志面板：[AlertPush] dispatch mode=...")
    print("  - 浏览器主页：右下角告警弹窗（带 dismiss）")
    print("  - BARK / Discord（如果 alert_notify_enabled=true 且渠道配好）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
