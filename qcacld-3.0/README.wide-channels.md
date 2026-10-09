# Onyx compiled channel profile

The sun_gki_wcn7750 profile enables CONFIG_WLAN_WIDE_CHANNELS=y. This is
inside qca_cld3_wcn7750.ko; it requires no boot script, INI edit, app command
or module parameter. It covers startup, Android/11d country updates and
firmware restart, using local requests without overwriting caller arguments.

The profile requests all three bands:

- Firmware FCC15_FCCA (0xea) and FCC1_6G_18 (0x18) form the matching
  pair in this handset's installed firmware database. Native WMI tests
  returned 6 GHz AP/client rules for this combination, including the
  5925–7125 MHz LPI client rule. FCC8_WORLD (0x09) with super-domain 0x09
  or 0x18 returned no 6 GHz rules. The older host US entry uses different
  identifiers and must not be substituted for the observed firmware pair.
- Channel 14 uses WMI_PDEV_SET_REGDOMAIN_CMDID to request MKKA on 2.4 GHz
  and FCC8 on 5 GHz, preserving the returned DFS region. No existing domain
  pair combines these. The compiled host mapping matches this combination.
- With CONFIG_BAND_6GHZ and firmware 6 GHz capability present, the request
  supplies FCC1_6G_18. Firmware without that capability receives
  a 2.4/5 GHz request and a diagnostic, preserving those bands.

For channel 14, firmware RF capabilities must include 2484 MHz and 802.11b.
The driver allocates a replacement rule array, queues the per-band command,
then appends a 2474–2494 MHz rule with 20 MHz bandwidth, 20 dBm power and
NO_OFDM. After successful command submission it extends the base 2.4 GHz
rule through 2482 MHz so channels 12/13 remain available with MKKA; the US
base rule ends at channel 11. Existing power, bandwidth and flags remain
intact. Failed allocation, failed command
submission, unsupported RF capability or excessive rule counts leaves the
original array unchanged and logs the reason. Per-PHY bookkeeping bounds
command submission to once per country request, including repeated events.
Command submission is not an RF-operation acknowledgement. Channel 14
remains experimental until a real scan/connection succeeds. Existing SME
code selects 802.11b at 2484 MHz.

The profile enables all-band MLME selection, bypasses Xiaomi's platform
2.4/5-only branch and OEM ranging restriction, and scans all 6 GHz channels
instead of the Onyx INI's no-6-GHz mode. Firmware/BDF band and frequency
capabilities, disabled channels, passive scan and 6 GHz security checks
remain authoritative. Ordinary profiles retain their existing behavior.

DFS/radar, non-occupancy lists, indoor and bandwidth limits, AFC,
coexistence, SAR, calibration and thermal handling remain active. FCC8 uses
firmware's FCC DFS region rather than TN's ETSI region. Legacy and extended
channel-list events cap profile power at 20 dBm for 2.4 GHz and 23 dBm for
5 GHz, or lower firmware limits. Firmware supplies 6 GHz power and PSD
limits. This is a compiled lab profile, not a Tunisia database update.
4.9 GHz is not added.

6 GHz remains a hardware/firmware experiment. The
[Xiaomi POCO F7 specification](https://www.mi.com/uk/product/poco-f7/specs/)
lists 2.4/5 GHz, while the
[Qualcomm Snapdragon 8s Gen 4 brief](https://www.qualcomm.com/content/dam/qcomm-martech/dm-assets/documents/Product-Brief-Snapdragon-8s-Gen-4.pdf)
lists 2.4/5/6 GHz platform capability. Platform capability does not establish
that this handset's RF components and board firmware implement 6 GHz.
The host database spans 5925–7125 MHz. Its LPI client rules split at
6875 MHz, inside channel 185, so the database coverage check does not
claim that channel fits one 20 MHz rule. Actual firmware rules determine
its usability; this profile does not replace 6 GHz power/PSD rules.

Firmware tests: /home/loukious/Android/mowa-cfr/firmware-inspection-20261009/round3.
Build/validation records: /home/loukious/Android/mowa-cfr/native-6ghz-20261009.
Run the portable source tests from this WLAN repository root:

    python3 qcacld-3.0/tests/test-wide-channels.py

Tests compile actual source with the option disabled, enabled without 6 GHz,
and enabled with 6 GHz. They exercise command errors, allocation/ownership,
RF gates, malformed counts, per-PHY routing, bounded re-entry, country-reset
bookkeeping, power/flag preservation and MLME/scan overrides. The option
requires CONFIG_REG_CLIENT=y. Set CONFIG_WLAN_WIDE_CHANNELS=n and rebuild
to restore normal selection.

The previous installed profile requested 0x09/0x09 and enabled channel 14,
but left every 6 GHz channel disabled. The corrected driver was packaged
into vendor_dlkm_a and booted on 2026-10-09. Runtime tests with adb.exe
verified all 59 standard 6 GHz channels enabled, channels 1–14 retained,
and the same result after framework country updates. The firmware completed
a passive scan at 5955 MHz and returned channel statistics. ASUS 5 GHz
connectivity and internet remained functional; the native app recorded
129 supported HE/VHT 80 MHz CFR records in its ten-second recording window.
These results establish configuration and scan-path acceptance, but a
6 GHz AP connection has not been tested.

The installed firmware reports the 5.9 GHz service absent, but its rules
cover channels 169/173/177. Native passive scans initially failed while
those frequencies were absent from the firmware scan table. Supplying
those channels made the scans complete. Subsequent native active scans
with wildcard probes on all three channels also completed with nonzero
firmware transmit statistics, matching the channel-165 control. Normal
country processing restored the full table after each diagnostic test.

The compiled client lab profile therefore retains the already filtered
firmware channel list for 5.9 GHz when regulatory data is offloaded,
the current pair is FCC15_FCCA and the firmware service bit is absent.
It adds no passive-only restriction. Firmware rules, RF-range, band,
indoor, NOL and later bandwidth exclusions remain intact; existing flags,
power and bandwidth are not cleared or increased. The firmware capability
bit stays unchanged. Ordinary profiles and targets with the capability
present keep their existing behavior. No signed firmware or board data
is modified. After flashing, ordinary active iw scans on all three channels
completed with transmit statistics; framework country updates retain them
without NO_IR along with channel 14 and all 59 standard 6 GHz channels.
Local-only AP startup at 20 MHz also succeeds at all three requested
frequencies. With the companion hostapd AIDL secondary-channel fix,
all three also start at 80 MHz, centered at 5855 MHz. That source is in
Loukious/android_external_wpa_supplicant_8, branch mowa-5dot9-hotspot-20261009;
the compiled KSU module mowa-hostapd-5dot9 is installed and its mount
verified after reboot. Association, peer data traffic and CSI on these channels
still require a compatible second device test. Active scan completion and
firmware transmit statistics do not independently verify reception or
all channel widths/rates. Evidence is in
/home/loukious/Android/mowa-cfr/active-5dot9-20261009.
The special lower 6 GHz edge channel (5935 MHz, channel 2) is also gated
by its separate firmware service capability and remains disabled.

Run the 5.9 GHz filter tests with:

    python3 qcacld-3.0/tests/test-wide-5dot9.py

Builds and host tests do not verify firmware acceptance or RF operation.
Merely displaying 6 GHz entries in iw is insufficient. The sensing decoder
currently handles the observed 80 MHz HE/VHT CFR formats; an 802.11b
channel-14 connection is not that CSI format.
