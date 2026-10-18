"""Execute extracted production GEN3 DBR bounds check with GCC ASan/UBSan.

This is not a simulated scan. Firmware reports are never sent to hardware.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
PHY=ROOT/'qca-wifi-host-cmn/target_if/spectral/target_if_spectral_phyerr.c'
DBR=ROOT/'qca-wifi-host-cmn/target_if/direct_buf_rx/src/target_if_direct_buf_rx_main.c'
API=ROOT/'qca-wifi-host-cmn/target_if/direct_buf_rx/inc/target_if_direct_buf_rx_api.h'

class TestGen3DbrBounds(unittest.TestCase):
    def test_wmi_length_unset_but_allocation_capacity_is_propagated(self):
        api=API.read_text()
        core=DBR.read_text()
        self.assertIn('size_t buf_capacity;',api)
        self.assertIn('dbr_data->buf_capacity = dbr_ring_cap->min_buf_size;',core)
        self.assertIn('dbr_data->dbr_len = dbr_rsp->dbr_entries[idx].len;',core)
        phy=PHY.read_text()
        self.assertLess(phy.index('target_if_spectral_gen3_dbr_report_fits(spectral, payload)'),
                        phy.index('report.data = payload->vaddr;'))
        self.assertIn('qdf_min(payload->buf_capacity,',phy)

    def test_extracted_real_helper_with_sanitizers(self):
        source=PHY.read_text()
        start=source.index('static bool target_if_spectral_gen3_dbr_report_fits(')
        stop=source.index('/* Log at most four valid, bounded 16-bit DMA FFT fingerprints per boot. */',start)
        function=source[start:stop]
        self.assertIn('sizeof(*fft) > payload->buf_capacity - fft_offset',function)
        self.assertIn('fft_hdr_length > payload->buf_capacity - fft_offset',function)
        harness=r'''
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define SPECTRAL_REPORT_LTS_HDR_LENGTH_POS_GEN3 0
#define SPECTRAL_REPORT_LTS_HDR_LENGTH_SIZE_GEN3 16
#define get_bitfield(x,size,pos) (((x) >> (pos)) & ((1u << (size))-1))
#define qdf_le32_to_cpu(x) (x)
struct spectral_sscan_summary_report_gen3 {uint32_t words[6];};
struct spectral_phyerr_fft_report_gen3 {
    uint32_t fft_timestamp, fft_hdr_lts, hdr_a, hdr_b, hdr_c, resv;
    uint8_t buf[];
} __attribute__((packed));
struct direct_buf_rx_data { size_t dbr_len,buf_capacity;void *vaddr;};
struct target_if_spectral {struct {size_t ssummary_padding_bytes,fft_report_hdr_len;} rparams;};
''' + function + r'''
static int run(size_t alloc, unsigned len_words, size_t pad, size_t min_header, bool expected) {
    uint8_t raw[2048]={0};
    struct target_if_spectral spectral={.rparams={pad,min_header}};
    struct direct_buf_rx_data payload={.dbr_len=0, .buf_capacity=alloc, .vaddr=raw};
    size_t header=24+pad;
    if (header + 8 <= sizeof(raw)) {
        uint32_t len=len_words;
        memcpy(raw+header+4,&len,sizeof(len));
    }
    bool result=target_if_spectral_gen3_dbr_report_fits(&spectral,&payload);
    if(result!=expected){fprintf(stderr,"alloc=%zu words=%u pad=%zu min=%zu result=%d expected=%d\\n",alloc,len_words,pad,min_header,result,expected);return 1;}
    return 0;
}
int main(void){
    int err=0;
    /* 24 summary + 16 pad + (24+1024) FFT = 1088 bytes; ring=2048. */
    err|=run(2048,262,16,24,true);
    err|=run(1088,262,16,24,true);
    err|=run(1087,262,16,24,false);
    err|=run(63,262,16,24,false);
    err|=run(40,262,16,24,false);
    err|=run(0,262,16,24,false);
    err|=run(2048,0,16,24,false);
    err|=run(2048,5,16,24,false);
    err|=run(2048,502,16,24,true);
    err|=run(2048,503,16,24,false);
    err|=run(2048,65535,16,24,false);
    err|=run(2048,262,16,1080,false);
    err|=run(2048,262,2030,24,false);
    err|=run(2048,262,0,24,true);
    struct target_if_spectral spec={.rparams={16,24}};
    if(target_if_spectral_gen3_dbr_report_fits(&spec,NULL)) err++;
    struct direct_buf_rx_data empty={0};
    if(target_if_spectral_gen3_dbr_report_fits(&spec,&empty)) err++;
    return err;
}
'''
        with tempfile.TemporaryDirectory() as path:
            path=Path(path)
            (path/'test.c').write_text(harness)
            cc=subprocess.run(['gcc','-std=gnu11','-O1','-g','-Wall','-Wextra',
                               '-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',
                               str(path/'test.c'),'-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(cc.returncode,0,cc.stdout+'\n'+cc.stderr)
            run=subprocess.run([str(path/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+'\n'+run.stderr)
if __name__=='__main__': unittest.main()
