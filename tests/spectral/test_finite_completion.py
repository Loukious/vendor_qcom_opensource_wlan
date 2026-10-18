"""Compile actual completion/stop functions against a fake host and WMI sink."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_wmi_guards import function

ROOT = Path(os.environ.get('WLAN_TEST_ROOT', Path(__file__).resolve().parents[2]))
SOURCE = ROOT / 'qca-wifi-host-cmn/target_if/spectral/target_if_spectral.c'

PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
#define ATH_PERF_PWR_OFFLOAD 1
#define QDF_STATUS int
enum { QDF_STATUS_SUCCESS, QDF_STATUS_E_FAILURE, QDF_STATUS_E_INVAL };
enum spectral_scan_mode { SPECTRAL_SCAN_MODE_NORMAL, SPECTRAL_SCAN_MODE_AGILE,
                          SPECTRAL_SCAN_MODE_MAX };
enum { SPECTRAL_SCAN_COMPLETE, SPECTRAL_SCAN_COMPLETE_SUCCESS };
enum { TARGET_IF_SPECTRAL_INFO_ENABLED, TARGET_IF_SPECTRAL_INFO_ACTIVE };
#define QDF_IS_STATUS_ERROR(s) ((s) != QDF_STATUS_SUCCESS)
#define spectral_err(...) ((void)0)
#define spectral_err_rl(...) ((void)0)
struct wlan_objmgr_pdev { int unused; };
struct wlan_objmgr_psoc;
struct target_if_finite_spectral_scan_params {
    bool finite_spectral_scan, is_scan_complete;
    uint32_t num_reports_expected, num_reports_requested;
};
struct target_if_spectral_param_state_info {
    int osps_lock;
    struct { uint8_t osc_spectral_active, osc_spectral_enabled; } osps_cache;
};
struct spectral_config { struct { unsigned cfreq1, cfreq2; } ss_frequency; };
struct target_if_spectral;
struct target_if_spectral_ops {
    int (*configure_spectral)(struct target_if_spectral *, struct spectral_config *,
                              enum spectral_scan_mode);
};
struct target_if_spectral {
    struct wlan_objmgr_pdev *pdev_obj;
    struct target_if_finite_spectral_scan_params finite_scan[SPECTRAL_SCAN_MODE_MAX];
    struct target_if_spectral_param_state_info param_info[SPECTRAL_SCAN_MODE_MAX];
    struct spectral_config params[SPECTRAL_SCAN_MODE_MAX];
    bool finite_scan_auto_disables;
    struct target_if_spectral_ops ops;
};
struct spectral_scan_complete_event {
    int completion_status; uint32_t num_received_samples;
};
struct spectral_scan_event {
    int event_id; struct spectral_scan_complete_event complete_event;
};
#define GET_TARGET_IF_SPECTRAL_OPS(s) (&(s)->ops)
static int events, event_failure, wmi_writes;
static void qdf_spin_lock_bh(int *lock) { assert(!*lock); *lock = 1; }
static void qdf_spin_unlock_bh(int *lock) { assert(*lock); *lock = 0; }
static int target_if_spectral_scan_complete_event(struct target_if_spectral *s,
                                                 struct spectral_scan_event *e) {
    assert(e->event_id == SPECTRAL_SCAN_COMPLETE);
    assert(e->complete_event.completion_status == SPECTRAL_SCAN_COMPLETE_SUCCESS);
    assert(e->complete_event.num_received_samples == 2);
    assert(!s->param_info[0].osps_lock);
    assert(s->finite_scan[0].is_scan_complete);
    if (s->finite_scan_auto_disables) {
        assert(!s->param_info[0].osps_cache.osc_spectral_active);
        assert(!s->param_info[0].osps_cache.osc_spectral_enabled);
    }
    events++;
    return event_failure;
}
static int target_if_spectral_info_read(struct target_if_spectral *s,
    enum spectral_scan_mode mode, int field, void *out, int len) {
    assert(mode < SPECTRAL_SCAN_MODE_MAX && len == 1);
    assert(field == TARGET_IF_SPECTRAL_INFO_ENABLED);
    *(uint8_t *)out = s->param_info[mode].osps_cache.osc_spectral_enabled;
    return 0;
}
static int target_if_spectral_info_write(struct target_if_spectral *s,
    enum spectral_scan_mode mode, int field, void *in, int len) {
    (void)s; (void)mode; (void)field; (void)in; (void)len;
    wmi_writes++; return 0;
}
'''

MAIN = r'''
int main(void) {
    struct wlan_objmgr_pdev pdev;
    for (int quirk = 0; quirk < 2; quirk++) {
        for (int notify_fail = 0; notify_fail < 2; notify_fail++) {
            struct target_if_spectral s = {0};
            s.pdev_obj = &pdev;
            s.finite_scan_auto_disables = quirk;
            s.finite_scan[0] = (struct target_if_finite_spectral_scan_params)
                                {true, false, 2, 2};
            s.param_info[0].osps_cache.osc_spectral_active = 1;
            s.param_info[0].osps_cache.osc_spectral_enabled = 1;
            s.param_info[1].osps_cache.osc_spectral_active = 1;
            s.param_info[1].osps_cache.osc_spectral_enabled = 1;
            events = wmi_writes = 0;
            event_failure = notify_fail;
            assert(target_if_spectral_finite_scan_update(&s, 0) == 0);
            assert(!events && !wmi_writes);
            assert(s.finite_scan[0].finite_spectral_scan);
            assert(s.param_info[0].osps_cache.osc_spectral_active == 1);
            assert(target_if_spectral_finite_scan_update(&s, 0) == notify_fail);
            assert(events == 1 && !wmi_writes);
            assert(!s.finite_scan[0].finite_spectral_scan);
            assert(s.finite_scan[0].is_scan_complete);
            assert(s.param_info[0].osps_cache.osc_spectral_active == !quirk);
            assert(s.param_info[0].osps_cache.osc_spectral_enabled == !quirk);
            assert(s.param_info[1].osps_cache.osc_spectral_active == 1);
            assert(s.param_info[1].osps_cache.osc_spectral_enabled == 1);
            /* Completed WCN7750 stop cannot send either redundant WMI write. */
            int rc = target_if_sops_stop_spectral_scan(&s, 0);
            assert(rc == (quirk ? -EPERM : 0));
            assert(wmi_writes == (quirk ? 0 : 2));
            assert(target_if_spectral_finite_scan_update(&s, 0) == QDF_STATUS_E_FAILURE);
            assert(events == 1);
        }
    }
    assert(target_if_spectral_finite_scan_update(NULL, 0) == QDF_STATUS_E_INVAL);
    struct target_if_spectral bad = {0};
    assert(target_if_spectral_finite_scan_update(&bad, 0) == QDF_STATUS_E_INVAL);
    bad.pdev_obj = &pdev;
    assert(target_if_spectral_finite_scan_update(&bad, SPECTRAL_SCAN_MODE_MAX)
           == QDF_STATUS_E_INVAL);
    return 0;
}
'''


class TestFiniteCompletion(unittest.TestCase):
    def test_completion_then_stop(self):
        source = SOURCE.read_text()
        code = PREAMBLE + '\n' + function(source, 'target_if_spectral_finite_scan_update')
        code += '\n' + function(source, 'target_if_sops_stop_spectral_scan') + '\n' + MAIN
        with tempfile.TemporaryDirectory() as tmp:
            cfile, exe = Path(tmp) / 'test.c', Path(tmp) / 'test'
            cfile.write_text(code)
            subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall',
                            '-Wextra', '-Werror', '-fsanitize=undefined',
                            str(cfile), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
