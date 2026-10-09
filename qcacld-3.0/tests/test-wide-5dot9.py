#!/usr/bin/env python3
"""Compile the actual 5.9 GHz filter and test capability/profile boundaries."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'qca-wifi-host-cmn/umac/regulatory/core/src'
source = (CORE / 'reg_build_chan_list.c').read_text()
start = source.index('static void\nreg_modify_chan_list_for_5dot9_ghz_channels(')
opening = source.index('{', start)
depth = 0
for end in range(opening, len(source)):
    depth += (source[end] == '{') - (source[end] == '}')
    if not depth:
        function = source[start:end + 1]
        break
assert re.search(r'FCC15_FCCA\s*=\s*0xEA', (CORE / 'reg_db.h').read_text())
stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
enum channel_enum { FIRST, NUM_CHANNELS=7 };
enum { FCC15_FCCA=0xea, REGULATORY_CHAN_DISABLED=1,
       REGULATORY_CHAN_NO_IR=2, INDOOR=4, RADAR=8,
       CHANNEL_STATE_DISABLE=0, CHANNEL_STATE_DFS=1, CHANNEL_STATE_ENABLE=2 };
struct regulatory_channel { unsigned center_freq, state, chan_flags, max_bw, tx_power; };
struct wlan_objmgr_psoc { int unused; };
struct wlan_objmgr_pdev { int unused; };
struct wlan_regulatory_pdev_priv_obj { unsigned reg_dmn_pair; };
static struct wlan_objmgr_psoc psoc;
static struct wlan_regulatory_pdev_priv_obj priv={FCC15_FCCA};
static bool fcc=true, offload=true, capability=false, master=false, have_priv=true;
static struct wlan_objmgr_psoc *wlan_pdev_get_psoc(struct wlan_objmgr_pdev *p) { return &psoc; }
static struct wlan_regulatory_pdev_priv_obj *reg_get_pdev_obj(struct wlan_objmgr_pdev *p) { return have_priv?&priv:NULL; }
static bool reg_is_fcc_regdmn(struct wlan_objmgr_pdev *p) { return fcc; }
static bool reg_is_regdb_offloaded(struct wlan_objmgr_psoc *p) { return offload; }
static bool reg_is_5dot9_ghz_supported(struct wlan_objmgr_psoc *p) { return capability; }
static bool reg_is_disabling_5dot9_needed(struct wlan_objmgr_psoc *p) {
#ifdef CONFIG_REG_CLIENT
 return !capability || !offload;
#else
 return !capability;
#endif
}
static bool reg_is_5dot9_ghz_chan_allowed_master_mode(struct wlan_objmgr_pdev *p) { return master; }
static bool reg_is_5dot9_ghz_freq(struct wlan_objmgr_pdev *p, unsigned f) { return f>=5845 && f<=5885; }
static bool reg_is_state_allowed(unsigned s) { return s==CHANNEL_STATE_ENABLE || s==CHANNEL_STATE_DFS; }
'''
tests = r'''
int main(void) {
 struct wlan_objmgr_pdev pdev={0};
 const struct regulatory_channel before[NUM_CHANNELS]={
  {5825,2,0,80,23}, {5845,2,0,40,23}, {5865,1,INDOOR|RADAR,40,17},
  {5885,2,INDOOR,20,8}, {5955,2,INDOOR,160,24},
  {5845,0,REGULATORY_CHAN_DISABLED|INDOOR,20,13},
  {5865,0,INDOOR,20,11}
 };
 struct regulatory_channel list[NUM_CHANNELS];
 /* Cover old profiles, missing pdev data, native capability, country,
    firmware offload and master-mode INI independently. */
 for (int have=0;have<2;have++) for(int pair=0;pair<2;pair++)
 for(int country=0;country<2;country++) for(int fw=0;fw<2;fw++)
 for(int bit=0;bit<2;bit++) for(int ini=0;ini<2;ini++) {
  have_priv=have; priv.reg_dmn_pair=pair?FCC15_FCCA:0x09;
  fcc=country; offload=fw; capability=bit; master=ini;
  memcpy(list,before,sizeof(list));
  reg_modify_chan_list_for_5dot9_ghz_channels(&pdev,list);
  assert(!memcmp(&list[0],&before[0],sizeof(list[0])));
  assert(!memcmp(&list[4],&before[4],sizeof(list[4])));
  bool fallback=false;
#if defined(CONFIG_WLAN_WIDE_CHANNELS) && defined(CONFIG_REG_CLIENT)
  fallback=have && pair && fw && !bit;
#endif
  for(int i=1;i<NUM_CHANNELS;i++) {
   if(i==4)continue;
   struct regulatory_channel expected=before[i];
   if(fcc) {
    if(reg_is_disabling_5dot9_needed(&psoc) && !fallback) {
     expected.state=CHANNEL_STATE_DISABLE;expected.chan_flags=REGULATORY_CHAN_DISABLED;
    } else if((!master || fallback) && !(expected.chan_flags&REGULATORY_CHAN_DISABLED)
              && (!fallback || reg_is_state_allowed(expected.state))) {
     expected.state=CHANNEL_STATE_DFS;expected.chan_flags|=REGULATORY_CHAN_NO_IR;
    }
   }
   assert(!memcmp(&list[i],&expected,sizeof(expected)));
  }
  assert(capability==bit); /* Never forge firmware capability. */
 }
 puts("64 cases: passive-only fallback, native behavior, excluded channels, limits/flags and option-off: OK");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(stub + function + tests)
    for wide, client in ((False, True), (True, True), (False, False), (True, False)):
        flags = (['-DCONFIG_WLAN_WIDE_CHANNELS'] if wide else []) + \
                (['-DCONFIG_REG_CLIENT'] if client else [])
        subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-parameter', '-Wno-unused-function',
                        '-fsanitize=undefined', *flags, str(path / 'test.c'),
                        '-o', str(path / 'test')], check=True)
        subprocess.run([str(path / 'test')], check=True)
