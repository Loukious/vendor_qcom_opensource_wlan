"""Check that Spectral DBR capacity is logged without altering DMA handling.

The logged allocation size is an upper bound, NOT a firmware payload length.
"""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'qca-wifi-host-cmn/target_if/direct_buf_rx/src/target_if_direct_buf_rx_main.c'

class TestSpectralCapacityAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = SOURCE.read_text()
        start = cls.src.index('static QDF_STATUS target_if_dbr_cfg_tgt(')
        end = cls.src.index('static QDF_STATUS target_if_init_dbr_ring(',start)
        cls.function = cls.src[start:end]

    def test_only_on_spectral_ring_cfg(self):
        self.assertRegex(self.function,
            r'if \(mod_param->mod_id == DBR_MODULE_SPECTRAL\)\s*direct_buf_rx_info\(')
        self.assertIn('Spectral DBR capacity:', self.function)
        self.assertIn('dbr_cfg_req.buf_size', self.function)
        self.assertIn('dbr_cfg_req.num_elems', self.function)
        self.assertIn('cfg_status %d', self.function)
        self.assertEqual(self.function.count('wmi_unified_dbr_ring_cfg('),1)

    def test_no_change_to_firmware_wmi_cap_values(self):
        self.assertIn('dbr_cfg_req.buf_size = dbr_ring_cap->min_buf_size;',self.function)
        self.assertIn('dbr_cfg_req.num_elems = dbr_ring_cap->ring_elems_min;',self.function)
        self.assertRegex(self.function,r'\breturn status;')

    def test_not_a_dma_release_handler_or_risky_debug(self):
        self.assertNotIn('target_if_spectral_fw_hang',self.function)
        self.assertNotIn('MEM_POISON_SIGNATURE',self.function)
        self.assertNotIn('target_if_dbr_get_dbr_data',self.function)

if __name__=='__main__': unittest.main()
