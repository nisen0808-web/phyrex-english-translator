"""Run offline Fed wording checks against the selected source or unpacked app."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    app = args.app.resolve()
    if not (app / 'fed_phrasing.py').is_file():
        parser.error('The selected app must contain fed_phrasing.py.')

    # Also enforce -B behavior when a caller forgets to pass the interpreter flag.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(app))
    with tempfile.TemporaryDirectory(prefix='phyrex-fed-wording-test-') as folder:
        os.environ['FED_TRANSLATOR_USER_DIR'] = folder
        import test_fed_phrasing
        suite = unittest.defaultTestLoader.loadTestsFromModule(test_fed_phrasing)
        result = unittest.TextTestRunner(verbosity=2).run(suite)

    report = {
        'tests': result.testsRun,
        'passed': result.wasSuccessful(),
        'failures': len(result.failures),
        'errors': len(result.errors),
        'skipped': len(result.skipped),
        'platform': sys.platform,
        'real_inference': False,
        'real_login': False,
        'scope': ('Selected app wording content, bounded current-only hints, unchanged general '
                  'English and data fields, mocked ChatGPT/Grok/Gemini routes, streaming '
                  'callback and stable prewarm instructions; no account/model requests.'),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
