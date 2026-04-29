"""
GATT 完整服务发现脚本
在设备配对模式下运行，列出所有 Service / Characteristic / Property
"""
import asyncio
from bleak import BleakClient, BleakScanner
from datetime import datetime

ADDRESS = "D4:92:DB:03:D7:59"

PROP_MAP = {
    "broadcast":          0x01,
    "read":               0x02,
    "write-without-resp": 0x04,
    "write":              0x08,
    "notify":             0x10,
    "indicate":           0x20,
    "auth-signed-write":  0x40,
}


def props_str(props):
    return ", ".join(p for p in props)


async def discover():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 连接 {ADDRESS} ...")
    async with BleakClient(ADDRESS, timeout=15) as client:
        print(f"已连接: {client.is_connected}\n")

        services = client.services
        for svc in services:
            print(f"{'='*70}")
            print(f"SERVICE  {svc.uuid}")
            print(f"         描述: {svc.description}")
            for char in svc.characteristics:
                props = props_str(char.properties)
                print(f"  CHAR   {char.uuid}")
                print(f"         handle={char.handle}  描述={char.description}")
                print(f"         properties=[{props}]")

                # 如果可读，尝试读一下
                if "read" in char.properties:
                    try:
                        val = await client.read_gatt_char(char.uuid)
                        try:
                            text = val.decode("utf-8").strip()
                        except Exception:
                            text = ""
                        hex_val = val.hex()
                        if text:
                            print(f"         值: {hex_val}  ({text})")
                        else:
                            print(f"         值: {hex_val}")
                    except Exception as e:
                        print(f"         读取失败: {e}")

                for desc in char.descriptors:
                    print(f"    DESC {desc.uuid}  handle={desc.handle}")
            print()


asyncio.run(discover())
