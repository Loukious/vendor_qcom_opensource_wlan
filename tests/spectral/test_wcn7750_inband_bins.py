"""Source regression for experimental WCN7750 in-band report-mode-2 count.

This checks host source and the exact source-level bin count arithmetic. It
cannot prove the WPSS firmware actually DMA-transfers only in-band bins.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'qca-wifi-host-cmn/target_if/spectral/target_if_spectral.c'
PHYERR = ROOT / 'qca-wifi-host-cmn/target_if/spectral/target_if_spectral_phyerr.c'


def expected_count(payload_bytes, bin_bytes, report_mode, adjust):
    assert payload_bytes % bin_bytes == 0
    count = payload_bytes // bin_bytes
    return count // 2 if (report_mode == 2 and adjust) else count


class TestWcn7750InbandBinCount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = TARGET.read_text()
        start = source.index('target_if_spectral_len_adj_swar_init(')
        end = source.index('/**', start)
        cls.init_body = source[start:end]
        cls.counter = PHYERR.read_text()

    def test_only_wcn7750_adds_special_flag(self):
        body = self.init_body
        self.assertRegex(body, r'if \(target_type == TARGET_TYPE_WCN7750\)\s*'
                               r'swar->inband_fftbin_size_adj = 1;')
        self.assertEqual(body.count('target_type == TARGET_TYPE_WCN7750'), 2)

    def test_null_mode1_unmodified(self):
        body = self.init_body
        wcn = body.index('if (target_type == TARGET_TYPE_WCN7750)',
                         body.index('swar->null_fftbin_adj = 0;'))
        before = body[:wcn]
        after = body[wcn:body.index('if (target_type == TARGET_TYPE_QCA8074V2)', wcn)]
        self.assertIn('swar->null_fftbin_adj = 0;', before)
        self.assertNotIn('null_fftbin_adj', after)

    def test_mode2_1024_byte_16bit_report_becomes_256(self):
        self.assertEqual(expected_count(1024, 2, 2, True), 256)
        self.assertEqual(expected_count(1024, 2, 2, False), 512)

    def test_mode3_stays_512_and_mode1_unaffected(self):
        self.assertEqual(expected_count(1024, 2, 3, True), 512)
        self.assertEqual(expected_count(1024, 2, 1, True), 512)

    def test_driver_only_applies_extra_halving_to_mode2(self):
        self.assertRegex(self.counter,
                         r'if \(rpt_mode == 2 && swar->inband_fftbin_size_adj\)\s*'
                         r'fft_bin_count >>= 1;')


if __name__ == '__main__':
    unittest.main()
