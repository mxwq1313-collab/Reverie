from pathlib import Path
import tempfile
import unittest
from wechat_archive.errors import ConflictError
from wechat_archive.knowledge.release_check import knowledge_check


class KnowledgeReleaseTests(unittest.TestCase):
    def test_offline_packaging_probe_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'probe'; result=knowledge_check(target)
            self.assertEqual(result['status'],'passed'); self.assertFalse(result['model_requested'])
            self.assertEqual(result['api_version'],'1.0'); self.assertTrue(result['source_change_revoked'])
            self.assertTrue((target/'knowledge_check.json').is_file())
            with self.assertRaises(ConflictError): knowledge_check(target)


if __name__=='__main__': unittest.main()
