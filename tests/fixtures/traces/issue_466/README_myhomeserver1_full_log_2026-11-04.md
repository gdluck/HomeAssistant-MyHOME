# BTicino 3488 HOMETOUCH (fw 3.2.5, initially configured as MyHomeServer1) — full Home Assistant debug log, 2026-11-04 (#466)

The endpoint answering OpenWebNet on port 20000 is a BTicino **3488 HOMETOUCH** 7" touch screen
running SMARTDES firmware `3.2.5` (initially configured under the `MyHomeServer1` profile and later
switched to `Generic`). Live Bus 2 verification and the `3488/030205` firmware oracle confirm that
the `3488` ships its own `openserver` on TCP port 20000 (`IsGateway=1`, `ForceHMAC=1`) and replies
with WHO 13 device type `200`, firmware `3.2.5`, and WHO 1013 `OBJECT_MODEL = 128`.

`MyHomeServer1_full_debug_log_2026-11-04T10-30-17.txt`: the reporter's complete
`home-assistant_myhome` log (4935 lines, 11:27:00 → 12:30:11 local, exported 10:30:17Z), verbatim
from the first `custom_components.myhome` line. Only the container start-up boilerplate above it is
left out. The gateway address and MAC were made synthetic (`192.0.2.9`, `00:03:50:00:11:04`, keeping
the BTicino OUI), and an unrelated LAN host in two `aioshelly` error lines became `192.0.2.26`;
nothing else was changed. No password is echoed in the log.

What it carries:

- **Identification** (INFO lines, 11:29:18): `Auto-detected gateway firmware 3.2.5 via WHO=13 Dimension
  16`, WHO 13 device type `200`, model code `1013-1-128` (BTicino `3488` HOMETOUCH).
- **Profile switch** (11:44:36): the entry is re-configured from the `MyHomeServer1` profile to
  `Generic`; all DEBUG bus traffic that follows runs under the Generic profile on `3488` hardware.
- **1374 inbound frames** (11:47:38 → 12:30:11): 950 WHO 4 thermoregulation (zone actuator state,
  setpoints, manual mode `4002`), 349 WHO 1 lighting with four-digit WHERE, 44 WHO 7 video and 29 WHO 8
  door-entry frames from the 3488's video door-entry functions (12:27–12:30), and two undocumented
  `*#130**1*6*3*2*5##` broadcasts.
- **OWNd parse coverage, identical on 2.0.0b13 and dev:** 1338 of 1374 parse (752 `OWNHeatingEvent`,
  198 `OWNHeatingCommand`, 349 `OWNLightingEvent`, 29 `OWNIntercomEvent`, 10 base `OWNEvent`). The
  36 that do not are all WHO 7 **event forms with the WHERE field absent**, `*7*WHAT*##` —
  `*7*73#1#100*##`, `*7*300#127#0#0#1#5000#2*##`, `*7*0*##`, `*7*219*##`, `*7*55*##`, ... — one star
  short of the documented `*7*WHAT*WHERE*##`; OWNd accepts the documented address-less release form
  `*7*9**##` but returns `None` for these; MyHOME logs each as `Data received is not a message` (45 such lines). The WHO 7
  dimension forms (`*#7**20*…`, `*#7**31#…`) and the two event forms that carry a WHERE parse. OWNd
  PR #162 (camera WHERE zero-padding) does not change this.
- The gateway echoes the dimension **write** form `*#4*Z#N*#20*V##` immediately before the `*20*`
  read form; MyHOME logs the write form as unsupported and takes zone state from the read form.

Relationship to `myhome_sweep_MyHomeServer1_all_2026-11-04T09-35-58.json`: same gateway and
morning, but that export is a 200-frame Bus Monitor buffer window (09:35:17 → 09:35:43Z) under the
`MyHomeServer1` profile, before DEBUG logging was on; the two do not overlap, so both are kept.

Pinned by `tests/test_issue_466_3488_hometouch_full_log_2026_11_04_trace.py` (SHA-256 provenance).
