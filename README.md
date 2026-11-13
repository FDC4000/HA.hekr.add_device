# HA.hekr.add_device

Reverse-engineered **device-provisioning toolkit** for the Wisen / Hekr-Hummingbird
IoT platform (`me.hekr.hummingbird`). It reproduces, in pure-Python, how the mobile
app onboards a new device onto the user's local Wi-Fi and binds it to the account.

> Rebuilt by static analysis (jadx) of the Wisen 1.9.1 APK. **For research and
> authorised testing only** — use solely against hardware/accounts you own or are
> permitted to provision. Credentials in the SoftAP/SmartConfig channels are
> transmitted in cleartext (see Security notes).

## The chain

```
login ──► get_pincode ──► airkiss / softap ──► (cloud) getNewDeviceList → bound
```

1. **login** — `POST {UAA}/login` → `access_token` / `refresh_token`
2. **get_pincode** — `GET {USER}/getPINCode?ssid=` (Bearer) → 6-char `PINCode`
3. **provision** — hand `ssid` / `password` / `pinCode` to the device:
   - **airkiss** (SmartConfig): UDP frame *lengths* encode the data to multicast `224.127.*.255:7001`
   - **softap**: cleartext `ssid=…&password=…&pinCode=…&end` to `192.168.4.1:7001`
4. the device joins the Wi-Fi, registers with the pinCode, and the app's
   `getNewDeviceList?pinCode=&ssid=` poll returns it bound to the account.

## Layout

```
hekr_provision/
├── login.py        POST {UAA}/login + token/refresh   (HekrUser.login)
├── get_pincode.py  GET getPINCode?ssid=                (HekrUserAction.getPinCode)
├── airkiss.py      SmartConfig length-encoder          (HekrAirKissEncoder)
├── softap.py       SoftAP exchange @192.168.4.1:7001   (CommonDeviceConfig)
└── cli.py          unified command-line entry point
```

See `hekr_provision/README.md` for the detailed flow, byte formats and sequence diagram.

## Usage

```bash
export PYTHONPATH=.

# 1) log in  ->  access_token
python3 -m hekr_provision.cli login --username <acct> --password <pw>

# 2) provisioning pinCode for the target SSID
python3 -m hekr_provision.cli pincode --token <access_token> --ssid MyWiFi

# 3a) SmartConfig: build (and optionally --send) the packet lengths
python3 -m hekr_provision.cli smartconfig --ssid MyWiFi --password <wifi_pw> --pin <pinCode>

# 3b) SoftAP: exchange with the device (phone must be on the device AP)
python3 -m hekr_provision.cli softap --ssid MyWiFi --password <wifi_pw> --pin <pinCode>
```

Every module also has a no-network self-test: `python3 hekr_provision/<module>.py --selftest`
(airkiss prints a structure summary instead).

## Security notes

- 🔸 **Cleartext credentials** in SoftAP (`password=` over HTTP/TCP) and only
  length-obfuscated in SmartConfig (passively recoverable over the air).
- 🔸 **Multicast leak** — AirKiss frames reach any device in pairing mode in range.
- 🔸 **pinCode is the sole binding secret** — verify server-side it is tied to the
  requesting token.
- 🔸 Regions: `asia` (hekr.me), `america` (hekrus.me), `europe` (hekreu.me), `test`.
