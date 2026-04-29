#!/usr/bin/env python3
"""测试 Discord 通知是否正常工作"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import CFG
from notify.discord_send import _request, _send_to_channel, _get_dm_channel

token       = CFG.get("discord_token", "")
channel_ids = CFG.get("discord_channel_ids", [])
user_ids    = CFG.get("discord_user_ids", [])

print(f"Token   : {token[:20]}...{token[-5:]}" if token else "Token   : (未配置)")
print(f"Channels: {channel_ids}")
print(f"Users   : {user_ids}")

if not token:
    print("\n[ERROR] discord_token 未配置。")
    sys.exit(1)

# 1. 验证 Bot 身份
print("\n[1] 验证 Bot 身份...")
me = _request(token, "GET", "/users/@me")
if me:
    print(f"    OK  Bot: {me.get('username')}  id={me.get('id')}")
else:
    print("    FAIL 无法获取 Bot 信息，请检查 token。")
    sys.exit(1)

msg = "🍼 [BabySentinel テスト]\nDiscord 通知の接続テストです。\n赤ちゃんのモニタリングシステムは正常に動作しています ✅"

# 2. 频道发送
print("\n[2] 频道消息测试...")
if not channel_ids:
    print("    SKIP 未配置 discord_channel_ids")
else:
    for cid in channel_ids:
        cid_str = str(cid)
        ok = _send_to_channel(token, cid_str, msg, "info")
        print(f"    {'OK  ' if ok else 'FAIL'} channel_id={cid_str}")

# 3. 私信发送
print("\n[3] 私信（DM）测试...")
if not user_ids:
    print("    SKIP 未配置 discord_user_ids")
else:
    for uid in user_ids:
        uid_str = str(uid)
        dm_id = _get_dm_channel(token, uid_str)
        if dm_id:
            ok = _send_to_channel(token, dm_id, msg, "info")
            print(f"    {'OK  ' if ok else 'FAIL'} user_id={uid_str} → dm_channel={dm_id}")
        else:
            print(f"    FAIL user_id={uid_str}  ← 无法创建 DM 频道（可能是频道ID而非用户ID）")

print("\n测试完成。")
