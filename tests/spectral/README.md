# Spectral configuration regression checks

Run from the WLAN repository root:

```sh
python3 -m unittest discover -s tests/spectral -v
```

The test compiles the two actual WMI sender functions from
`target_if_spectral.c` against a fake host and WMI sink. It exhausts 256
combinations of requested and available four-chain masks, checks a stale zero
mask is recovered and committed only after a successful submission, and
injects WMI failures and missing-vdev failures. No radio or device is used.
The harness does not verify firmware behavior, the entire kernel integration,
or asynchronous report/timer behavior. Kbuild remains required.

`test_finite_completion.py` compiles the actual completion and stop functions
against a fake host/WMI sink. On WCN7750, completing the requested finite
report count clears the local active/enabled cache before notifying userspace.
This reflects firmware's finite-completion stop and avoids a redundant WMI
stop. Partial completion and other targets keep their existing state; failed
userspace notification still retires the completed scan. The harness also
checks that an immediate stop emits no WMI writes after this completion.
The two controlled no-host-stop tests remained crash-free for about 44 seconds
each, but this source correction still needs device validation after Kbuild.
It does not repair the observed zero FFT bins.

The source correction addresses host defects found during WCN7750 spectral
debugging:

- A get-config query can initialize cached defaults with a zero mask before
  HDD initializes the vdev mask at scan startup. Updating the vdev alone does
  not refresh those defaults.
- The WMI callbacks return QDF status, while the surrounding cache writer
  expects negative OS errors. Positive QDF failures were treated as success.
- Configuration/start callers discarded return values and could report
  success or request activation after an earlier failure.

The corrected path rejects unavailable RX chains, recovers stale zero masks
from the initialized vdev, keeps the cache consistent with successfully
submitted settings, and propagates failures. If startup fails after finite
scan initialization, timer cancellation runs after releasing spectral_lock.

These are host correctness fixes. They have not been shown to resolve the
observed zero FFT bins or WPSS crashes. WMI submission success is not a
firmware acknowledgement. Do not use a successful CI build as evidence that
the current firmware is safe to scan, and do not hot-replace the permanent
WLAN module. Deployment needs a separately reviewed boot/recovery plan and
an ABI comparison with the installed modules.

### WCN7750 mode-2 in-band FFT length hypothesis

`test_wcn7750_inband_bins.py` validates the experimental WCN7750-only
`inband_fftbin_size_adj` flag and the existing report-mode-2 conditional.
This branch is based on the separate *untested on-device* finite-completion
revision (`b38a22e`). Earlier mode-2 FFT9 capture exported 512 bins, but
all 74 clipped 255-valued samples were in the upper half; mode 3 had no
clipped values. This resembles Qualcomm's documented report-mode-2 condition
where firmware DMA-transfers only in-band bins despite a full advertised
length. Neither source tests nor successful compilation prove the WCN7750
firmware requires this adjustment. Do not flash this build merely because
CI passed; assess descriptor lengths and the independent completion change.

### FFT bin-size memory safety and missing WMI DBR length

`test_fft_bin_size_storage.py` verifies the size_t output of
`target_if_spectral_get_bin_count_after_len_adj()` is stored in a genuine
`size_t` temporary before converting to the `uint8_t` field. The previous
`(size_t *)&p_sfft->fft_bin_size` writes eight bytes starting at offset 60,
corrupting four bytes of the neighboring bin pointer at offset 64 (64-bit).

`test_wcn7750_dbr_length_semantics.py` verifies why `dbr_len=0` in the
spectral callback is not evidence of zero actual RF samples: the WMI DMA
release TLV only transports a physical address, and the host decoder
never populates the intermediate `len` field. Diagnose actual payloads
using the embedded GEN3 FFT report length; do not reject zero dbr_len
or assume it denotes no DMA transfer.

### Spectral ring-buffer capacity audit

`test_dbr_capacity_audit.py` validates a one-time informational trace when
Qualcomm configures the Spectral DMA ring. The logged `buf_size` is the
**allocated and firmware-advertised ring-buffer capacity**, not bytes
transferred in a particular DMA completion. The WMI release TLV has no
usable payload length. This diagnostic does not enable RF scanning, debug
poisoning, firmware asserts or active tracing; it runs during normal ring
configuration, and it doesn't change the WMI command sent to firmware.

### GEN3 spectral direct DMA buffer bounds

`test_gen3_dbr_bounds.py` extracts the **actual production C bounds-check
helper** and runs it under GCC/UBSan with a 2,048-byte ring, 16-byte V2
padding, 24-byte FFT header and 512 x 2-byte bins. It also verifies
undersized allocations, missing buffers and impossible/oversized TLV
lengths are rejected, while valid 1,088-byte and 2,048-byte cases pass.

`direct_buf_rx_data.buf_capacity` is sourced from the DMA ring allocation
(`min_buf_size`) and remains **independent** of the WMI release TLV's
missing `dbr_len` and the host synthesized `spectral_data_len`. This patch
only adds a pre-parse memory-safety check; it does not change firmware WMI
configuration, enable RF scans or force a firmware assertion, and it does
**not** establish that FFT magnitudes are calibrated or nonzero.

### WCN7750 GEN3 raw-bin fingerprint (first four valid reports)

The production callback now records at most **four** compact, bounded
fingerprints of **raw 16-bit** FFT values before byte swapping or SAMP
8-bit saturation. It runs only after the existing direct DMA allocation
bounds check and only when report format V2 and firmware bin width 2 are
in use. Each line includes word count, zero/one/>255 counts, maximum,
first/middle/last values, FNV-1a hash, FFT length word, and buffer
capacity. It contains **no arbitrary raw buffer dump**, does not change
WMI scan configuration, and does not activate or assert the firmware.

`test_gen3_raw_bin_fingerprint.py` compiles and runs the extracted
production C helper using synthetic DMA buffers under GCC UBSan. It
exercises a 512-bin payload containing zero, one, 256 and 65535 as well
as the four-report rate limit. A normal Wi-Fi boot will not create a
fingerprint unless a genuine Spectral DMA completion is delivered.

### GEN3 signed FFT peak bin index (2026-10-19)

The WCN7750 firmware FFT V2 header reports a **signed** peak bin offset
from the center. Prior GEN3 host code decoded this offset into
`fft_peak_sidx` but never populated the outgoing SAMP `max_index`, so it
was always zero. The archived mode-3 512-bin record with header
`hdr_a=0x1007e0` yields offset `+2`, matching the actual exported bin
maximum at index `512/2+2 = 258`. SAMP stores `spectral_max_index` as
`int16_t` (even though the intermediate params field is `uint16_t`).

`test_gen3_peak_index.py` verifies the output propagation in both old and
optimized SAMP paths, including secondary-80 reporting. It compiles the
production conversion helper with GCC UBSan to verify two's-complement
preservation for positive and negative offsets. This is a **metadata-only
host fix**; it does not alter RF, FFT DMA, firmware configuration, power
scaling, or scan behavior and cannot fix the all-zero FFT captures.
