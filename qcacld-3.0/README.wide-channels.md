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
cover channels 169/173/177. Direct passive scan tests initially failed while
those frequencies were absent from the firmware scan table. After a
temporary table update, all three scans completed and returned channel
statistics. The normal table was restored after the test.

The compiled client lab profile therefore retains otherwise permitted
5.9 GHz channels as passive (NO_IR) when regulatory data is offloaded and
the current pair is FCC15_FCCA. It does not revive channels excluded by
firmware rules, RF range, band selection, indoor policy or NOL. It preserves
power/bandwidth/other flags, does not grant master mode even if that INI is
enabled, and leaves the firmware capability bit unchanged. Ordinary profiles
and targets with the capability present keep their existing behavior.
This does not modify signed firmware or board data. Passive scanning is
verified; association, transmission and CSI on these channels still need
a compatible access point test. After installing the rebuilt module,
ordinary iw passive scans at 5845/5865/5885 MHz all visited the requested
frequency, returned statistics and completed. Framework US/GB updates and
clearing the override preserve 14 enabled 2.4 GHz channels, 28 enabled
5 GHz channels (169/173/177 passive), and 59 standard 6 GHz channels.
Return probes still report the 5.9 GHz firmware capability as absent.
ASUS 5260 MHz internet and app capture regression passed: 130 supported
HE/VHT80 records in the ten-second recording window, none unsupported.
Evidence is in
/home/loukious/Android/mowa-cfr/5dot9-investigation-20261009.
The special lower 6 GHz edge channel (5935 MHz, channel 2) is also gated
by its separate firmware service capability and remains disabled.

Run the passive 5.9 GHz filter tests with:

    python3 qcacld-3.0/tests/test-wide-5dot9.py

Builds and host tests do not verify firmware acceptance or RF operation.
Merely displaying 6 GHz entries in iw is insufficient. The sensing decoder
currently handles the observed 80 MHz HE/VHT CFR formats; an 802.11b
channel-14 connection is not that CSI format.
