"""Run offline DeepSeek API and local key-entry checks against a selected app."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('app', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('--require-packaged-certifi', action='store_true')
    args = parser.parse_args()
    root = args.app.resolve()
    if not (root / 'deepseek_api.py').is_file():
        parser.error('The selected app must contain deepseek_api.py.')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(root))
    with tempfile.TemporaryDirectory(prefix='phyrex-deepseek-api-test-') as folder:
        os.environ['FED_TRANSLATOR_USER_DIR'] = folder
        from runtime import prepare
        prepare()
        try:
            import certifi
            certifi_source = 'installed'
        except ImportError:
            # CI's source-only Linux job tests behavior without a packaged runtime.
            # Native release jobs must use the actual packaged CA bundle below.
            system_ca = Path('/etc/ssl/certs/ca-certificates.crt')
            if args.require_packaged_certifi or not sys.platform.startswith('linux') or not system_ca.is_file():
                raise
            certifi = types.ModuleType('certifi')
            certifi.where = lambda: str(system_ca)
            sys.modules['certifi'] = certifi
            certifi_source = 'linux-test-system-ca'
        if args.require_packaged_certifi:
            packages = (root / '.runtime/packages').resolve()
            if not Path(certifi.__file__).resolve().is_relative_to(packages):
                raise RuntimeError('Expected certifi inside the packaged application runtime.')
            if not Path(certifi.where()).resolve().is_relative_to(packages) or not Path(certifi.where()).is_file():
                raise RuntimeError('Expected a packaged certifi CA bundle.')
            certifi_source = 'packaged'
        import test_deepseek_api
        import test_deepseek_integration
        import test_api_charge_confirmation
        import test_deepseek_transport
        loader = unittest.defaultTestLoader
        suite = unittest.TestSuite([loader.loadTestsFromModule(test_deepseek_api),
                                    loader.loadTestsFromModule(test_deepseek_integration),
                                    loader.loadTestsFromModule(test_api_charge_confirmation),
                                    loader.loadTestsFromModule(test_deepseek_transport)])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'tests': result.testsRun, 'passed': result.wasSuccessful(),
              'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'platform': sys.platform,
              'real_inference': False, 'real_login': False, 'real_api_charge': False,
              'certifi_source': certifi_source,
              'scope': 'Mock DeepSeek Chat Completions and local key endpoint; no real key, account, or paid request.'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
