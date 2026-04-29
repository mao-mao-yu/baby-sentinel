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
    addr = CFG["ble_address"].replace(":", "").lower()
    return f"{prefix}-{addr}"

CHAR_REGISTER   = _uuid("01021921-9e06-a079-2e3f")
CHAR_REALTIME   = _uuid("01021922-9e06-a079-2e3f")
CHAR_DATA_GUIDE = _uuid("01021923-9e06-a079-2e3f")
CHAR_SETTINGS   = _uuid("01021925-9e06-a079-2e3f")

def _pk_reconnect(code: bytes) -> bytes:
    b = bytearray(18); b[0] = 0x70; b[1:7] = code[:6]; b[7:11] = _ts_be(); return bytes(b)

def _pk_get_batch()     -> bytes: b = bytearray(20); b[0] = 0xC0; b[1] = 0x01; return bytes(b)
def _pk_get_baby_data() -> bytes: b = bytearray(20); b[0] = 0xBA; return bytes(b)
def _pk_power_on()      -> bytes: return bytes([0xF5, 0xF2, 0x32, 0x03, 0x00])
def _pk_temp_alarm()    -> bytes: return bytes([0xB2, 0x00, 0x68, 0x01, 0xC8, 0x00])
def _pk_kick_alarm()    -> bytes: return bytes([0xB3, 0x00, 0x0F, 0x03, 0x00])
def _pk_breath_alarm()  -> bytes: return bytes([0xB0, 0x01, 0x19])

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

_POSTURES = {0: "仰卧", 1: "俯卧", 2: "左侧卧", 3: "右侧卧"}


async def parse_baby_data(data: bytes) -> None:
    """解析 0xBA get_baby_data 响应包（APK parseDeviceLastData 格式）。
    布局: [0]=0xBA [2]=姿势 [3-4]=温度*10 [5]=湿度 [6]=呼吸 [9]=电量 [10]=佩戴"""
    global _last_prone_alert
    if len(data) < 11:
        return

    posture_id = _u8(data[2])
    p = _POSTURES.get(posture_id, f"未知({posture_id})")
    prev_posture = sensor_state.get("posture")
    sensor_state["posture"] = p
    log.debug(f"[BLE] 姿势(0xBA): {p}")
    if posture_id == 1:
        now = time.time()
        if prev_posture != "俯卧" or now - _last_prone_alert > CFG.get("prone_alert_cooldown_s", 300):
            _last_prone_alert = now
            await trigger_alert("🚨 うつ伏せです！すぐ確認してください！", "danger")

    temp = (_u8(data[4]) << 8 | _u8(data[3])) / 10.0
    if 10.0 < temp < 50.0:
        sensor_state["temperature"] = temp
        sensor_state["humidity"]    = _u8(data[5])
        log.debug(f"[BLE] 衣内温度(0xBA): {temp}°C  湿度: {sensor_state['humidity']}%")

    rate = _u8(data[6])
    if rate < 200:
        sensor_state["breath_rate"] = rate
        log.debug(f"[BLE] 呼吸频率(0xBA): {rate} 次/min")

    battery = _u8(data[9])
    if battery <= 100:
        sensor_state["battery"] = battery
        log.debug(f"[BLE] 电量(0xBA): {battery}%")

    sensor_state["is_wearing"] = (_u8(data[10]) == 0x81)

    sensor_state["last_update"] = datetime.now().strftime("%H:%M:%S")
    await broadcast({"type": "sensor", **sensor_state})

async def parse_sensor(data: bytes) -> None:
    global _last_prone_alert
    if len(data) < 2:
        return
    rt = (_u8(data[0]) >> 3) & 0x1F
    st = ((_u8(data[0]) << 8 | _u8(data[1])) >> 6) & 0x1F
    changed = False

    if rt == 0x06:
        if st == 0x01 and len(data) >= 7:
            sensor_state["battery"]    = _u8(data[6])
            sensor_state["is_wearing"] = True
            log.debug(f"[BLE] 电量: {sensor_state['battery']}%")
            changed = True
        elif st == 0x02:
            sensor_state["is_wearing"] = False; changed = True
        elif st == 0x04:
            sensor_state["is_wearing"] = True;  changed = True

    elif rt == 0x08:
        if st == 0x01 and len(data) >= 8:
            sensor_state["temperature"] = (_u8(data[6]) << 8 | _u8(data[5])) / 10.0
            sensor_state["humidity"]    = _u8(data[7])
            log.debug(f"[BLE] 衣内温度: {sensor_state['temperature']}°C  湿度: {sensor_state['humidity']}%")
            changed = True

        elif st == 0x02 and len(data) >= 7:
            mode, notify = _u8(data[5]), _u8(data[6])
            if notify:
                msgs = {
                    2: ("⚠️ 姿勢アラート！",              "warning"),
                    3: ("🌡️ 衣内温度が高すぎます！",     "danger"),
                    4: ("🌡️ 衣内温度が低すぎます！",     "warning"),
                    7: ("🌡️ 衣内温度が下がっています！", "warning"),
                    8: ("💨 呼吸が速すぎます！",          "danger"),
                    9: ("💨 呼吸が遅い／止まっています！","danger"),
                }
                if mode in msgs:
                    await trigger_alert(*msgs[mode])

        elif st == 0x04 and len(data) >= 6:
            p            = _POSTURES.get(_u8(data[5]), f"未知({_u8(data[5])})")
            prev_posture = sensor_state.get("posture")
            sensor_state["posture"] = p
            log.debug(f"[BLE] 姿势: {p}")
            changed = True
            if _u8(data[5]) == 1:
                now = time.time()
                if prev_posture != "俯卧" or now - _last_prone_alert > CFG.get("prone_alert_cooldown_s", 300):
                    _last_prone_alert = now
                    await trigger_alert("🚨 うつ伏せです！すぐ確認してください！", "danger")

        elif st == 0x05 and len(data) >= 7:
            rate = _u8(data[5])
            if rate < 200:
                sensor_state["breath_rate"] = rate
                log.debug(f"[BLE] 呼吸频率: {rate} 次/min")
                changed = True

    if changed:
        sensor_state["last_update"] = datetime.now().strftime("%H:%M:%S")
        await broadcast({"type": "sensor", **sensor_state})

# ── BLE 连接循环 ──────────────────────────────────────────────────────

_current_client = None   # 保持当前 BleakClient，供外部主动刷新使用


async def request_refresh() -> bool:
    """向设备发送 get_baby_data (0xBA) 命令，触发设备重新推送所有传感器数据。"""
    if _current_client and _current_client.is_connected:
        try:
            await _current_client.write_gatt_char(CHAR_SETTINGS, _pk_get_baby_data(), response=True)
            log.debug("[BLE] 主动刷新：已发送 get_baby_data (0xBA)")
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
            # 用回调方式扫描：发现目标设备立即返回，最多等 20 s
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
                await asyncio.sleep(1.5)

                loop_ = asyncio.get_event_loop()

                async def on_settings(_s, raw: bytearray):
                    d = bytes(raw)
                    if not d: return
                    if   d[0] == 0xC0: await client.write_gatt_char(CHAR_SETTINGS, _pk_power_on(),     response=False)
                    elif d[0] == 0xF5: await client.write_gatt_char(CHAR_SETTINGS, _pk_temp_alarm(),   response=False)
                    elif d[0] == 0xB2: await client.write_gatt_char(CHAR_SETTINGS, _pk_kick_alarm(),   response=False)
                    elif d[0] == 0xB3: await client.write_gatt_char(CHAR_SETTINGS, _pk_breath_alarm(), response=False)
                    elif d[0] == 0xB0: log.info("[BLE] 设备配置完成，传感器数据开始接收")
                    elif d[0] == 0xBA: await parse_baby_data(d)
                    else:              await parse_sensor(d)

                async def on_register(_s, raw: bytearray):
                    d = bytes(raw)
                    if not d: return
                    if d[0] == 0x70:
                        if len(d) >= 2 and d[1] == 0x00:
                            log.info("[BLE] 鉴权成功！")
                            sensor_state.update(ble_ok=True)
                            await broadcast({"type": "sensor", **sensor_state})
                            await client.write_gatt_char(CHAR_SETTINGS, _pk_get_batch(), response=False)
                            await asyncio.sleep(0.5)
                            await client.write_gatt_char(CHAR_SETTINGS, _pk_get_baby_data(), response=True)
                            log.info("[BLE] 已请求全量传感器数据 (0xBA)")
                        elif len(d) >= 2 and d[1] == 0x01:
                            log.error("[BLE] 鉴权失败！baby_code 无效，请删除 baby_code.json 后重新配对")
                    else:
                        await parse_sensor(d)

                def on_data(_s, raw: bytearray):
                    loop_.call_soon_threadsafe(
                        asyncio.ensure_future, parse_sensor(bytes(raw))
                    )

                for uuid, name, handler in [
                    (CHAR_REGISTER,   "CHAR_1", on_register),
                    (CHAR_REALTIME,   "CHAR_2", on_data),
                    (CHAR_DATA_GUIDE, "CHAR_3", on_data),
                    (CHAR_SETTINGS,   "CHAR_4", on_settings),
                ]:
                    for attempt in range(3):
                        try:
                            await client.start_notify(uuid, handler)
                            await asyncio.sleep(0.3)
                            break
                        except Exception as e:
                            if attempt < 2:
                                await asyncio.sleep(1.0)
                            else:
                                log.warning(f"[BLE] 订阅 {name} 失败: {e}")

                await client.write_gatt_char(CHAR_REGISTER, _pk_reconnect(code), response=False)

                # 等待断线事件；每 N 秒向设备请求一次全量传感器数据（0xBA）
                _POLL_S = CFG.get("ble_poll_interval_s", 5)
                while not disc_evt.is_set():
                    try:
                        await asyncio.wait_for(disc_evt.wait(), timeout=_POLL_S)
                        break  # disc_evt fired → 正常断线
                    except asyncio.TimeoutError:
                        if not client.is_connected:
                            break
                        try:
                            await client.write_gatt_char(CHAR_SETTINGS, _pk_get_baby_data(), response=True)
                            log.debug("[BLE] 定期数据请求：已发送 get_baby_data (0xBA)")
                        except Exception as ke:
                            log.debug(f"[BLE] get_baby_data 失败: {ke}")

                _current_client = None
                elapsed = int(time.time() - _connect_ts)
                log.info(f"[BLE] 连接断开（持续 {elapsed}s）")

        except Exception as e:
            log.warning(f"[BLE] 错误: {type(e).__name__}: {e}")

        sensor_state.update(ble_ok=False)
        await broadcast({"type": "sensor", **sensor_state})
        delay = CFG.get("ble_reconnect_delay_s", 10)
        log.debug(f"[BLE] {delay} 秒后重连（等待 Windows BLE 栈释放）...")
        await asyncio.sleep(delay)
