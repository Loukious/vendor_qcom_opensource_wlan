# WCN7750 monitor channel and boot configuration

The monitor driver supports stock WEXT `SIOCSIWFREQ` channel selection through
the existing cfg80211 monitor path. Same-primary requests preserve the full
active channel; different supported primaries use the existing handoff and
channel-readback checks. WEXT channel support does not provide independent
simultaneous channels on the internal radio.

Shared monitors also accept a compatible narrower cfg80211 channel definition
without retuning the live owner. Receive pause is cleared when arming a new
monitor generation after teardown, and failed monitor opens return Linux
errors instead of successful netlink acknowledgments with the interface down.

Experimental coexistence parameters remain disabled by default and read-only
after loading. To opt in with Android's native modprobe, include this line in
the matched ROM image's `lib/modules/modules.options` beside the driver:

```text
options qca_cld3_wcn7750 sta_monitor_coexist=1 ap_monitor_coexist=1 sta_ap_monitor_coexist=1
```

A matched native Onyx installation loaded the qualified driver and all three
options after fastbootd flashing and reboot with the optional KernelSU Next WLAN
manager removed. Wi-Fi reconnected with background scanning enabled. The
Android 17 / 6.18 kernel port maintains its own ABI adaptations and matching
image layout; this driver branch still requires a compatible kernel build.

See the [kernel-port validation](https://github.com/Loukious/onyx-android17-6.18/blob/android17-6.18-lts/validation/wlan-native-fastboot-20261112.md)
for build checks, bounded monitor-restart/capture results and native boot
configuration. Device-specific logs, partition images and captures are not
part of this source repository.
