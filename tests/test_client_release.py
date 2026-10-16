from pathlib import Path
import tempfile
import unittest
from wechat_archive.ui.release_check import workbench_check


class ClientRuntimeProbeTests(unittest.TestCase):
    def test_existing_desktop_probe_covers_all_six_units_without_real_services(self):
        with tempfile.TemporaryDirectory() as directory:
            result=workbench_check(Path(directory)/'client-runtime')
        self.assertEqual(result['status'],'passed')
        self.assertEqual(len(result['client_experience']),6)
        self.assertTrue(all(result['client_experience'].values()))
        self.assertTrue(result['copilot_phase1']['context_bound'])
        self.assertFalse(result['copilot_phase1']['model_request'])
        self.assertFalse(result['personal_source_read']);self.assertFalse(result['auth_or_model_request'])
