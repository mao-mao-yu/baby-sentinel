#!/usr/bin/env python3
"""
LLM toolcall 调试 CLI — 跳过 STT/TTS，直接发文本给 voice_service 看 LLM 怎么调工具。

用法:
    python tools/test_llm.py "配方奶 90 毫升"
    python tools/test_llm.py --lang ja "粉ミルク 90 ml"
    python tools/test_llm.py --url http://localhost:8001 "今日喂了几次"

工具会真实执行（写入 baby_log）。说"撤销"或在 web UI 里删除可回滚。
LLM 的 tool_calls 详情看 manager UI 里 voice service 的日志面板。
"""
import argparse
import json
import sys
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", help="模拟用户语音转写后的文本")
    ap.add_argument("--lang", default="zh", help="zh / ja / en (default: zh)")
    ap.add_argument("--url", default="http://localhost:8001",
                    help="voice service base URL (default: http://localhost:8001)")
    args = ap.parse_args()

    body = json.dumps({"text": args.text, "lang": args.lang}).encode()
    req = urllib.request.Request(
        f"{args.url.rstrip('/')}/voice/test_llm",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"连接 {args.url} 失败: {e.reason}", file=sys.stderr)
        return 1

    print(f"\n  in:    [{data['lang']}] {data['text_in']!r}")
    print(f"  out:   {data['reply']!r}")
    print(f"  elapsed: {data['elapsed_s']}s   followup={data['needs_followup']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
