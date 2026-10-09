# Onyx compiled channel profile

The `sun_gki_wcn7750` profile enables `CONFIG_WLAN_WIDE_CHANNELS=y` for the
Onyx lab build. This is a change inside `qca_cld3_wcn7750.ko`; it requires
no boot script, country-code module parameter, app command, or INI override.

On driver startup, HDD uses the existing regulatory API to request
`FCC8_WORLD` (`0x09`) from firmware. Both country-command paths in the target
interface also select that domain, covering subsequent Android country
updates, 11d updates, and restoration after a firmware restart. Requests use
local structures: the original country arguments are not overwritten.

The driver database pairs the WORLD 2.4 GHz domain (channels 1–13) with
FCC8 on 5 GHz: channels 36–64, 100–144 and 149–177. This is a compiled lab
domain selection, not an update to the Tunisia country database. Firmware
must recognize the domain and return its channel rules; the host does not
fabricate enabled channels or clear disabled flags after the fact.

The actual available set can be narrower than the database profile:

- Hardware frequency ranges, firmware/BDF band and 5.9 GHz capability
  checks remain active. Channels 169–177 also retain the existing passive
  and indoor handling; support for them is not guaranteed.
- DFS/radar, non-occupancy lists, indoor restrictions, bandwidth limits,
  coexistence filtering, SAR, calibration and thermal handling remain active.
  FCC8 selects the firmware's FCC DFS region instead of the TN ETSI region.
- For firmware rules identifying FCC8_WORLD, both legacy and extended
  channel-list events cap host regulatory power at the observed TN ceilings:
  20 dBm for 2.4 GHz and 23 dBm for 5 GHz. Lower firmware limits are retained.
  Board limits and SAR can impose additional reductions.
- Channel 14, 4.9 GHz and 6 GHz are not enabled. The request's 6 GHz
  super-domain is zero. This profile does not claim universal RF support.

The option is enabled only in `sun_gki_wcn7750_defconfig`. To return to normal
country selection, set `CONFIG_WLAN_WIDE_CHANNELS=n` there and rebuild, or
pass that value on the direct kernel module make command. Other profiles
leave the option unset and retain their normal country behavior.

Build and validation artifacts for the local change are in
`/home/loukious/Android/mowa-cfr/wide-channels-20261009`. The full module build
passed against the same ABI symbol tables used for the flashed ROM. The
complete `__versions` table matches the earlier working module, and CFR
streamfs/relay support remains in the binary. Host tests compile the actual
changed request/startup functions with the feature enabled and disabled,
exercise missing handles and firmware command failures, verify reference
release and caller argument preservation, and check power caps without
changing DFS/indoor flags or unrelated fields.

Run the portable source checks from the WLAN repository root:

```sh
python3 qcacld-3.0/tests/test-wide-channels.py
```

The ROM's Onyx INI also explicitly disables 6 GHz with `BandCapability=3`
and `oem_6g_support_disable=1`. This change covers its existing 2.4/5 GHz
bands; enabling and validating 6 GHz would require addressing that separate
OEM configuration and confirming board/firmware support.

Firmware acceptance and hotspot discovery have not been tested with this
module loaded. After packaging it into the boot-time module location and
booting the updated ROM, check with `adb.exe`:

```sh
adb.exe -s 5493f3c6 shell 'su -c "dmesg | grep -i wide-channel"'
adb.exe -s 5493f3c6 shell 'su -c "iw reg get; iw phy phy0 info"'
adb.exe -s 5493f3c6 shell 'su -c "cmd wifi start-scan"'
adb.exe -s 5493f3c6 shell 'su -c "cmd wifi list-scan-results"'
```

Confirm that `phy#0` has the broader channel rules, supported high channels
are enabled, DFS flags and power caps remain, and the `PC` hotspot appears.
If firmware rejects the domain or returns the original narrow list, the
patch is not a verified channel unlock; retain the logs for diagnosis.
