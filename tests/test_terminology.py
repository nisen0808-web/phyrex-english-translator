import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from runtime import ROOT
from terminology import (translation_glossary, recognition_hotwords, validate_glossary,
                         TRANSLATION_MAX_CHARS, TRANSLATION_MAX_TERMS, ASR_MAX_CHARS)


class TerminologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.glossary = json.loads((ROOT / 'glossary.json').read_text(encoding='utf-8'))

    def test_catalog_counts_and_required_domains(self):
        info = json.loads((ROOT / 'glossary-info.json').read_text(encoding='utf-8'))
        self.assertEqual(len(self.glossary), 556)
        self.assertEqual(info['count'], sum(info['categories'].values()))
        self.assertEqual(len(info['categories']), 8)
        self.assertEqual(len(self.glossary), len({key.casefold() for key in self.glossary}))
        for key in ('Federal Reserve', 'labor force participation rate', 'JOLTS', 'core PCE inflation',
                    'final sales to private domestic purchasers', 'SOFR', 'IORB', 'CET1', 'SAAR'):
            self.assertIn(key, self.glossary)
        validate_glossary(self.glossary)

    def test_easily_confused_concepts_keep_distinct_translations(self):
        for left, right in [('disinflation', 'deflation'), ('basis points', 'percentage points'),
                            ('quits', 'separations'), ('labor force participation rate', 'employment-population ratio'),
                            ('not in the labor force', 'unemployed'), ('annualized', 'year over year')]:
            self.assertNotEqual(self.glossary[left], self.glossary[right])

    def test_no_substring_matching_and_supports_hyphens_case_and_plural(self):
        self.assertEqual(translation_glossary('A spicy recipe and a repository.', '', {'CPI': '物价', 'repo': '回购'}), {})
        result = translation_glossary('POLICY RATES and credit spreads rose year-over-year.', '', self.glossary)
        for key in ('policy rate', 'credit spread', 'year over year'):
            self.assertIn(key, result)

    def test_late_catalog_terms_and_context_are_usable(self):
        result = translation_glossary('The response rate and CET1 were stable.', 'The SLOOS survey showed tighter lending standards.', self.glossary)
        for key in ('response rate', 'CET1', 'SLOOS', 'lending standards'):
            self.assertIn(key, result)
        self.assertNotIn('soft landing', result)

    def test_current_content_wins_over_a_dense_previous_segment(self):
        previous = '. '.join(list(self.glossary)[:150])
        result = translation_glossary('The supplementary leverage ratio changed.', previous, self.glossary)
        self.assertEqual(next(iter(result)), 'supplementary leverage ratio')

    def test_long_phrases_take_priority_and_custom_meanings_are_retained(self):
        custom = {**self.glossary, 'core PCE inflation': '用户定义的核心PCE通胀'}
        result = translation_glossary('Core PCE inflation declined.', '', custom)
        self.assertEqual(next(iter(result)), 'core PCE inflation')
        self.assertEqual(result['core PCE inflation'], custom['core PCE inflation'])

    def test_dense_matching_payload_stays_bounded(self):
        result = translation_glossary('. '.join(self.glossary), '', self.glossary)
        self.assertLessEqual(len(result), TRANSLATION_MAX_TERMS)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), TRANSLATION_MAX_CHARS)
        custom = {f'special financial phrase {i}': '很长的术语含义' * 25 for i in range(100)}
        result = translation_glossary('. '.join(custom), '', custom)
        self.assertGreater(len(result), 0)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), TRANSLATION_MAX_CHARS)

    def test_hotwords_reach_beyond_first_fifty_without_unbounded_prompt(self):
        hint = recognition_hotwords('CET1 and unit labor costs were discussed.', list(self.glossary))
        self.assertIn('CET1', hint)
        self.assertIn('unit labor costs', hint)
        self.assertIn('Federal Reserve', hint)
        self.assertLessEqual(len(hint), ASR_MAX_CHARS)
        self.assertLessEqual(len(hint.split(', ')), 20)

    def test_general_english_never_receives_finance_hints(self):
        self.assertEqual(translation_glossary('CPI and JOLTS', '', self.glossary, 'general'), {})
        self.assertEqual(recognition_hotwords('CPI and JOLTS', list(self.glossary), 'general'), '')

    def test_editing_capacity_and_malformed_input(self):
        validate_glossary({str(i): '术语' for i in range(1000)})
        for invalid in ({str(i): '术语' for i in range(1001)}, {' ': '词'}, {'term': ' '}, {'x': 1}, [], {'x' * 121: '术语'}):
            with self.assertRaises(ValueError):
                validate_glossary(invalid)

    def test_actual_translation_bridge_passes_selected_glossary_to_cli(self):
        import bridge
        process = Mock(returncode=0, stdout=json.dumps({'chinese': '单位劳动力成本下降。', 'review': False, 'note': ''}), stderr='')
        with patch('bridge.login_status', return_value={'ready': True}), patch('bridge.subprocess.run', return_value=process) as run:
            bridge.translate('Unit labor costs declined.', '', self.glossary)
        prompt = run.call_args.kwargs['input']
        payload = json.loads(prompt.split('资料 JSON：\n', 1)[1])
        self.assertIn('unit labor costs', payload['glossary'])
        self.assertNotIn('Federal Reserve', payload['glossary'])
        self.assertEqual(payload['current'], 'Unit labor costs declined.')
        self.assertIn('同比与年化环比', prompt)

    def test_actual_recognizer_passes_topic_terms_and_locks_english(self):
        from recognizer import Recognizer
        recognizer = Recognizer()
        recognizer.model = Mock()
        recognizer.model.transcribe.return_value = ([], None)
        recognizer.transcribe(b'\x01\x10' * 16000, b'', 'Unit labor costs declined.', list(self.glossary))
        args = recognizer.model.transcribe.call_args.kwargs
        self.assertIn('unit labor costs', args['hotwords'])
        self.assertEqual(args['language'], 'en')


if __name__ == '__main__':
    unittest.main(verbosity=2)
