"""Optional GPU setup must check compatibility before downloading anything."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import setup_gpu


class GpuInstallTests(unittest.TestCase):
    def test_incompatible_hardware_never_downloads_or_changes_existing_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            marker = root / '.runtime/gpu/ready.txt'
            marker.parent.mkdir(parents=True)
            marker.write_text('existing', encoding='ascii')
            with patch.object(setup_gpu, 'ROOT', root), patch.object(setup_gpu, 'check_hardware', side_effect=RuntimeError('not compatible')), patch.object(setup_gpu.urllib.request, 'urlopen') as download:
                with self.assertRaises(RuntimeError):
                    setup_gpu.install()
            download.assert_not_called()
            self.assertEqual(marker.read_text(), 'existing')

    def test_bad_checksum_cannot_install_libraries_or_mark_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stream = io.BytesIO(b'not the pinned package')
            stream.headers = {'Content-Length': str(len(stream.getvalue()))}
            with patch.object(setup_gpu, 'ROOT', root), patch.object(setup_gpu, 'check_hardware'), patch.object(setup_gpu.shutil, 'disk_usage', return_value=Mock(free=5_000_000_000)), patch.object(setup_gpu, 'PACKAGES', (('test', 'https://example.invalid/file', '0' * 64),)), patch.object(setup_gpu.urllib.request, 'urlopen', return_value=stream):
                with self.assertRaisesRegex(RuntimeError, '校验失败'):
                    setup_gpu.install()
            self.assertFalse((root / '.runtime/gpu/ready.txt').exists())
            self.assertFalse(list(root.rglob('*.dll')))
            self.assertFalse(list(root.rglob('*.download')))

    def test_no_cuda_device_is_reported_before_network_access(self):
        with patch.object(setup_gpu.os, 'name', 'nt'), patch.object(setup_gpu.platform, 'machine', return_value='AMD64'), patch('ctranslate2.get_cuda_device_count', return_value=0), patch.object(setup_gpu.urllib.request, 'urlopen') as download:
            with self.assertRaisesRegex(RuntimeError, '未检测到'):
                setup_gpu.check_hardware()
            download.assert_not_called()

    def test_verified_archive_cannot_extract_outside_runtime_directory(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('../../../escape.dll', b'dll')
        data = archive.getvalue()
        stream = io.BytesIO(data)
        stream.headers = {'Content-Length': str(len(data))}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'app'
            root.mkdir()
            with patch.object(setup_gpu, 'ROOT', root), patch.object(setup_gpu, 'check_hardware'), patch.object(setup_gpu.shutil, 'disk_usage', return_value=Mock(free=5_000_000_000)), patch.object(setup_gpu, 'PACKAGES', (('test', 'https://example.invalid/file', hashlib.sha256(data).hexdigest()),)), patch.object(setup_gpu.urllib.request, 'urlopen', return_value=stream):
                with self.assertRaisesRegex(RuntimeError, '路径无效'):
                    setup_gpu.install()
            self.assertFalse((Path(folder) / 'escape.dll').exists())
            self.assertFalse((root / '.runtime/gpu/ready.txt').exists())


if __name__ == '__main__':
    unittest.main()
