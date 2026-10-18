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
