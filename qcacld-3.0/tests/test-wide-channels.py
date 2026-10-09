#!/usr/bin/env python3
"""Compile actual changed functions with injected WMI/lifecycle failures."""
from pathlib import Path
import argparse
import json
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report', type=Path, help='Optional JSON validation report')
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'qca-wifi-host-cmn/umac/regulatory/core/src'
TARGET = ROOT / 'qca-wifi-host-cmn/target_if/regulatory/src/target_if_reg.c'


def function(path, signature):
    text = path.read_text()
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 0
    for i in range(opening, len(text)):
        depth += (text[i] == '{') - (text[i] == '}')
        if not depth:
            return text[start:i + 1]
    raise AssertionError('Missing function end')


public_stub = r'''
#include <stdint.h>
struct cc_regdmn_s {
    union {
        uint16_t country_code;
        struct { uint16_t reg_2g_5g_pair_id, sixg_superdmn_id; } regdmn;
        uint8_t alpha[3];
    } cc;
    uint8_t flags;
};
enum { INVALID_CC, CC_IS_SET, REGDMN_IS_SET, ALPHA_IS_SET };
struct cur_reg_rule {
    uint16_t start_freq, end_freq, max_bw;
    uint8_t reg_power, ant_gain;
    uint16_t flags;
};
struct cur_regulatory_info {
    uint16_t reg_dmn_pair;
    uint32_t num_2g_reg_rules, num_5g_reg_rules;
    struct cur_reg_rule *reg_rules_2g_ptr, *reg_rules_5g_ptr;
};
'''
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define __REG_DB_H
enum { FCC8_WORLD = 0x09 };
#include "reg_channel_profile.h"
typedef int QDF_STATUS;
typedef void *wmi_unified_t;
#define QDF_STATUS_E_FAILURE 1
#define QDF_STATUS_E_INVAL 2
#define QDF_IS_STATUS_ERROR(s) ((s) != 0)
#define WLAN_REGULATORY_NB_ID 1
#define target_if_info(...) ((void)0)
#define target_if_err(...) ((void)0)
#define hdd_info(...) ((void)0)
#define hdd_err(...) ((void)0)
struct wlan_objmgr_psoc { int unused; };
struct wlan_objmgr_pdev { int unused; };
struct hdd_context { struct wlan_objmgr_psoc *psoc; struct wlan_objmgr_pdev *pdev; };
struct set_country { uint8_t country[3]; uint8_t pdev_id; };
static struct wlan_objmgr_pdev pdev;
static int have_pdev = 1, have_wmi = 1, offload = 1, allowed = 1;
static int legacy_calls, user_calls, program_calls, hdd_country_calls, release_calls;
static int send_result;
static uint8_t sent_pdev;
static struct cc_regdmn_s sent_rd;
static struct set_country sent_country;
static char *country_code;
static wmi_unified_t get_wmi_unified_hdl_from_psoc(struct wlan_objmgr_psoc *p) { return have_wmi ? (void *)1 : NULL; }
static wmi_unified_t get_wmi_unified_hdl_from_pdev(struct wlan_objmgr_pdev *p) { return have_wmi ? (void *)1 : NULL; }
static struct wlan_objmgr_pdev *wlan_objmgr_get_pdev_by_id(struct wlan_objmgr_psoc *p, uint8_t id, int ref) { return have_pdev ? &pdev : NULL; }
static void wlan_objmgr_pdev_release_ref(struct wlan_objmgr_pdev *p, int ref) { assert(p); release_calls++; }
static QDF_STATUS wmi_unified_set_country_cmd_send(wmi_unified_t w, void *arg) { legacy_calls++; sent_country = *(struct set_country *)arg; return send_result; }
static QDF_STATUS wmi_unified_set_user_country_code_cmd_send(wmi_unified_t w, uint8_t id, struct cc_regdmn_s *rd) { user_calls++; sent_pdev=id; sent_rd=*rd; return send_result; }
static bool ucfg_reg_is_regdb_offloaded(struct wlan_objmgr_psoc *p) { return offload; }
static bool ucfg_reg_is_user_country_set_allowed(struct wlan_objmgr_psoc *p) { return allowed; }
static QDF_STATUS ucfg_reg_program_cc(struct wlan_objmgr_pdev *p, struct cc_regdmn_s *rd) { program_calls++; sent_rd=*rd; return send_result; }
static int qdf_status_to_os_return(QDF_STATUS s) { return s ? -EIO : 0; }
static int hdd_reg_set_country(struct hdd_context *h, char *c) { hdd_country_calls++; return -EAGAIN; }
'''
tests = r'''
int main(void) {
    struct wlan_objmgr_psoc psoc = {0};
    struct hdd_context hdd = {&psoc, &pdev};
    struct set_country c = {{'T','N',0}, 0xff};
    struct cc_regdmn_s requested = {.cc.alpha={'T','N',0}, .flags=ALPHA_IS_SET}, before=requested;
    assert(tgt_if_regulatory_set_country_code(&psoc, &c) == 0);
    assert(c.pdev_id == 0xff && !memcmp(c.country, "TN", 3));
#ifdef CONFIG_WLAN_WIDE_CHANNELS
    assert(user_calls == 1 && legacy_calls == 0 && sent_pdev == 0xff);
    assert(sent_rd.flags == REGDMN_IS_SET && sent_rd.cc.regdmn.reg_2g_5g_pair_id == 0x09);
    assert(sent_rd.cc.regdmn.sixg_superdmn_id == 0);
    assert(tgt_if_regulatory_set_country_code(&psoc, NULL) == QDF_STATUS_E_INVAL);
#else
    assert(user_calls == 0 && legacy_calls == 1 && !memcmp(sent_country.country, "TN", 3));
#endif
    assert(tgt_if_regulatory_set_user_country_code(&psoc, 7, &requested) == 0);
    assert(!memcmp(&requested, &before, sizeof(before)) && sent_pdev == 7);
    assert(release_calls == 1);
#ifdef CONFIG_WLAN_WIDE_CHANNELS
    assert(sent_rd.flags == REGDMN_IS_SET && sent_rd.cc.regdmn.reg_2g_5g_pair_id == 0x09);
#else
    assert(!memcmp(&sent_rd, &requested, sizeof(requested)));
#endif
    for (int flag=CC_IS_SET; flag<=ALPHA_IS_SET; flag++) {
        requested.flags=flag; before=requested;
        assert(tgt_if_regulatory_set_user_country_code(&psoc, 0, &requested)==0);
        assert(!memcmp(&requested, &before, sizeof(before)));
#ifdef CONFIG_WLAN_WIDE_CHANNELS
        assert(sent_rd.flags==REGDMN_IS_SET && sent_rd.cc.regdmn.reg_2g_5g_pair_id==0x09);
#endif
    }
    int previous=release_calls, calls=user_calls;
    have_pdev=0;
    assert(tgt_if_regulatory_set_user_country_code(&psoc, 0, &requested)==QDF_STATUS_E_FAILURE);
    assert(release_calls==previous && user_calls==calls);
    have_pdev=1; have_wmi=0;
    assert(tgt_if_regulatory_set_country_code(&psoc, &c)==QDF_STATUS_E_FAILURE);
    assert(tgt_if_regulatory_set_user_country_code(&psoc, 0, &requested)==QDF_STATUS_E_FAILURE);
    assert(release_calls==previous+1 && user_calls==calls);
    have_wmi=1; send_result=3;
    assert(tgt_if_regulatory_set_user_country_code(&psoc, 0, &requested)==3);
    assert(release_calls==previous+2);
    assert(tgt_if_regulatory_set_country_code(&psoc, &c)==3);
    assert(tgt_if_regulatory_set_user_country_code(&psoc, 0, NULL)==QDF_STATUS_E_INVAL);
    send_result=0;
    assert(hdd_update_country_code(&hdd)==0);
#ifdef CONFIG_WLAN_WIDE_CHANNELS
    assert(program_calls==1 && hdd_country_calls==0);
    send_result=3;
    assert(hdd_update_country_code(&hdd)==-EIO);
    send_result=0;
#else
    assert(program_calls==0 && hdd_country_calls==0);
#endif
    offload=0; country_code="TN";
    assert(hdd_update_country_code(&hdd)==-EAGAIN && hdd_country_calls==1);
    allowed=0;
    assert(hdd_update_country_code(&hdd)==0 && hdd_country_calls==1);
    struct cur_reg_rule two[]={{2402,2482,40,30,0,0},{2402,2472,20,8,0,1}};
    struct cur_reg_rule five[]={{5250,5330,80,30,6,0x123},{5490,5730,160,10,0,0x321},{5945,7125,320,30,0,8}};
    struct cur_reg_rule two_before[2], five_before[3];
    memcpy(two_before,two,sizeof(two)); memcpy(five_before,five,sizeof(five));
    struct cur_regulatory_info info={0x09,2,3,two,five};
    reg_cap_channel_profile_power(&info);
#ifdef CONFIG_WLAN_WIDE_CHANNELS
    two_before[0].reg_power=20; five_before[0].reg_power=23;
#endif
    assert(!memcmp(two,two_before,sizeof(two)) && !memcmp(five,five_before,sizeof(five)));
    info.reg_dmn_pair=0x30; two[0].reg_power=30;
    reg_cap_channel_profile_power(&info); assert(two[0].reg_power==30);
    info.reg_dmn_pair=0x09; info.reg_rules_2g_ptr=NULL; info.reg_rules_5g_ptr=NULL;
    reg_cap_channel_profile_power(&info);
    puts("startup, country/domain updates, error propagation, references, power and feature-off checks: OK");
}
'''

assert re.search(r'FCC8_WORLD\s*=\s*0x09', (CORE / 'reg_db.h').read_text())
assert TARGET.read_text().count('reg_cap_channel_profile_power(reg_info);') == 2
functions = '\n'.join([
    function(TARGET, 'static QDF_STATUS tgt_if_regulatory_set_country_code('),
    function(TARGET, 'static QDF_STATUS tgt_if_regulatory_set_user_country_code('),
    function(ROOT / 'qcacld-3.0/core/hdd/src/wlan_hdd_main.c', 'int hdd_update_country_code('),
])
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    (tmp / 'reg_services_public_struct.h').write_text(public_stub)
    (tmp / 'test.c').write_text(prefix + functions + tests)
    for enabled in (False, True):
        command = ['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                   '-Wno-unused-parameter', '-fsanitize=undefined', '-g', '-I', str(tmp), '-I', str(CORE)]
        if enabled:
            command.append('-DCONFIG_WLAN_WIDE_CHANNELS')
        subprocess.run(command + [str(tmp / 'test.c'), '-o', str(tmp / 'test')], check=True)
        subprocess.run([str(tmp / 'test')], check=True)

db = (CORE / 'reg_db.c').read_text()
assert '{FCC8_WORLD, FCC8, WORLD}' in db
domain = re.search(r'\[FCC8\]\s*=.*?\{(CHAN_.*?)\}\s*\}', db, re.S).group(1)
names = re.findall(r'CHAN_\w+', domain)
rules = {}
for name in names:
    match = re.search(r'\[' + name + r'\]\s*=\s*\{(.*?)\}', db, re.S)
    values = [v.strip() for v in match.group(1).split(',')]
    rules[name] = {'start_mhz': int(values[0]), 'end_mhz': int(values[1]),
                   'max_bw_mhz': int(values[2]), 'db_power_dbm': int(values[3]), 'flags': values[4]}
channels = list(range(36, 65, 4)) + list(range(100, 145, 4)) + list(range(149, 178, 4))
for channel in channels:
    frequency = 5000 + 5 * channel
    covering = [r for r in rules.values() if r['start_mhz'] <= frequency - 10 and r['end_mhz'] >= frequency + 10]
    assert covering, f'Channel {channel} missing from profile'
    if 52 <= channel <= 64 or 100 <= channel <= 144:
        assert all('RADAR' in r['flags'] for r in covering)
report = {'source_tests': 'passed with feature enabled and disabled',
          'profile': 'FCC8_WORLD (0x09)', 'database_5ghz_channels': channels,
          'rules': rules, 'firmware_acceptance': 'not tested; phone has original module',
          'power_caps_dbm': {'2.4ghz': 20, '5ghz': 23}}
if args.report:
    args.report.write_text(json.dumps(report, indent=2) + '\n')
print('Database coverage and DFS flags: OK; firmware acceptance remains untested.')
