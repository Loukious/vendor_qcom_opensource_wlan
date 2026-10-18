"""Regression checks for 64-bit FFT bin-size out-parameter aliasing bug."""
import ctypes
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / 'qca-wifi-host-cmn/target_if/spectral/target_if_spectral_phyerr.c'


class FFTInfo(ctypes.Structure):
    # Exactly the fields before the suspect u8/pointer in Qualcomm's header.
    _fields_ = [('earlier_u32', ctypes.c_uint32 * 15),
                ('fft_bin_size', ctypes.c_uint8),
                ('bin_pwr_data', ctypes.c_void_p)]


class TestFFTBinSizeStorage(unittest.TestCase):
    def test_source_uses_correct_out_parameter_type(self):
        code = FILE.read_text()
        pos = code.index('target_if_process_sfft_report_gen3(')
        end = code.index('target_if_spectral_populate_samp_params_gen3()', pos)
        function = code[pos:end]
        self.assertIn('size_t fft_bin_size;', function)
        self.assertIn('&spectral->len_adj_swar, &fft_bin_size);', function)
        self.assertIn('p_sfft->fft_bin_size = (uint8_t)fft_bin_size;', function)
        self.assertNotIn('(size_t *)&p_sfft->fft_bin_size', function)

    def test_layout_reveals_original_bad_write_overlaps_pointer(self):
        # Width and overlap independently checked against debug-bearing .ko
        # using pahole: byte field +60; pointer +64; sizeof(size_t)=8.
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            self.skipTest('64-bit ABI required')
        self.assertEqual(FFTInfo.fft_bin_size.offset, 60)
        self.assertEqual(FFTInfo.bin_pwr_data.offset, 64)
        bad_end = FFTInfo.fft_bin_size.offset + ctypes.sizeof(ctypes.c_size_t)
        self.assertGreater(bad_end, FFTInfo.bin_pwr_data.offset)

    def test_other_spectral_size_calls_use_real_size_t(self):
        code = FILE.read_text()
        self.assertEqual(code.count('(size_t *)&p_sfft->fft_bin_size'), 0)
        self.assertRegex(code, r'\bsize_t fft_bin_size;')


if __name__ == '__main__':
    unittest.main()
