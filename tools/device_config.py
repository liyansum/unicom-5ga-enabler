"""Public device selection: no embedded serial numbers or pairing records."""
SUPPORTED_PRODUCT='iPhone15,2'
SUPPORTED_IOS='27.0.1'
SUPPORTED_BUILD='24A446'

def require_supported(product,version,build):
    if (product,version,build)!=(SUPPORTED_PRODUCT,SUPPORTED_IOS,SUPPORTED_BUILD):
        raise RuntimeError('此载荷仅适用于 iPhone 14 Pro / iOS 27.0.1 (24A446)，已停止操作。')

async def check_lockdown(lockdown):
    require_supported(lockdown.product_type,lockdown.product_version,await lockdown.get_value(key='BuildVersion'))

async def choose_device():
    from pymobiledevice3.usbmux import list_devices
    from pymobiledevice3.lockdown import create_using_usbmux
    devices=[device for device in await list_devices() if device.is_usb]
    if len(devices)!=1:raise RuntimeError('请仅通过 USB 连接一台已解锁并信任此电脑的 iPhone。')
    lockdown=await create_using_usbmux(serial=devices[0].serial,autopair=False)
    try:
        await check_lockdown(lockdown)
        return devices[0].serial
    finally:await lockdown.close()
