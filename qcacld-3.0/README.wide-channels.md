# Onyx compiled channel profile

The sun_gki_wcn7750 profile enables CONFIG_WLAN_WIDE_CHANNELS=y. This is
inside qca_cld3_wcn7750.ko; it requires no boot script, INI edit, app command
or module parameter. It covers startup, Android/11d country updates and
firmware restart, using local requests without overwriting caller arguments.

The profile requests all three bands:

- Firmware FCC8_WORLD (0x09) supplies channels 1–13 and 5 GHz channels
  36–64, 100–144 and 149–177.
- Channel 14 uses WMI_PDEV_SET_REGDOMAIN_CMDID to request MKKA on 2.4 GHz
  and FCC8 on 5 GHz, preserving the returned DFS region. No existing domain
  pair combines these. The compiled host mapping matches this combination.
- With CONFIG_BAND_6GHZ and firmware 6 GHz capability present, the request
  also supplies FCC1_6G_09 (0x09), the full-range LPI/SP super-domain used by
  the existing US country entry. Firmware without that capability receives
  a 2.4/5 GHz request and a diagnostic, preserving those bands.

For channel 14, firmware RF capabilities must include 2484 MHz and 802.11b.
The driver allocates a replacement rule array, queues the per-band command,
then appends a 2474–2494 MHz rule with 20 MHz bandwidth, 20 dBm power and
NO_OFDM. Existing rules remain intact. Failed allocation, failed command
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

Build/validation records: /home/loukious/Android/mowa-cfr/all-bands-20261009.
Run the portable source tests from this WLAN repository root:

    python3 qcacld-3.0/tests/test-wide-channels.py

Tests compile actual source with the option disabled, enabled without 6 GHz,
and enabled with 6 GHz. They exercise command errors, allocation/ownership,
RF gates, malformed counts, per-PHY routing, bounded re-entry, country-reset
bookkeeping, power/flag preservation and MLME/scan overrides. The option
requires CONFIG_REG_CLIENT=y. Set CONFIG_WLAN_WIDE_CHANNELS=n and rebuild
to restore normal selection.

The restarted phone still had the original ROM driver, SHA-256
53679567e1977a410c761d80879dc4773bc8bd515e4d41a9fc35d5a6072c322d.
Neither source profile has been loaded. After packaging the new driver
into the ROM's boot-time module location and booting it, use adb.exe to
check its module hash, kernel profile/channel-14 diagnostics, iw reg get,
iw phy phy0 info, scan results and actual connection behavior.

Builds and host tests do not verify firmware acceptance or RF operation.
Merely displaying 6 GHz entries in iw is insufficient. The sensing decoder
currently handles the observed 80 MHz HE/VHT CFR formats; an 802.11b
channel-14 connection is not that CSI format.
