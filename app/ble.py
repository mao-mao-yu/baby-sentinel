import asyncio
import json
import os
import time
from datetime import datetime
from typing import Optional

from bleak import BleakClient, BleakScanner

from app.config import CFG, CODE_FILE, log
from app.state import sensor_state, broadcast
from app.alerts import trigger_alert

# ── BLE 协议常量 ──────────────────────────────────────────────────────

def _u8(b: int) -> int:
    return b & 0xFF

def _ts_be() -> bytes:
    t = int(time.time())
    return bytes([(t >> 24) & 0xFF, (t >> 16) & 0xFF, (t >> 8) & 0xFF, t & 0xFF])

def _uuid(prefix: str) -> str:
    # Sense-U 的 GATT 特征 UUID 末尾 12 hex 是设备 MAC。
    # macOS 上 ble_address 是 CoreBluetooth UUID（无法反推 MAC），需通过 ble_mac 单独提供。
    mac = CFG.get("ble_mac") or CFG.get("ble_address", "")
    addr = mac.replace(":", "").replace("-", "").lower()[-12:]
    return f"{prefix}-{addr}"

CHAR_REGISTER = _uuid("01021921-9e06-a079-2e3f")  # 0x70 鉴权
CHAR_SETTINGS = _uuid("01021925-9e06-a079-2e3f")  # 0xBA 数据 polling

def _pk_reconnect(code: bytes) -> bytes:
    b = bytearray(18); b[0] = 0x70; b[1:7] = code[:6]; b[7:11] = _ts_be(); return bytes(b)

def _pk_get_baby_data() -> bytes:
    b = bytearray(20); b[0] = 0xBA; return bytes(b)

# ── 辅助 ──────────────────────────────────────────────────────────────

def load_baby_code() -> Optional[bytes]:
    if not os.path.exists(CODE_FILE):
        return None
    try:
        with open(CODE_FILE, encoding="utf-8") as f:
            h = json.load(f).get("baby_code", "")
        return bytes.fromhex(h) if len(h) == 12 else None
    except Exception:
        return None

# ── 传感器解析 ────────────────────────────────────────────────────────

_last_prone_alert: float = 0
_prone_since:      float = 0   # 当前这段连续俯卧的开始时刻；非俯卧时为 0
_POSTURES = {0: "仰卧", 1: "俯卧", 2: "左侧卧", 3: "右侧卧", 4: "坐姿"}


async def parse_baby_data(data: bytes) -> None:
    """解析 0xBA get_baby_data 响应包。
    布局: [0]=0xBA [2]=姿势 [3-4]=衣内温度*10 (LE) [6]=呼吸 [9]=电量 [10]=佩戴"""
    global _last_prone_alert, _prone_since
    if len(data) < 11:
        return

    # 姿势：data[2] 单字节，0=仰 1=俯 2=左 3=右 4=坐
    posture_id = _u8(data[2])
    if posture_id in _POSTURES:
        sensor_state["posture"] = _POSTURES[posture_id]
        log.debug(f"[BLE] 姿势: {_POSTURES[posture_id]}")
    else:
        log.warning(f"[BLE] 姿势 ID 未知: {posture_id} (0x{posture_id:02x})  data={data.hex(' ')}")

    # 俯卧报警：持续 ≥ prone_alert_threshold_s 才首次报警，
    # 之后每 prone_alert_cooldown_s 重复一次（如仍在俯卧）。
    now = time.time()
    if posture_id == 1:
        if _prone_since == 0:
            _prone_since = now
        elapsed   = now - _prone_since
        threshold = CFG.get("prone_alert_threshold_s", 30)
        cooldown  = CFG.get("prone_alert_cooldown_s", 300)
        if elapsed >= threshold and (now - _last_prone_alert) > cooldown:
            _last_prone_alert = now
            await trigger_alert(
                f"🚨 うつ伏せが {int(elapsed)} 秒続いています！すぐ確認してください！",
                "danger",
            )
    else:
        _prone_since = 0   # 切回非俯卧 → 计时重置

    # 衣内温度：data[3..4] 16-bit Little-Endian，单位 0.1°C
    temp = (_u8(data[4]) << 8 | _u8(data[3])) / 10.0
    if 10.0 < temp < 50.0:
        sensor_state["temperature"] = round(temp, 1)
        log.debug(f"[BLE] 衣内温度: {temp:.1f}°C")
    elif temp != 0.0:
        log.warning(f"[BLE] 温度超范围: [3-4]={data[3]:02x} {data[4]:02x} → {temp:.1f}°C")

    rate = _u8(data[6])
    if rate < 200:
        sensor_state["breath_rate"] = rate
        log.debug(f"[BLE] 呼吸频率: {rate} 次/min")

    battery = _u8(data[9])
    if battery <= 100:
        sensor_state["battery"] = battery
        log.debug(f"[BLE] 电量: {battery}%")

    # 收到 0xBA 数据即视为连接活跃
    if not sensor_state.get("ble_ok"):
        sensor_state["ble_ok"] = True
        log.info("[BLE] 连接已活跃")

    sensor_state["last_update"] = datetime.now().strftime("%H:%M:%S")
    await broadcast({"type": "sensor", **sensor_state})


# ── BLE 连接循环 ──────────────────────────────────────────────────────

_current_client = None   # 保持当前 BleakClient，供外部主动刷新使用


async def request_refresh() -> bool:
    """向设备发送 get_baby_data (0xBA)，触发设备立即推送一份完整快照。"""
    if _current_client and _current_client.is_connected:
        try:
            await _current_client.write_gatt_char(CHAR_SETTINGS, _pk_get_baby_data(), response=True)
            log.debug("[BLE] 主动刷新：已发送 0xBA")
            return True
        except Exception as e:
            log.debug(f"[BLE] 主动刷新失败: {e}")
    return False


async def loop() -> None:
    addr = CFG["ble_address"]

    while True:
        code = load_baby_code()
        if code is None:
            log.warning("[BLE] 未找到 baby_code.json，请先运行 tools/pairing.py 完成配对")
            await asyncio.sleep(10)
            continue

        log.debug(f"[BLE] 扫描 {addr}...")
        sensor_state.update(ble_ok=False)
        await broadcast({"type": "sensor", **sensor_state})

        try:
            found_evt    = asyncio.Event()
            found_device = None

            def _detection_cb(dev, _):
                nonlocal found_device
                if dev.address.upper() == addr.upper() and not found_evt.is_set():
                    found_device = dev
                    found_evt.set()

            async with BleakScanner(detection_callback=_detection_cb):
                try:
                    await asyncio.wait_for(found_evt.wait(), timeout=CFG.get("ble_scan_timeout_s", 20))
                except asyncio.TimeoutError:
                    pass

            device = found_device
            if device is None:
                log.warning("[BLE] 未扫描到设备，5 秒后重试...")
                await asyncio.sleep(5)
                continue

            log.info("[BLE] 找到设备，连接中...")
            disc_evt = asyncio.Event()
            _connect_ts = time.time()

            async with BleakClient(
                device, timeout=CFG.get("ble_connect_timeout_s", 15),
                disconnected_callback=lambda _: disc_evt.set(),
            ) as client:
                global _current_client
                _current_client = client
                log.info("[BLE] 已连接，等待 GATT 就绪...")
                await asyncio.sleep(2.5)

                async def on_settings(_s, raw: bytearray):
                    d = bytes(raw)
                    if d and d[0] == 0xBA:
                        await parse_baby_data(d)

                async def on_register(_s, raw: bytearray):
                    d = bytes(raw)
                    if not d or d[0] != 0x70:
                        return
                    if len(d) >= 2 and d[1] == 0x00:
                        log.info("[BLE] 鉴权成功！")
                        sensor_state.update(ble_ok=True)
                        await broadcast({"type": "sensor", **sensor_state})
                    elif len(d) >= 2 and d[1] == 0x01:
                        log.error("[BLE] 鉴权失败！baby_code 无效，请删除 baby_code.json 后重新配对")

                def _wrap(name: str, handler):
                    """如开 ble_dump_raw，先 hex dump 再交给原 handler。"""
                    async def _aw(s, raw):
                        if CFG.get("ble_dump_raw"):
                            log.info(f"[BLE] RX {name}: {bytes(raw).hex(' ')}")
                        await handler(s, raw)
                    return _aw

                # 只订阅鉴权 + 数据两个 char
                for uuid, name, handler in [
                    (CHAR_REGISTER, "CHAR_1", on_register),
                    (CHAR_SETTINGS, "CHAR_4", on_settings),
                ]:
                    log.info(f"[BLE] 订阅 {name}...")
                    for attempt in range(3):
                        try:
                            await asyncio.wait_for(
                                client.start_notify(uuid, _wrap(name, handler)), timeout=10
                            )
                            log.info(f"[BLE] 已订阅 {name}")
                            await asyncio.sleep(0.3)
                            break
                        except asyncio.TimeoutError:
                            log.warning(f"[BLE] 订阅 {name} 超时 (尝试 {attempt+1}/3)")
                            if attempt < 2:
                                await asyncio.sleep(1.0)
                        except Exception as e:
                            if attempt < 2:
                                await asyncio.sleep(1.0)
                            else:
                                log.warning(f"[BLE] 订阅 {name} 失败: {e}")

                pkt = _pk_reconnect(code)
                log.info(f"[BLE] 发送鉴权重连包 (0x70): {pkt.hex()}")
                try:
                    await asyncio.wait_for(
                        client.write_gatt_char(CHAR_REGISTER, pkt, response=False),
                        timeout=10,
                    )
                except asyncio.TimeoutError:
                    log.warning("[BLE] 鉴权写入超时")
                except Exception as e:
                    log.warning(f"[BLE] 鉴权写入失败: {e}")

                # 立即拉一次完整快照，避免等 polling 间隔
                try:
                    await client.write_gatt_char(CHAR_SETTINGS, _pk_get_baby_data(), response=True)
                except Exception:
                    pass

                # 主循环：每 N 秒 polling 一次 0xBA
                _POLL_S = CFG.get("ble_poll_interval_s", 2)
                while not disc_evt.is_set():
                    try:
                        await asyncio.wait_for(disc_evt.wait(), timeout=_POLL_S)
                        break  # disc_evt fired → 正常断线
                    except asyncio.TimeoutError:
                        if not client.is_connected:
                            break
                        try:
                            await client.write_gatt_char(CHAR_SETTINGS, _pk_get_baby_data(), response=True)
                            log.debug("[BLE] 0xBA polling")
                        except Exception as ke:
                            log.warning(f"[BLE] 0xBA 发送失败: {ke}")

                _current_client = None
                elapsed = int(time.time() - _connect_ts)
                log.info(f"[BLE] 连接断开（持续 {elapsed}s）")

        except Exception as e:
            log.warning(f"[BLE] 错误: {type(e).__name__}: {e}")

        sensor_state.update(ble_ok=False)
        await broadcast({"type": "sensor", **sensor_state})
        delay = CFG.get("ble_reconnect_delay_s", 10)
        log.debug(f"[BLE] {delay} 秒后重连...")
        await asyncio.sleep(delay)
