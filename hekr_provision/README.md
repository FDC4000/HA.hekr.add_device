# hekr_provision

Reverse-engineered device-provisioning toolkit for the **Wisen / Hekr-Hummingbird**
IoT app (`me.hekr.hummingbird`, v1.9.1). It reproduces, in Python, how the app
onboards a new device onto the user's local Wi-Fi.

> Rebuilt by static analysis (jadx) of `CommonDeviceConfig`, `HekrAirKissEncoder`,
> `ConfigPresenter` and `HekrUserAction`. **For research / authorised testing only** —
> use solely against hardware you own or are permitted to provision.

---

## The onboarding flow

```
 ┌────────┐         ┌──────────────┐        ┌────────────┐        ┌─────────┐
 │  App   │         │  Hekr Cloud  │        │  New Device│        │  Router │
 └───┬────┘         └──────┬───────┘        └─────┬──────┘        └────┬────┘
     │ 1. GET getPINCode?ssid=  (Bearer token)    │                    │
     │─────────────────────►│                     │                    │
     │   pinCode            │                     │                    │
     │◄─────────────────────│                     │                    │
     │                                            │                    │
     │ 2a. SmartConfig: UDP frames whose LENGTHS encode ssid/pw/pin    │
     │    to multicast 224.127.<n>.255:7001  ─ ─ ─►│ (sniffs lengths)  │
     │                 ── or ──                    │                    │
     │ 2b. SoftAP: "ssid=..&password=..&pinCode=..&end"                 │
     │    over TCP/HTTP to 192.168.4.1:7001  ─────►│                    │
     │    {"action":"devConfig","params":{devTid,STEP,code,PIN,bind}}  │
     │◄───────────────────────────────────────────│                    │
     │                                            │ 3. join Wi-Fi ────►│
     │                                            │ 4. register (pin)  │
     │                                            │───► cloud          │
     │ 5. poll getNewDeviceList?pinCode=&ssid= (Bearer)                 │
     │─────────────────────►│  [{devTid, bindResultCode:0}]            │
     │◄─────────────────────│  → device bound to the account           │
```

The **pinCode** (fetched in step 1 with the user's token) is the glue: the device
registers with it, and `getNewDeviceList?pinCode=` returns the freshly-bound device
to the right account. There is no separate explicit bind call in this path.

---

## Modules

| File | Reproduces | Key API |
|---|---|---|
| `airkiss.py` | `HekrAirKissEncoder` (SmartConfig length-encoding, Maxim CRC-8 `0x8C`) | `HekrAirKissEncoder(ssid, password, pin).get_encoded_data()`, `broadcast()` |
| `softap.py` | `CommonDeviceConfig.SoftAPAsyncTask` / `handlerConfigFromAP` | `provision_softap()`, `build_payload()`, `parse_dev_config()`, `get_pin_code()` |
| `cli.py` | — | unified command-line entry point |

### SmartConfig encoder (`airkiss.py`)
`get_encoded_data()` returns a list of **UDP packet lengths** (not bytes). A device
in Wi-Fi monitor mode measures the frame lengths to recover the data. Frame layout
(repeated 5×): `leadingPart` → `magicCode` (len+CRC8(ssid)) → 15× (`prefixCode` +
length-encoded `password+pinCode` in CRC-checked 4-byte sequences). The SSID string
itself is **not** transmitted — only its length and CRC8.

### SoftAP exchange (`softap.py`)
Joined to the device's own AP, the app sends (every 1 s, cleartext)
`ssid=…&password=…&pinCode=…&end` to `192.168.4.1:7001` over raw TCP (or HTTP POST),
and accepts the first `devConfig` reply where **`PIN` matches** the sent pinCode and
**`bind != 0`**; `code == 200` means the step succeeded.

---

For installation, CLI usage, the full parameter reference and security notes,
see the [project README](../README.md).

