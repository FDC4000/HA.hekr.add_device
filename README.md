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
├── provision.py    end-to-end chain (login→pin→config)
└── cli.py          unified command-line entry point
```

See `hekr_provision/README.md` for the detailed flow, byte formats and sequence diagram.

## Install

```bash
pip install -e .            # installs the `hekr-provision` console command
hekr-provision --help
```

Pure standard library, no third-party dependencies (Python ≥ 3.8). Without installing,
run from the repo root with `PYTHONPATH=.` and `python3 -m hekr_provision.cli …`.

## Tests

35 tests, standard-library `unittest`, fully offline (local mock HTTP servers and a
mock device AP — no hardware or network):

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -t .
```

Coverage: AirKiss CRC-8 + structure/round-trip, SoftAP payload & `devConfig` parsing,
pinCode fetch (success / 401 / bad length / non-JSON), login + token refresh + JWT uid,
the end-to-end `provision` chain, and CLI dispatch.

## Usage

```bash
export PYTHONPATH=.
# ── end-to-end (login -> pinCode -> provision) in one go ──
python3 -m hekr_provision.cli provision \
    --username <acct> --password <pw> \
    --ssid <ssid> --wifi-password <wifi_pw> --method softap

# ── or step by step ──
# 1) log in  ->  access_token
python3 -m hekr_provision.cli login --username <acct> --password <pw>

# 2) provisioning pinCode for the target SSID
python3 -m hekr_provision.cli pincode --token <access_token> --ssid <ssid>

# 3a) SmartConfig: build (and optionally --send) the packet lengths
python3 -m hekr_provision.cli smartconfig --ssid <ssid> --password <wifi_pw> --pin <pinCode>

# 3b) SoftAP: exchange with the device (phone must be on the device AP)
python3 -m hekr_provision.cli softap --ssid <ssid> --password <wifi_pw> --pin <pinCode>

# ── actually onboard a device over the air (SmartConfig broadcast) ──
# This is the real call that bound a device. The laptop/phone MUST be joined to
# the 2.4 GHz band of <ssid> while broadcasting (the device only does 2.4 GHz).
# Put the device into pairing mode first; it usually catches the credentials
# within the first pass and leaves pairing mode on success.
python3 -m hekr_provision.cli provision \
    --username <acct> --password <pw> \
    --ssid <ssid> --wifi-password <wifi_pw> \
    --method smartconfig --region europe --send
```

`provision` accepts `--token`/`--pin` to skip the login/pinCode steps, `--method smartconfig`
(with `--send` to broadcast), and `--region {asia,america,europe,test}`.

Every module also has a no-network self-test: `python3 -m hekr_provision.<module> --selftest`
(airkiss prints a structure summary; provision runs the whole chain against local mocks).

## Parameters

Shared placeholders: `<acct>`/`<pw>` = Hekr **account** login; `<ssid>`/`<wifi_pw>` =
the **target Wi-Fi** the device should join; `<pinCode>` = the 6-char provisioning code.

### `provision` — end-to-end (login → pinCode → SmartConfig/SoftAP)

| Flag | Default | Description |
|------|---------|-------------|
| `--username` | — | Hekr account (phone/email); omit if `--token` given |
| `--password` | — | Hekr account password; omit if `--token` given |
| `--ssid` | *(required)* | target Wi-Fi SSID the device should join |
| `--wifi-password` | `""` | target Wi-Fi password |
| `--method` | `softap` | `softap` or `smartconfig` |
| `--token` | — | reuse an `access_token` (skip the login step) |
| `--pin` | — | reuse a `pinCode` (skip the getPINCode step) |
| `--pid` | `00000000000` | product id (UAA login field; placeholder from Wisen config) |
| `--region` | `asia` | `asia` / `america` / `europe` / `test` |
| `--host` | `192.168.4.1` | SoftAP device host |
| `--port` | `7001` | SoftAP / SmartConfig port |
| `--http` | off | SoftAP: HTTP POST instead of raw TCP |
| `--attempts` | `60` | SoftAP: `devConfig` read attempts |
| `--send` | off | SmartConfig: actually UDP-broadcast (otherwise a dry run) |
| `--repeat` | `3` | SmartConfig: broadcast passes (~21 s each; 3 ≈ 1 min) |

### `login` — authenticate to Hekr UAA, print `access_token`

| Flag | Default | Description |
|------|---------|-------------|
| `--username` | — | phone/email/account |
| `--password` | — | password |
| `--pid` | `00000000000` | product id |
| `--region` | `asia` | `asia` / `america` / `europe` / `test` |
| `--base-url` | — | override `BASE_UAA_URL` (wins over `--region`) |
| `--refresh` | — | refresh an existing `refresh_token` instead of logging in |

### `pincode` — fetch the provisioning pinCode from the cloud

| Flag | Default | Description |
|------|---------|-------------|
| `--token` | *(required)* | user Bearer `access_token` |
| `--ssid` | *(required)* | target SSID |
| `--base-url` | `https://user-openapi.hekr.me/` | USER API base |

### `smartconfig` — build / broadcast AirKiss packet lengths

| Flag | Default | Description |
|------|---------|-------------|
| `--ssid` | *(required)* | target SSID |
| `--password` | *(required)* | target Wi-Fi password |
| `--pin` | *(required)* | pinCode |
| `--send` | off | actually UDP-broadcast the lengths (otherwise a dry run) |
| `--port` | `7001` | multicast port |
| `--repeat` | `3` | broadcast passes (~21 s each; 3 ≈ 1 min) |

### `softap` — exchange with the device AP at `192.168.4.1:7001`

| Flag | Default | Description |
|------|---------|-------------|
| `--ssid` | *(required)* | target SSID |
| `--password` | *(required)* | target Wi-Fi password |
| `--pin` | *(required)* | pinCode |
| `--host` | `192.168.4.1` | device AP host |
| `--port` | `7001` | device AP port |
| `--http` | off | HTTP POST instead of raw TCP |
| `--attempts` | `60` | `devConfig` read attempts |

## Security notes

- 🔸 **Cleartext credentials** in SoftAP (`password=` over HTTP/TCP) and only
  length-obfuscated in SmartConfig (passively recoverable over the air).
- 🔸 **Multicast leak** — AirKiss frames reach any device in pairing mode in range.
- 🔸 **pinCode is the sole binding secret** — verify server-side it is tied to the
  requesting token.
- 🔸 Regions: `asia` (hekr.me), `america` (hekrus.me), `europe` (hekreu.me), `test`.
