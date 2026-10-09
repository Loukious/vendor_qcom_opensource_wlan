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
    struct wlan_objmgr_psoc *psoc;
    uint8_t phy_id;
    int status_code, dfs_region;
};
'''
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>
#define __REG_DB_H
enum { FCC15_FCCA = 0xea, FCC1_6G_18 = 0x18, MKKA = 0, FCC8 = 1 };
#include "reg_channel_profile.h"
typedef int QDF_STATUS;
typedef void *wmi_unified_t;
#define QDF_STATUS_E_FAILURE 1
#define QDF_STATUS_E_INVAL 2
#define QDF_STATUS_E_NOMEM 4
#define QDF_STATUS_SUCCESS 0
#define REG_SET_CC_STATUS_PASS 0
#define PSOC_MAX_PHY_REG_CAP 2
#define MAX_REG_RULES 10
#define HOST_REGDMN_MODE_11B 1
#define REGULATORY_CHAN_NO_OFDM 64
#define CTL_MKK 0x40
#define CTL_FCC 0x10
#define REG_BAND_MASK_ALL 7
#define XIAOMI_HW_PLATFORM_2G_5G_ONLY 3
#define SCAN_MODE_6G_ALL_CHANNEL 2
#define QDF_IS_STATUS_ERROR(s) ((s) != 0)
#define WLAN_REGULATORY_NB_ID 1
#define target_if_info(...) ((void)0)
#define target_if_err(...) ((void)0)
#define hdd_info(...) ((void)0)
#define hdd_err(...) ((void)0)
#define mlme_info(...) ((void)0)
struct wlan_objmgr_psoc { int unused; };
struct wlan_objmgr_pdev { int unused; };
struct hdd_context { struct wlan_objmgr_psoc *psoc; struct wlan_objmgr_pdev *pdev; };
struct set_country { uint8_t country[3]; uint8_t pdev_id; };
static struct wlan_objmgr_pdev pdev;
static int have_pdev = 1, have_wmi = 1, offload = 1, allowed = 1, firmware_sixg=1;
static int legacy_calls, user_calls, program_calls, hdd_country_calls, release_calls;
static int send_result;
static uint8_t sent_pdev;
static struct cc_regdmn_s sent_rd;
static struct set_country sent_country;
static char *country_code;
struct wlan_regulatory_psoc_priv_obj { bool wide_channel14_ctl_sent[PSOC_MAX_PHY_REG_CAP]; };
struct wlan_psoc_host_hal_reg_capabilities_ext { uint32_t wireless_modes; uint16_t low_2ghz_chan, high_2ghz_chan; };
struct pdev_set_regdomain_params { uint16_t currentRDinuse, currentRD2G, currentRD5G; uint32_t ctl_2G, ctl_5G; uint8_t dfsDomain; uint32_t pdev_id; };
struct wlan_lmac_if_reg_tx_ops { void (*get_pdev_id_from_phy_id)(struct wlan_objmgr_psoc *, uint8_t, uint8_t *); };
struct wlan_mlme_generic { uint32_t band_capability, band; };
struct wlan_mlme_wifi_pos_cfg { bool oem_6g_support_disable; };
struct wlan_scan_obj { struct { int scan_mode_6g; bool skip_6g_and_indoor_freq; } scan_def; };
static struct wlan_regulatory_psoc_priv_obj soc_reg;
static struct wlan_psoc_host_hal_reg_capabilities_ext caps[2]={{1,2400,2500},{1,2400,2500}};
static struct pdev_set_regdomain_params sent_ctl;
const uint32_t reg_2g_sub_dmn_code[]={0x0a40,0};
const uint32_t reg_5g_sub_dmn_code[]={0,0x0810};
static int ctl_calls, ctl_result, fail_alloc, live_allocations, have_caps=1, platform=3;
static int get_hw_version_platform(void) { return platform; }
static struct wlan_regulatory_psoc_priv_obj *reg_get_psoc_obj(struct wlan_objmgr_psoc *p) { return &soc_reg; }
static struct wlan_psoc_host_hal_reg_capabilities_ext *ucfg_reg_get_hal_reg_cap(struct wlan_objmgr_psoc *p) { return have_caps ? caps : NULL; }
static void map_phy(struct wlan_objmgr_psoc *p, uint8_t phy, uint8_t *id) { *id=phy+7; }
static struct wlan_lmac_if_reg_tx_ops tx_ops={map_phy};
static struct wlan_lmac_if_reg_tx_ops *target_if_regulatory_get_tx_ops(struct wlan_objmgr_psoc *p) { return &tx_ops; }
static void *qdf_mem_malloc(size_t n) { if(fail_alloc) return NULL; void *p=calloc(1,n); assert(p); live_allocations++; return p; }
static void qdf_mem_free(void *p) { if(p) { free(p); live_allocations--; } }
#define qdf_mem_copy memcpy
#define qdf_mem_zero(p,n) memset(p,0,n)
static QDF_STATUS wmi_unified_pdev_set_regdomain_cmd_send(wmi_unified_t w, struct pdev_set_regdomain_params *p) { ctl_calls++; sent_ctl=*p; return ctl_result; }
static wmi_unified_t get_wmi_unified_hdl_from_psoc(struct wlan_objmgr_psoc *p) { return have_wmi ? (void *)1 : NULL; }
static bool tgt_if_regulatory_is_6ghz_supported(struct wlan_objmgr_psoc *p) { return firmware_sixg; }
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
#ifdef CONFIG_WLAN_WIDE_CHANNELS
static struct cur_regulatory_info event(struct wlan_objmgr_psoc *psoc, uint8_t phy) {
    struct cur_reg_rule *rules=qdf_mem_malloc(sizeof(*rules));
    *rules=(struct cur_reg_rule){2402,2472,40,20,0,0};
    return (struct cur_regulatory_info){.reg_dmn_pair=0xea,.num_2g_reg_rules=1,
        .num_5g_reg_rules=5,.reg_rules_2g_ptr=rules,.psoc=psoc,.phy_id=phy,.dfs_region=2};
}
static void channel14_tests(struct wlan_objmgr_psoc *psoc) {
    tgt_if_reset_channel14_profile(psoc);
    struct cur_regulatory_info info=event(psoc,0);
    struct cur_reg_rule *original=info.reg_rules_2g_ptr;
    info.reg_dmn_pair=0x09;
    assert(tgt_if_apply_channel14_profile(&info)==0 && ctl_calls==0);
    assert(info.reg_rules_2g_ptr==original && original[0].end_freq==2472);
    info.reg_dmn_pair=0xea;
    info.status_code=5;
    assert(tgt_if_apply_channel14_profile(&info)==0 && ctl_calls==0);
    info.status_code=0; have_caps=0;
    assert(tgt_if_apply_channel14_profile(&info)==QDF_STATUS_E_FAILURE);
    have_caps=1; caps[0].high_2ghz_chan=2482;
    assert(tgt_if_apply_channel14_profile(&info)==QDF_STATUS_E_FAILURE && ctl_calls==0);
    caps[0].high_2ghz_chan=2500; caps[0].wireless_modes=0;
    assert(tgt_if_apply_channel14_profile(&info)==QDF_STATUS_E_FAILURE);
    caps[0].wireless_modes=1;
    info.num_5g_reg_rules=9;
    assert(tgt_if_apply_channel14_profile(&info)==QDF_STATUS_E_INVAL);
    info.num_5g_reg_rules=5; fail_alloc=1;
    assert(tgt_if_apply_channel14_profile(&info)==QDF_STATUS_E_NOMEM);
    fail_alloc=0; have_wmi=0;
    assert(tgt_if_apply_channel14_profile(&info)==QDF_STATUS_E_FAILURE);
    have_wmi=1; ctl_result=3;
    assert(tgt_if_apply_channel14_profile(&info)==3);
    assert(info.reg_rules_2g_ptr==original && info.num_2g_reg_rules==1);
    assert(live_allocations==1 && !soc_reg.wide_channel14_ctl_sent[0]);
    assert(original[0].end_freq==2472);
    ctl_result=0; int calls=ctl_calls;
    assert(tgt_if_apply_channel14_profile(&info)==0 && ctl_calls==calls+1);
    assert(sent_ctl.currentRD2G==0x0a40 && sent_ctl.currentRD5G==0x0810);
    assert(sent_ctl.currentRDinuse==0xea && sent_ctl.ctl_2G==0x40 && sent_ctl.ctl_5G==0x10);
    assert(sent_ctl.dfsDomain==2 && sent_ctl.pdev_id==7);
    assert(info.num_2g_reg_rules==2 && live_allocations==1);
    assert(info.reg_rules_2g_ptr[0].start_freq==2402 && info.reg_rules_2g_ptr[0].end_freq==2482);
    struct cur_reg_rule *fourteen=&info.reg_rules_2g_ptr[1];
    assert(fourteen->start_freq==2474 && fourteen->end_freq==2494);
    assert(fourteen->max_bw==20 && fourteen->reg_power==20 && fourteen->flags==64);
    calls=ctl_calls;
    assert(tgt_if_apply_channel14_profile(&info)==0 && ctl_calls==calls && info.num_2g_reg_rules==2);
    qdf_mem_free(info.reg_rules_2g_ptr);
    info=event(psoc,0);
    assert(tgt_if_apply_channel14_profile(&info)==0 && ctl_calls==calls);
    qdf_mem_free(info.reg_rules_2g_ptr);
    info=event(psoc,1);
    assert(tgt_if_apply_channel14_profile(&info)==0 && ctl_calls==calls+1 && sent_ctl.pdev_id==8);
    qdf_mem_free(info.reg_rules_2g_ptr);
    tgt_if_reset_channel14_profile(psoc);
    assert(!soc_reg.wide_channel14_ctl_sent[0] && !soc_reg.wide_channel14_ctl_sent[1]);
    info=event(psoc,0);
    assert(tgt_if_apply_channel14_profile(&info)==0 && ctl_calls==calls+2);
    qdf_mem_free(info.reg_rules_2g_ptr);
    info=event(psoc,2);
    assert(tgt_if_apply_channel14_profile(&info)==QDF_STATUS_E_INVAL);
    qdf_mem_free(info.reg_rules_2g_ptr);
    info=event(psoc,0); original=info.reg_rules_2g_ptr; info.reg_rules_2g_ptr=NULL;
    assert(tgt_if_apply_channel14_profile(&info)==QDF_STATUS_E_INVAL);
    qdf_mem_free(original);
    assert(live_allocations==0);
    puts("channel 14: bounds, 802.11b flags, RF gates, OOM, CTL failure, per-PHY/reset and bounded re-entry: OK");
}
#endif
int main(void) {
    struct wlan_objmgr_psoc psoc = {0};
    struct hdd_context hdd = {&psoc, &pdev};
    struct set_country c = {{'T','N',0}, 0xff};
    struct cc_regdmn_s requested = {.cc.alpha={'T','N',0}, .flags=ALPHA_IS_SET}, before=requested;
    assert(tgt_if_regulatory_set_country_code(&psoc, &c) == 0);
    assert(c.pdev_id == 0xff && !memcmp(c.country, "TN", 3));
#ifdef CONFIG_WLAN_WIDE_CHANNELS
    assert(user_calls == 1 && legacy_calls == 0 && sent_pdev == 0xff);
    assert(sent_rd.flags == REGDMN_IS_SET && sent_rd.cc.regdmn.reg_2g_5g_pair_id == 0xea);
#ifdef CONFIG_BAND_6GHZ
    assert(sent_rd.cc.regdmn.sixg_superdmn_id == 0x18);
#else
    assert(sent_rd.cc.regdmn.sixg_superdmn_id == 0);
#endif
    assert(tgt_if_regulatory_set_country_code(&psoc, NULL) == QDF_STATUS_E_INVAL);
#else
    assert(user_calls == 0 && legacy_calls == 1 && !memcmp(sent_country.country, "TN", 3));
#endif
    assert(tgt_if_regulatory_set_user_country_code(&psoc, 7, &requested) == 0);
    assert(!memcmp(&requested, &before, sizeof(before)) && sent_pdev == 7);
    assert(release_calls == 1);
#ifdef CONFIG_WLAN_WIDE_CHANNELS
    assert(sent_rd.flags == REGDMN_IS_SET && sent_rd.cc.regdmn.reg_2g_5g_pair_id == 0xea);
#else
    assert(!memcmp(&sent_rd, &requested, sizeof(requested)));
#endif
    for (int flag=CC_IS_SET; flag<=ALPHA_IS_SET; flag++) {
        requested.flags=flag; before=requested;
        assert(tgt_if_regulatory_set_user_country_code(&psoc, 0, &requested)==0);
        assert(!memcmp(&requested, &before, sizeof(before)));
#ifdef CONFIG_WLAN_WIDE_CHANNELS
        assert(sent_rd.flags==REGDMN_IS_SET && sent_rd.cc.regdmn.reg_2g_5g_pair_id==0xea);
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
#if defined(CONFIG_WLAN_WIDE_CHANNELS) && defined(CONFIG_BAND_6GHZ)
    firmware_sixg=0;
    assert(tgt_if_regulatory_set_country_code(&psoc, &c)==0 && sent_rd.cc.regdmn.sixg_superdmn_id==0);
    assert(tgt_if_regulatory_set_user_country_code(&psoc, 0, &requested)==0 && sent_rd.cc.regdmn.sixg_superdmn_id==0);
    firmware_sixg=1;
#endif
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
    struct cur_regulatory_info info={.reg_dmn_pair=0xea,.num_2g_reg_rules=2,
        .num_5g_reg_rules=3,.reg_rules_2g_ptr=two,.reg_rules_5g_ptr=five};
    reg_cap_channel_profile_power(&info);
    struct wlan_mlme_generic gen={3,3};
    struct wlan_mlme_wifi_pos_cfg pos={true};
    struct wlan_scan_obj scan={{0,true}};
    mlme_apply_wide_channel_band_cfg(&gen);
    mlme_apply_wide_channel_pos_cfg(&pos);
    wlan_scan_apply_wide_channel_cfg(&scan);
#ifdef CONFIG_WLAN_WIDE_CHANNELS
    assert(!mlme_xiaomi_hw_is_2g_5g_only() && gen.band_capability==7 && gen.band==7);
    assert(!pos.oem_6g_support_disable);
    channel14_tests(&psoc);
#else
    assert(mlme_xiaomi_hw_is_2g_5g_only() && gen.band_capability==3 && gen.band==3);
    assert(pos.oem_6g_support_disable);
#endif
#if defined(CONFIG_WLAN_WIDE_CHANNELS) && defined(CONFIG_BAND_6GHZ)
    assert(scan.scan_def.scan_mode_6g==2 && !scan.scan_def.skip_6g_and_indoor_freq);
#else
    assert(scan.scan_def.scan_mode_6g==0 && scan.scan_def.skip_6g_and_indoor_freq);
#endif
#ifdef CONFIG_WLAN_WIDE_CHANNELS
    two_before[0].reg_power=20; five_before[0].reg_power=23;
#endif
    assert(!memcmp(two,two_before,sizeof(two)) && !memcmp(five,five_before,sizeof(five)));
    info.reg_dmn_pair=0x30; two[0].reg_power=30;
    reg_cap_channel_profile_power(&info); assert(two[0].reg_power==30);
    info.reg_dmn_pair=0xea; info.reg_rules_2g_ptr=NULL; info.reg_rules_5g_ptr=NULL;
    reg_cap_channel_profile_power(&info);
    puts("startup, country/domain updates, error propagation, references, power and feature-off checks: OK");
}
'''

assert re.search(r'FCC15_FCCA\s*=\s*0xEA', (CORE / 'reg_db.h').read_text())
assert re.search(r'FCC1_6G_18\s*=\s*0x18', (CORE / 'reg_db.h').read_text())
assert TARGET.read_text().count('reg_cap_channel_profile_power(reg_info);') == 2
mlme = ROOT / 'qcacld-3.0/components/mlme/core/src/wlan_mlme_main.c'
scan = ROOT / 'qca-wifi-host-cmn/umac/scan/dispatcher/src/wlan_scan_ucfg_api.c'
functions = '#ifdef CONFIG_WLAN_WIDE_CHANNELS\n' + '\n'.join([
    function(TARGET, 'static void\ntgt_if_reset_channel14_profile('),
    function(TARGET, 'static QDF_STATUS\ntgt_if_apply_channel14_profile('),
]) + '\n#endif\n' + '\n'.join([
    function(TARGET, 'static QDF_STATUS tgt_if_regulatory_set_country_code('),
    function(TARGET, 'static QDF_STATUS tgt_if_regulatory_set_user_country_code('),
    function(ROOT / 'qcacld-3.0/core/hdd/src/wlan_hdd_main.c', 'int hdd_update_country_code('),
    function(mlme, 'static inline bool mlme_xiaomi_hw_is_2g_5g_only('),
    function(mlme, 'static inline void\nmlme_apply_wide_channel_band_cfg('),
    function(mlme, 'static inline void\nmlme_apply_wide_channel_pos_cfg('),
    function(scan, 'static inline void\nwlan_scan_apply_wide_channel_cfg('),
])
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    (tmp / 'reg_services_public_struct.h').write_text(public_stub)
    (tmp / 'test.c').write_text(prefix + functions + tests)
    for enabled, sixg in ((False, True), (True, False), (True, True)):
        command = ['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                   '-Wno-unused-parameter', '-fsanitize=undefined', '-g', '-I', str(tmp), '-I', str(CORE)]
        if enabled:
            command.append('-DCONFIG_WLAN_WIDE_CHANNELS')
        if sixg:
            command.append('-DCONFIG_BAND_6GHZ')
        subprocess.run(command + [str(tmp / 'test.c'), '-o', str(tmp / 'test')], check=True)
        subprocess.run([str(tmp / 'test')], check=True)

db = (CORE / 'reg_db.c').read_text()
assert '{FCC8_WORLD, FCC8, WORLD}' in db
assert '{FCC15_FCCA, FCC8, MKKA}' in db
assert '{FCC15_FCCA, FCC15, FCCA}' in db
assert re.search(r'\[MKKA\]\s*=\s*0x0A40', db)
assert re.search(r'\[FCC8\]\s*=\s*0x0810', db)
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
sixg_domain = re.search(r'\[FCC1_CLI_LPI_DEFAULT_6G\]\s*=.*?\{(CHAN_.*?)\}\s*\}', db, re.S).group(1)
sixg_rules = []
for name in re.findall(r'CHAN_\w+', sixg_domain):
    values = re.search(r'\[' + name + r'\]\s*=\s*\{(.*?)\}', db, re.S).group(1).split(',')
    sixg_rules.append((int(values[0]), int(values[1])))
sixg_channels = []
sixg_split_channels = []
# The requested domain spans the band, but its power/PSD rule boundary at
# 6875 MHz bisects channel 185. Do not claim that a single rule admits it.
edge = 5925
for start, end in sorted(sixg_rules):
    assert start <= edge, f'6 GHz database gap before {start} MHz'
    edge = max(edge, end)
assert edge == 7125
for channel in range(1, 234, 4):
    frequency = 5950 + 5 * channel
    if any(start <= frequency - 10 and end >= frequency + 10 for start, end in sixg_rules):
        sixg_channels.append(channel)
    else:
        sixg_split_channels.append(channel)
assert sixg_split_channels == [185]
report = {'source_tests': 'passed with feature disabled and enabled with/without 6 GHz',
          'profile': 'FCC15_FCCA (0xea)', 'database_5ghz_channels': channels,
          'rules': rules, 'firmware_acceptance': 'matching pair returned rules in native tests; built driver not tested by this source test',
          'channel14': '802.11b-only rule, subject to firmware RF range and per-band command acceptance',
          'sixg_superdomain': 'FCC1_6G_18 (0x18)',
          'database_6ghz_20mhz_channels': sixg_channels,
          'database_6ghz_split_rule_channels': sixg_split_channels,
          'sixg_rule_boundary_note': 'Channel 185 straddles the 6875 MHz power/PSD boundary; firmware rules determine usability',
          'power_caps_dbm': {'2.4ghz': 20, '5ghz': 23}}
if args.report:
    args.report.write_text(json.dumps(report, indent=2) + '\n')
print('Database coverage and DFS flags: OK; firmware acceptance remains untested.')
