"""Production SAMP GEN3 peak-index mapping and archived WCN7750 evidence.

Run actual C helper under GCC/UBSan with positive and negative indices.
No RF capture or device write is performed.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
PHY=ROOT/'qca-wifi-host-cmn/target_if/spectral/target_if_spectral_phyerr.c'
NET=ROOT/'qca-wifi-host-cmn/target_if/spectral/target_if_spectral_netlink.c'
COMMON=ROOT/'qca-wifi-host-cmn/spectral/dispatcher/inc/spectral_ioctl.h'

class PeakIndexTests(unittest.TestCase):
    def test_header_matches_archived_bin_max(self):
        # Nonzero mode-3 run: hdr_a 0x1007e0, peak index field [29:19] is +2.
        hdr_a=0x1007e0
        signed_peak=(hdr_a>>19)&0x7ff
        if signed_peak & 0x400:signed_peak-=0x800
        self.assertEqual(signed_peak,2)
        raw_bin_peak_position=258
        self.assertEqual(raw_bin_peak_position-512//2,signed_peak)
        self.assertNotEqual(signed_peak,0)

    def test_all_paths_fill_signed_peak_index(self):
        s=PHY.read_text()
        self.assertRegex(s,r'params->max_index\s*=\s*target_if_spectral_gen3_peak_sidx_to_samp\(\s*p_sfft->fft_peak_sidx\)')
        self.assertRegex(s,r'params\.max_index\s*=\s*target_if_spectral_gen3_peak_sidx_to_samp\(\s*p_sfft->fft_peak_sidx\)')
        self.assertRegex(s,r'params\.max_index_sec80\s*=\s*target_if_spectral_gen3_peak_sidx_to_samp\(\s*p_sfft->fft_peak_sidx\)')
        self.assertRegex(NET.read_text(),r'samp_data->spectral_max_index\s*=\s*params->max_index;')
        self.assertIn('int16_t spectral_max_index;',COMMON.read_text())

    def test_extracted_c_helper_ubsan(self):
        s=PHY.read_text()
        start=s.index('static uint16_t target_if_spectral_gen3_peak_sidx_to_samp(')
        end=s.index('\n#ifndef OPTIMIZED_SAMP_MESSAGE',start)
        function=s[start:end]
        harness=r'''#include <stdint.h>
#include <assert.h>
''' +function+ r'''
int main(void) {
    /* The SAMP wire field is int16_t; params uses uint16_t. */
    assert((int16_t)target_if_spectral_gen3_peak_sidx_to_samp(2)==2);
    assert((int16_t)target_if_spectral_gen3_peak_sidx_to_samp(-2)==-2);
    assert((int16_t)target_if_spectral_gen3_peak_sidx_to_samp(-1024)==-1024);
    assert((int16_t)target_if_spectral_gen3_peak_sidx_to_samp(1023)==1023);
    assert((int16_t)target_if_spectral_gen3_peak_sidx_to_samp(0)==0);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/'test.c').write_text(harness)
            cc=subprocess.run(['gcc','-std=gnu11','-O1','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fno-sanitize-recover=all',
                str(p/'test.c'),'-o',str(p/'test')],capture_output=True,text=True)
            self.assertEqual(cc.returncode,0,cc.stderr)
            t=subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(t.returncode,0,t.stderr)

if __name__=='__main__':unittest.main()
