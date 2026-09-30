"""GPU acceleration must never make CPU-only receivers unusable."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from gpu_runtime import SpeechRuntime


class GpuFallbackTests(unittest.TestCase):
    def setUp(self):
        self.model_path_patch = patch('gpu_runtime.model_path', return_value='test-local-model')
        self.model_path_patch.start()
        self.addCleanup(self.model_path_patch.stop)

    def test_missing_optional_runtime_loads_cpu_without_probing_gpu(self):
        runtime = SpeechRuntime()
        with patch('gpu_runtime.enable_local_cuda', return_value=False), patch('faster_whisper.WhisperModel') as model:
            runtime.load()
        self.assertEqual(runtime.backend, 'cpu')
        self.assertEqual(model.call_args.kwargs['device'], 'cpu')

    def test_failed_gpu_compute_falls_back_before_ready(self):
        runtime = SpeechRuntime()
        gpu, cpu = Mock(), Mock()
        gpu.feature_extractor.mel_filters.shape = (80, 201)
        gpu.encode.side_effect = RuntimeError('missing CUDA runtime')
        with patch('gpu_runtime.enable_local_cuda', return_value=True), patch('ctranslate2.get_cuda_device_count', return_value=1), patch('faster_whisper.WhisperModel', side_effect=[gpu, cpu]):
            runtime.load()
        self.assertIs(runtime.model, cpu)
        self.assertEqual(runtime.backend, 'cpu')

    def test_gpu_failure_during_iteration_retries_whole_audio_once_on_cpu(self):
        runtime = SpeechRuntime()
        gpu, cpu = Mock(), Mock()
        runtime.model, runtime.backend = gpu, 'cuda'
        def failed():
            yield 'partial GPU result'
            raise RuntimeError('CUDA out of memory')
        gpu.transcribe.return_value = (failed(), None)
        cpu.transcribe.return_value = (iter(['complete CPU result']), None)
        with patch('faster_whisper.WhisperModel', return_value=cpu):
            result = runtime.decode_segments('same-audio', beam_size=3)
        self.assertEqual(result, ['complete CPU result'])
        self.assertEqual(runtime.backend, 'cpu')
        cpu.transcribe.assert_called_once_with('same-audio', beam_size=3)

    def test_cpu_errors_remain_errors(self):
        runtime = SpeechRuntime()
        runtime.model = Mock()
        runtime.model.transcribe.side_effect = RuntimeError('decode failed')
        with self.assertRaises(RuntimeError):
            runtime.decode_segments('audio')

    def test_repeated_characters_cannot_enter_translator_or_context(self):
        runtime = SpeechRuntime()
        runtime.model = Mock()
        runtime.model.transcribe.return_value = ([SimpleNamespace(text='____' * 20)], None)
        with self.assertRaises(RuntimeError):
            runtime.decode_segments('audio')

    def test_degenerate_hint_is_removed_for_one_bounded_relisten(self):
        runtime = SpeechRuntime()
        runtime.model = Mock()
        runtime.model.transcribe.side_effect = [([SimpleNamespace(text='_' * 80)], None), ([SimpleNamespace(text='Rates remain unchanged.')], None)]
        rows = runtime.decode_segments('audio', initial_prompt='bad hint', hotwords='bad')
        self.assertEqual(rows[0].text, 'Rates remain unchanged.')
        self.assertEqual(runtime.model.transcribe.call_count, 2)
        self.assertIsNone(runtime.model.transcribe.call_args.kwargs['initial_prompt'])
        self.assertTrue(runtime.recovered_decode)


if __name__ == '__main__':
    unittest.main()
