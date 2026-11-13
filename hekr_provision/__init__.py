"""hekr_provision — reverse-engineered Hekr/Wisen device provisioning toolkit.

Modules:
  login       — authenticate to Hekr UAA (access_token / refresh_token)
  get_pincode — fetch the provisioning pinCode from the Hekr cloud
  airkiss     — SmartConfig/AirKiss length-encoder (HekrAirKissEncoder port)
  softap      — SoftAP exchange with the device at 192.168.4.1:7001
"""
from . import airkiss, get_pincode, login, softap

__all__ = ["airkiss", "get_pincode", "login", "softap"]
__version__ = "1.0.0"
