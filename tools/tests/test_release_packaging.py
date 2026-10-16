"""The hosted release runtime is fixed, verified and extracted as files only."""
import base64,hashlib,io,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools import prepare_codex_runtime as runtime

class RuntimePackagingTests(unittest.TestCase):
    def archive(self,license=True):
        output=io.BytesIO()
        files={'vendor/codex.exe':b'unit codex executable','vendor/codex-code-mode-host.exe':b'unit host executable'}
        if license:files['package/LICENSE']=b'unit license'
        with tarfile.open(fileobj=output,mode='w:gz') as archive:
            for name,data in files.items():
                item=tarfile.TarInfo(name);item.size=len(data);archive.addfile(item,io.BytesIO(data))
        return output.getvalue(),{Path(name).name:hashlib.sha256(data).hexdigest() for name,data in files.items() if name.endswith('.exe')}
    def test_only_verified_named_executables_and_license_are_written(self):
        data,expected=self.archive()
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'runtime'
            with patch.object(runtime,'urlopen',return_value=io.BytesIO(data)),patch.object(runtime,'INTEGRITY',base64.b64encode(hashlib.sha512(data).digest()).decode()),patch.object(runtime,'EXPECTED',expected):runtime.prepare(target)
            self.assertEqual({p.name for p in target.iterdir()},{*expected,'LICENSE','runtime_manifest.json'})
    def test_archive_digest_failure_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'runtime'
            with patch.object(runtime,'urlopen',return_value=io.BytesIO(b'untrusted archive')):
                with self.assertRaises(ValueError):runtime.prepare(target)
            self.assertFalse(target.exists())
    def test_member_digest_failure_leaves_no_output(self):
        data,expected=self.archive();expected['codex.exe']='0'*64
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'runtime'
            with patch.object(runtime,'urlopen',return_value=io.BytesIO(data)),patch.object(runtime,'INTEGRITY',base64.b64encode(hashlib.sha512(data).digest()).decode()),patch.object(runtime,'EXPECTED',expected):
                with self.assertRaises(ValueError):runtime.prepare(target)
            self.assertFalse(target.exists())
    def test_missing_license_and_existing_output_are_refused(self):
        data,expected=self.archive(license=False)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'runtime'
            with patch.object(runtime,'LICENSE_FILE',Path(folder)/'absent-license'),patch.object(runtime,'urlopen',return_value=io.BytesIO(data)),patch.object(runtime,'INTEGRITY',base64.b64encode(hashlib.sha512(data).digest()).decode()),patch.object(runtime,'EXPECTED',expected):
                with self.assertRaises(ValueError):runtime.prepare(target)
            target.mkdir()
            with patch.object(runtime,'urlopen',side_effect=AssertionError('No network for an existing destination')):
                with self.assertRaises(ValueError):runtime.prepare(target)

if __name__=='__main__':unittest.main()
