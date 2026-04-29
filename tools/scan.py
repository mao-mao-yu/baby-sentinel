import asyncio
from bleak import BleakScanner

async def main():
    devices = await BleakScanner.discover(timeout=10)
    for d in devices:
        print(d.address, d.name)

asyncio.run(main())