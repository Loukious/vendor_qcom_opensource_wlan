"""Document why zero dbr_len does NOT prove missing firmware DMA data."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / 'fw-api/fw/wmi_unified.h'
WMI = ROOT / 'qca-wifi-host-cmn/wmi/src/wmi_unified_dbr_tlv.c'
DBR = ROOT / 'qca-wifi-host-cmn/target_if/direct_buf_rx/src/target_if_direct_buf_rx_main.c'


class TestDBRLengthSemantics(unittest.TestCase):
    def test_firmware_release_event_contains_address_without_length(self):
        source = FW.read_text()
        start = source.index('} wmi_dma_buf_release_fixed_param;')
        begin = source.index('typedef struct {', start)
        end = source.index('} wmi_dma_buf_release_entry;', begin)
        fw_struct = source[begin:end]
        self.assertIn('paddr_lo;', fw_struct)
        self.assertIn('paddr_hi;', fw_struct)
        self.assertNotIn('A_UINT32 len;', fw_struct)

    def test_host_dbr_length_remains_unset_by_wmi_decoder(self):
        source = WMI.read_text()
        begin = source.index('static QDF_STATUS extract_dbr_buf_release_entry_tlv(')
        end = source.index('static QDF_STATUS extract_dbr_buf_metadata_tlv(', begin)
        decoder = source[begin:end]
        self.assertIn('param->paddr_lo = entry->paddr_lo;', decoder)
        self.assertIn('param->paddr_hi = entry->paddr_hi;', decoder)
        self.assertNotIn('param->len =', decoder)
        self.assertIn('dbr_data->dbr_len = dbr_rsp->dbr_entries[idx].len;', DBR.read_text())


if __name__ == '__main__':
    unittest.main()
