"""Run pipeline checks against a selected unpacked app without touching user data."""
import os
import json
from pathlib import Path
import sys
import tempfile
import unittest

app = Path(sys.argv[1]).resolve()
assert (app / 'latency.py').is_file(), 'Apply the low-latency app update first'
sys.path.insert(0, str(app))
with tempfile.TemporaryDirectory(prefix='phyrex-latency-test-') as folder:
    os.environ['FED_TRANSLATOR_USER_DIR'] = folder
    from runtime import prepare
    prepare()
    try:
        import faster_whisper
    except ImportError:
        sys.path.append(str(Path(__file__).resolve().parents[3] / 'fed-live-translator/.runtime/packages'))
    suite = unittest.TestSuite(unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern=pattern)
                               for pattern in ('test_latency.py', 'test_streaming.py', 'test_gpu_runtime.py', 'test_gpu_install.py', 'test_live_updates.py'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps({'tests': result.testsRun,
            'passed': result.wasSuccessful(), 'failures': len(result.failures),
            'errors': len(result.errors), 'scope': 'Packaged pipeline, streaming, GPU fallback, installer and HTTP events; no real AI login'}, indent=2), encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
