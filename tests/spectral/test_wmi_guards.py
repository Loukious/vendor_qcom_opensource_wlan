#!/usr/bin/env python3
"""Exercise the actual spectral WMI senders with a fake host and WMI sink.

No kernel, phone or RF access. Tests source functions, not a Python rewrite.
The full Android module still needs its ordinary Kbuild compilation.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(os.environ.get('WLAN_TEST_ROOT', Path(__file__).resolve().parents[2]))
SOURCE = ROOT / 'qca-wifi-host-cmn/target_if/spectral/target_if_spectral.c'


def function(source, name):
    match = re.search(r'^' + re.escape(name) + r'\(', source, re.M)
    if not match:
        raise ValueError(name)
    start = source.index('{', match.start())
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return 'static int\n' + source[match.start():end]


PREAMBLE = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
typedef int QDF_STATUS;
enum { QDF_STATUS_SUCCESS, QDF_STATUS_E_FAILURE, QDF_STATUS_E_INVAL,
       QDF_STATUS_E_NOENT, QDF_STATUS_E_NULL_VALUE };
enum spectral_scan_mode { SPECTRAL_SCAN_MODE_NORMAL, SPECTRAL_SCAN_MODE_AGILE };
#define QDF_IS_STATUS_SUCCESS(s) ((s) == QDF_STATUS_SUCCESS)
#define spectral_err(...) ((void)0)
#define qdf_mem_zero(p, n) memset((p), 0, (n))
#define WLAN_SPECTRAL_ID 1
#define GET_WMI_HDL_FROM_PDEV(p) ((void *)(p))
static int qdf_status_to_os_return(QDF_STATUS status) {
    switch (status) {
    case QDF_STATUS_SUCCESS: return 0;
    case QDF_STATUS_E_INVAL: return -EINVAL;
    case QDF_STATUS_E_NOENT: return -ENOENT;
    default: return -EIO;
    }
}
struct wlan_objmgr_psoc { int unused; };
struct wlan_objmgr_pdev { int unused; };
struct wlan_objmgr_vdev { int unused; };
struct spectral_config {
    unsigned ss_count, ss_period, ss_recapture, ss_spectral_pri, ss_fft_size;
    unsigned ss_gc_ena, ss_restart_ena, ss_noise_floor_ref, ss_init_delay;
    unsigned ss_nb_tone_thr, ss_str_bin_thr, ss_wb_rpt_mode, ss_rssi_rpt_mode;
    unsigned ss_rssi_thr, ss_pwr_format, ss_rpt_mode, ss_bin_scale, ss_dbm_adj;
    unsigned ss_chn_mask, ss_bandwidth;
    struct { unsigned cfreq1, cfreq2; } ss_frequency;
};
struct vdev_spectral_configure_params {
    unsigned vdev_id, count, period, fft_recap, spectral_pri, fft_size;
    unsigned gc_enable, restart_enable, noise_floor_ref, init_delay;
    unsigned nb_tone_thr, str_bin_thr, wb_rpt_mode, rssi_rpt_mode, rssi_thr;
    unsigned pwr_format, rpt_mode, bin_scale, dbm_adj, chn_mask;
    unsigned mode, center_freq1, center_freq2, chan_width;
};
struct vdev_spectral_enable_params {
    unsigned vdev_id, active_valid, enabled_valid, active, enabled, mode;
};
struct target_if_spectral { struct wlan_objmgr_pdev *pdev_obj; };
struct target_if_psoc_spectral {
    struct {
        QDF_STATUS (*wmi_spectral_configure_cmd_send)(void *, struct vdev_spectral_configure_params *);
        QDF_STATUS (*wmi_spectral_enable_cmd_send)(void *, struct vdev_spectral_enable_params *);
    } wmi_ops;
};
static struct wlan_objmgr_psoc psoc;
static struct wlan_objmgr_pdev pdev;
static struct wlan_objmgr_vdev vdev;
static struct target_if_psoc_spectral psoc_spectral;
static int config_calls, enable_calls, releases, no_vdev;
static uint8_t active_mask;
static QDF_STATUS config_status, enable_status;
static struct vdev_spectral_configure_params captured;
static struct vdev_spectral_enable_params captured_enable;
static struct wlan_objmgr_psoc *wlan_pdev_get_psoc(struct wlan_objmgr_pdev *p) {
    (void)p; return &psoc;
}
static struct target_if_psoc_spectral *get_target_if_spectral_handle_from_psoc(struct wlan_objmgr_psoc *p) {
    (void)p; return &psoc_spectral;
}
static struct wlan_objmgr_vdev *target_if_spectral_get_vdev(struct target_if_spectral *p, enum spectral_scan_mode mode) {
    (void)p; (void)mode; return no_vdev ? 0 : &vdev;
}
static unsigned wlan_vdev_get_id(struct wlan_objmgr_vdev *p) { (void)p; return 7; }
static uint8_t wlan_vdev_mlme_get_rxchainmask(struct wlan_objmgr_vdev *p) { (void)p; return active_mask; }
static void wlan_objmgr_vdev_release_ref(struct wlan_objmgr_vdev *p, int id) {
    (void)p; (void)id; ++releases;
}
static QDF_STATUS config_sink(void *p, struct vdev_spectral_configure_params *param) {
    (void)p; ++config_calls; captured = *param; return config_status;
}
static QDF_STATUS enable_sink(void *p, struct vdev_spectral_enable_params *param) {
    (void)p; ++enable_calls; captured_enable = *param; return enable_status;
}
'''

CASES = r'''
int main(void) {
    struct target_if_spectral spectral = {.pdev_obj = &pdev};
    struct spectral_config cfg = {.ss_count = 8, .ss_fft_size = 7, .ss_rpt_mode = 2};
    int rc;
    psoc_spectral.wmi_ops.wmi_spectral_configure_cmd_send = config_sink;
    psoc_spectral.wmi_ops.wmi_spectral_enable_cmd_send = enable_sink;
    /* Exhaust all 4-bit masks: preserve valid subsets, reject inactive bits. */
    for (unsigned live = 0; live < 16; ++live) {
        for (unsigned requested = 0; requested < 16; ++requested) {
            unsigned resolved = requested ? requested : live;
            int valid = live && resolved && !(resolved & ~live);
            active_mask = live; cfg.ss_chn_mask = requested;
            config_calls = releases = 0;
            rc = target_if_send_vdev_spectral_configure_cmd(&spectral, 0, &cfg);
            assert(releases == 1);
            assert((rc == 0) == valid);
            assert(config_calls == valid);
            assert(cfg.ss_chn_mask == (valid ? resolved : requested));
            if (valid) {
                assert(captured.chn_mask == resolved);
                assert(captured.vdev_id == 7 && captured.count == 8);
                assert(captured.fft_size == 7 && captured.rpt_mode == 2);
            }
        }
    }
    /* A rejected WMI send must be negative and must not commit recovered state. */
    active_mask = 3; cfg.ss_chn_mask = 0; config_status = QDF_STATUS_E_FAILURE;
    rc = target_if_send_vdev_spectral_configure_cmd(&spectral, 0, &cfg);
    assert(rc < 0 && cfg.ss_chn_mask == 0);
    enable_status = QDF_STATUS_E_FAILURE;
    rc = target_if_send_vdev_spectral_enable_cmd(&spectral, 0, 1, 1, 1, 1);
    assert(rc < 0 && enable_calls == 1);
    enable_status = QDF_STATUS_SUCCESS;
    rc = target_if_send_vdev_spectral_enable_cmd(&spectral, 0, 1, 0, 1, 0);
    assert(rc == 0 && captured_enable.active == 0 && captured_enable.enabled == 0);
    /* Missing vdev must never become a positive pseudo-success. */
    no_vdev = 1; config_calls = enable_calls = 0;
    assert(target_if_send_vdev_spectral_configure_cmd(&spectral, 0, &cfg) == -ENOENT);
    assert(target_if_send_vdev_spectral_enable_cmd(&spectral, 0, 1, 1, 1, 1) == -ENOENT);
    assert(config_calls == 0 && enable_calls == 0);
    return 0;
}
'''


class SpectralWmiGuards(unittest.TestCase):
    def test_actual_senders_with_invalid_masks_and_wmi_failures(self):
        source = SOURCE.read_text()
        body = '\n'.join(function(source, name) for name in (
            'target_if_send_vdev_spectral_configure_cmd',
            'target_if_send_vdev_spectral_enable_cmd'))
        with tempfile.TemporaryDirectory(prefix='spectral-guards-') as temp:
            code = Path(temp) / 'test.c'
            binary = Path(temp) / 'test'
            code.write_text(PREAMBLE + body + CASES)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall',
                            '-Wextra', '-Werror', '-fsanitize=undefined',
                            str(code), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
