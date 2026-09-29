import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

import native_host
from runtime import ROOT, USER_DIR, codex_path
from bridge import environment


class DistributionTests(unittest.TestCase):
    def test_only_packaged_cli_and_separate_account_directory(self):
        with patch.dict('os.environ', {'CODEX_HOME': 'publisher-account', 'OPENAI_API_KEY': 'publisher-key'}):
            env = environment()
        self.assertEqual(Path(env['CODEX_HOME']), USER_DIR / 'account')
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertEqual(Path(codex_path()).parent, ROOT / '.runtime/codex')

    def test_native_messaging_round_trip_and_size_bounds(self):
        output = io.BytesIO()
        payload = {'ok': True, 'message': '英语译文'}
        native_host.write_message(output, payload)
        output.seek(0)
        self.assertEqual(native_host.read_message(output), payload)
        self.assertIsNone(native_host.read_message(output))
        for body in (struct.pack('<I', 20000), b'\x01', struct.pack('<I', 10) + b'{}'):
            with self.assertRaises(ValueError):
                native_host.read_message(io.BytesIO(body))

    def test_native_bridge_rejects_arbitrary_commands(self):
        with patch('native_host.ensure_service') as launch:
            for command in ({'command': 'exec', 'args': 'powershell'}, {'command': 'start-shell'}, [], None):
                self.assertFalse(native_host.dispatch(command)['ok'])
            launch.assert_not_called()
            self.assertTrue(native_host.dispatch({'command': 'start'})['ok'])
            launch.assert_called_once()

    def test_extension_id_matches_key_and_has_only_needed_permissions(self):
        manifest = json.loads((ROOT / 'extension/manifest.json').read_text(encoding='utf-8'))
        digest = hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
        identity = ''.join(chr(ord('a') + int(char, 16)) for char in digest)
        self.assertEqual(identity, native_host.EXTENSION_ID)
        self.assertEqual(set(manifest['permissions']), {'sidePanel', 'nativeMessaging'})
        self.assertNotIn('host_permissions', manifest)
        self.assertNotIn('content_scripts', manifest)
        self.assertNotIn('externally_connectable', manifest)


if __name__ == '__main__':
    unittest.main(verbosity=2)
