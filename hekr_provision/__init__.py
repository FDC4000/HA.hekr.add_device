"""hekr_provision — reverse-engineered Hekr/Wisen device provisioning toolkit.

Modules:
  airkiss     — SmartConfig/AirKiss length-encoder (HekrAirKissEncoder port)
  softap      — SoftAP exchange with the device at 192.168.4.1:7001
  get_pincode — fetch the provisioning pinCode from the Hekr cloud
"""
from . import airkiss, get_pincode, softap

__all__ = ["airkiss", "get_pincode", "softap"]
__version__ = "1.0.0"
