"""Compatibility and privacy behavior; no device I/O."""
import asyncio,importlib.util,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from pathlib import Path
spec=importlib.util.spec_from_file_location('device_config_test',Path(__file__).resolve().parents[1]/'tools/device_config.py')
config=importlib.util.module_from_spec(spec);spec.loader.exec_module(config)

class TestDeviceConfig(unittest.TestCase):
 def test_supported_configuration(self):config.require_supported('iPhone15,2','27.0.1','24A446')
 def test_other_model_system_or_build_is_rejected(self):
  for values in [('iPhone16,1','27.0.1','24A446'),('iPhone15,2','27.0','24A446'),('iPhone15,2','27.0.1','unknown')]:
   with self.assertRaises(RuntimeError):config.require_supported(*values)
 def test_one_usb_device_is_used_without_querying_personal_name(self):
  device=SimpleNamespace(serial='offline-device',is_usb=True)
  wifi=SimpleNamespace(serial='offline-network',is_usb=False)
  lockdown=SimpleNamespace(product_type='iPhone15,2',product_version='27.0.1',get_value=AsyncMock(return_value='24A446'),close=AsyncMock())
  with patch('pymobiledevice3.usbmux.list_devices',new_callable=AsyncMock,return_value=[device,wifi]),patch('pymobiledevice3.lockdown.create_using_usbmux',new_callable=AsyncMock,return_value=lockdown) as create:
   self.assertEqual(asyncio.run(config.choose_device()),'offline-device')
   create.assert_awaited_once_with(serial='offline-device',autopair=False)
   lockdown.get_value.assert_awaited_once_with(key='BuildVersion')
   lockdown.close.assert_awaited_once()
 def test_multiple_usb_devices_are_refused_before_connection(self):
  devices=[SimpleNamespace(serial='one',is_usb=True),SimpleNamespace(serial='two',is_usb=True)]
  with patch('pymobiledevice3.usbmux.list_devices',new_callable=AsyncMock,return_value=devices),patch('pymobiledevice3.lockdown.create_using_usbmux',new_callable=AsyncMock) as create:
   with self.assertRaises(RuntimeError):asyncio.run(config.choose_device())
   create.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
