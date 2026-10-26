"""Offline public-provider integration checks. No login or inference requests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import bridge
import fed_phrasing as phrasing
import providers
import streaming


SOURCE = 'Labor demand is softening, but PCE inflation may not decline.'
RESULT = {'chinese': '劳动力需求正在减弱，但PCE通胀可能不会下降。',
          'review': True, 'note': '请核实听写。'}
VERIFIED_MODULE_SHA256 = 'be7e70adddcb648f8697ff652c2aa63c2c2d0a435f9ad391eaeb2c1ff15d0e92'


def split_prompt(prompt):
    instruction, raw = prompt.split(phrasing.MARKER, 1)
    return instruction, json.loads(raw)


class FedPhrasingTests(unittest.TestCase):
    def test_selected_app_and_platforms_use_the_verified_module(self):
        repo = Path(__file__).resolve().parents[1]
        paths = [Path(phrasing.__file__).resolve()]
        paths.extend(repo / platform / 'app/fed_phrasing.py' for platform in ('windows', 'mac'))
        for path in paths:
            with self.subTest(path=str(path)):
                # Git can check out LF or CRLF. Verify source content on both hosts.
                raw = path.read_bytes().replace(b'\r\n', b'\n')
                self.assertEqual(hashlib.sha256(raw).hexdigest(), VERIFIED_MODULE_SHA256)

    def test_each_semantic_distinction_is_selected_when_relevant(self):
        examples = {
            'growth_moderation': 'There has been moderation in growth.',
            'policy_stance': 'The policy stance remains restrictive.',
            'inflation_direction': 'Disinflation may not continue.',
            'labor': 'Hiring has slowed.',
            'rate_units': 'Reduce the rate by 25 basis points to 4 percent.',
            'pce': 'Real personal consumption expenditures rose.',
            'measurement_basis': 'Real GDP grew at an annualized rate.',
        }
        for key, source in examples.items():
            with self.subTest(key=key):
                self.assertIn(key, phrasing.fed_usage_hints(source))

    def test_hints_are_bounded_even_when_every_rule_matches(self):
        source = ('Moderation in growth. Restrictive policy. Disinflation. '
                  'Labor market. 25 basis points. PCE. Annualized real GDP.')
        hints = phrasing.fed_usage_hints(source)
        self.assertGreater(len(hints), 0)
        self.assertLessEqual(len(hints), phrasing.MAX_HINTS)
        self.assertLessEqual(len(json.dumps(hints, ensure_ascii=False)), phrasing.MAX_HINT_CHARS)

    def test_hints_depend_only_on_current_source_not_previous_topic(self):
        _, payload = split_prompt(bridge.translation_prompt(
            'Bake the bread slowly.', SOURCE, {'PCE': '个人消费支出'}))
        self.assertEqual(payload['fed_usage'], {})

    def test_wrapper_preserves_original_data_and_has_fixed_instructions(self):
        glossary = {'PCE': '用户定义的PCE', 'labor demand': '劳动力需求'}
        original_glossary = glossary.copy()
        for source in (SOURCE, 'Moderation and growth.', 'Bake the bread slowly.'):
            with self.subTest(source=source):
                with patch.object(bridge, 'augment_prompt', side_effect=lambda prompt, profile: prompt):
                    original = bridge.translation_prompt(source, 'context ' * 400, glossary)
                actual = bridge.translation_prompt(source, 'context ' * 400, glossary)
                base_instruction, base_data = split_prompt(original)
                instruction, data = split_prompt(actual)
                self.assertEqual(instruction, base_instruction + phrasing.FED_STYLE_INSTRUCTION)
                self.assertEqual(data.pop('fed_usage'), phrasing.fed_usage_hints(source))
                self.assertEqual(data, base_data)
                self.assertEqual(data['current'], source)
                self.assertEqual(len(data['previous']), 1800)
        self.assertEqual(glossary, original_glossary)

    def test_general_profile_is_byte_for_byte_unchanged(self):
        for source in (SOURCE, 'Bake the bread slowly.'):
            with self.subTest(source=source):
                with patch.object(bridge, 'augment_prompt', side_effect=lambda prompt, profile: prompt):
                    original = bridge.translation_prompt(source, SOURCE, {'PCE': '测试'}, 'general')
                actual = bridge.translation_prompt(source, SOURCE, {'PCE': '测试'}, 'general')
                self.assertEqual(actual, original)
                self.assertNotIn('fed_usage', split_prompt(actual)[1])
                self.assertEqual(phrasing.fed_usage_hints(source, 'general'), {})

    def test_all_provider_entrypoints_send_the_same_augmented_prompt_once(self):
        # Mock every external boundary; only the actual public routing/prompt code runs.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for profile in ('fed', 'general'):
                expected = bridge.translation_prompt(SOURCE, '', {}, profile)
                for provider in ('chatgpt', 'grok', 'gemini'):
                    with self.subTest(profile=profile, provider=provider):
                        process = Mock(returncode=0, stderr='', stdout=json.dumps(RESULT))
                        with patch.object(bridge, 'ROOT', root), \
                             patch.object(bridge, 'login_status', return_value={'ready': True}), \
                             patch.object(bridge, 'codex_path', return_value='mock-codex'), \
                             patch.object(bridge, 'settings', return_value={}), \
                             patch.object(bridge, 'environment', return_value={}), \
                             patch.object(providers, 'login_status', return_value={'ready': True}), \
                             patch.object(providers, 'environment', return_value={}), \
                             patch.object(providers, 'home', return_value=root), \
                             patch.object(providers, 'clear_transient_history'), \
                             patch.object(providers, 'cli', return_value=['mock-cli']), \
                             patch.object(bridge.subprocess, 'run', return_value=process) as run:
                            result, _ = providers.translate(SOURCE, '', {}, profile=profile, provider=provider)
                        self.assertEqual(result, RESULT)
                        run.assert_called_once()
                        command = run.call_args.args[0]
                        prompt = (command[command.index('-p') + 1] if provider == 'grok'
                                  else run.call_args.kwargs['input'])
                        self.assertEqual(prompt, expected)
                        if provider == 'chatgpt':
                            self.assertEqual(command[command.index('-m') + 1], 'gpt-6-luna')
                            self.assertIn('model_reasoning_effort="low"', command)
                            self.assertIn('--ephemeral', command)
                        elif provider == 'grok':
                            self.assertEqual(command[command.index('--max-turns') + 1], '1')

    def test_streaming_receives_identical_prompt_and_keeps_callback(self):
        callback = Mock()
        with patch.object(streaming, 'translate', return_value=(RESULT, 0.1)) as translate, \
             patch.object(bridge.subprocess, 'run') as run:
            result = providers.translate(SOURCE, '', {}, 'gpt-6-luna',
                                         on_partial=callback, session_id='test-session')
        self.assertEqual(result, (RESULT, 0.1))
        translate.assert_called_once_with(bridge.translation_prompt(SOURCE, '', {}),
                                          'gpt-6-luna', 'test-session', callback)
        run.assert_not_called()

    def test_prepared_instructions_match_every_live_chunk_without_inference(self):
        for profile in ('fed', 'general'):
            cancelled = Mock(return_value=False)
            with self.subTest(profile=profile), \
                 patch.object(streaming.CLIENT, 'prepare') as prepare, \
                 patch.object(bridge.subprocess, 'run') as run:
                providers.prepare_session(model='gpt-6-luna', profile=profile,
                                          session_id='test-session', cancelled=cancelled)
                prepare.assert_called_once()
                instruction = prepare.call_args.args[0]
                for source in ('', SOURCE, 'Growth has moderated.', 'Bake the bread slowly.'):
                    self.assertEqual(instruction, split_prompt(
                        bridge.translation_prompt(source, SOURCE, {}, profile))[0])
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
