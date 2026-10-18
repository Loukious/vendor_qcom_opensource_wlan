"""Compile and exercise real GEN3 preconversion raw16 logger under UBSan.

Only uses synthetic, bounded in-memory ring samples; does not scan Wi-Fi.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[2]/'qca-wifi-host-cmn/target_if/spectral/target_if_spectral_phyerr.c'

class TestRawBinFingerprint(unittest.TestCase):
    def test_source_order_and_no_crash_instrumentation(self):
        s=SRC.read_text()
        self.assertLess(s.index('target_if_spectral_gen3_dbr_report_fits(spectral, payload)'),
                        s.index('target_if_spectral_gen3_raw_bin_fingerprint(spectral, payload)'))
        self.assertLess(s.index('target_if_spectral_gen3_raw_bin_fingerprint(spectral, payload)'),
                        s.index('ret = target_if_consume_spectral_report_gen3(spectral, &report);'))
        part=s[s.index('static void target_if_spectral_gen3_raw_bin_fingerprint('):s.index('int target_if_spectral_process_report_gen3(',s.index('static void target_if_spectral_gen3_raw_bin_fingerprint('))]
        self.assertNotIn('target_if_spectral_fw_hang',part)
        self.assertNotIn('target_if_spectral_hexdump',part)
        self.assertIn('atomic_inc_return',part)
        self.assertIn('SPECTRAL_GEN3_FINGERPRINT_LIMIT 4',s)

    def test_extracted_production_logger_with_ubsan(self):
        s=SRC.read_text()
        start=s.index('/* Log at most four valid, bounded 16-bit DMA FFT fingerprints per boot. */')
        end=s.index('int target_if_spectral_process_report_gen3(',start)
        fun=s[start:end]
        harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#define SPECTRAL_REPORT_FORMAT_VERSION_2 2
#define SPECTRAL_REPORT_LTS_HDR_LENGTH_POS_GEN3 0
#define SPECTRAL_REPORT_LTS_HDR_LENGTH_SIZE_GEN3 16
#define get_bitfield(x,size,pos) (((x)>>(pos))&((1u<<(size))-1))
#define qdf_le16_to_cpu(x) (x)
#define qdf_le32_to_cpu(x) (x)
#define qdf_mem_copy memcpy
struct spectral_sscan_summary_report_gen3 {uint32_t words[6];};
struct spectral_phyerr_fft_report_gen3 {
    uint32_t fft_timestamp,fft_hdr_lts,hdr_a,hdr_b,hdr_c,resv;
    uint8_t buf[];
} __attribute__((packed));
struct direct_buf_rx_data {size_t dbr_len,buf_capacity;void *vaddr;};
struct target_if_spectral {
    struct {size_t ssummary_padding_bytes,fft_report_hdr_len;
            unsigned version,hw_fft_bin_width;} rparams;
};
typedef struct {int counter;} atomic_t;
#define ATOMIC_INIT(v) {v}
#define atomic_read(p) ((p)->counter)
#define atomic_inc_return(p) (++(p)->counter)
static unsigned log_count,logged_bins,logged_zero,logged_over,logged_peak,logged_hash;
#define spectral_info(fmt,...) log_values(__VA_ARGS__)
/* Called with exact values from production log; same order as format. */
static void log_values(int sample,size_t bins,unsigned zeros,unsigned ones,
                       unsigned over,unsigned peak,unsigned max_index,
                       unsigned first,unsigned mid,unsigned last,unsigned hash,
                       unsigned lts,size_t cap) {
   (void)sample;(void)ones;(void)max_index;(void)first;(void)mid;
   (void)last;(void)lts;(void)cap;
   log_count++;logged_bins=bins;logged_zero=zeros;logged_over=over;
   logged_peak=peak;logged_hash=hash;
}
''' + fun + r'''
int main(void) {
   uint8_t raw[2048]={0};
   struct target_if_spectral spectral={.rparams={16,24,2,2}};
   struct direct_buf_rx_data payload={.dbr_len=0,.buf_capacity=2048,.vaddr=raw};
   uint32_t words=262;
   memcpy(raw+40+4,&words,4);
   /* 512 x 16-bit bins, deliberately include zero, one and clamped values. */
   uint16_t *ptr=(uint16_t *)(raw+64);
   ptr[0]=0;ptr[1]=1;ptr[2]=256;ptr[3]=65535;
   target_if_spectral_gen3_raw_bin_fingerprint(&spectral,&payload);
   if(log_count!=1 || logged_bins!=512 || logged_zero!=509 ||
      logged_over!=2 || logged_peak!=65535 || logged_hash==0) return 1;
   for(int i=0;i<20;i++)
       target_if_spectral_gen3_raw_bin_fingerprint(&spectral,&payload);
   if(log_count!=4) return 2;
   spectral.rparams.hw_fft_bin_width=1;
   target_if_spectral_gen3_raw_bin_fingerprint(&spectral,&payload);
   if(log_count!=4) return 3;
   return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            (path/'test.c').write_text(harness)
            out=subprocess.run(['gcc','-std=gnu11','-O1','-g','-Wall','-Wextra',
                                '-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',
                                str(path/'test.c'),'-o',str(path/'test')],
                               text=True,capture_output=True)
            self.assertEqual(out.returncode,0,out.stdout+'\n'+out.stderr)
            run=subprocess.run([str(path/'test')],text=True,capture_output=True)
            self.assertEqual(run.returncode,0,run.stdout+'\n'+run.stderr)

if __name__=='__main__':unittest.main()
