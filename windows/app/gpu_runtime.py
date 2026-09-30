"""Use optional local CUDA libraries; keep the same speech model and CPU fallback."""
import os
import re
from runtime import ROOT, model_path

_dll_handles = []
_registered = False


class UnstableDecode(RuntimeError):
    pass


def enable_local_cuda():
    global _registered
    if _registered:
        return True
    folder = ROOT / '.runtime/gpu'
    if os.name != 'nt' or not (folder / 'ready.txt').is_file():
        return False
    directories = [folder / 'nvidia/cublas/bin', folder / 'nvidia/cudnn/bin']
    if not all(path.is_dir() for path in directories):
        return False
    # Keep handles alive. Only this process changes its DLL search path.
    for path in directories:
        _dll_handles.append(os.add_dll_directory(str(path)))
    os.environ['PATH'] = os.pathsep.join(map(str, directories)) + os.pathsep + os.environ.get('PATH', '')
    _registered = True
    return True


class SpeechRuntime:
    def __init__(self):
        self.model = None
        self.backend = 'cpu'
        self._gpu_disabled = False
        self.recovered_decode = False

    @property
    def status_message(self):
        return '本地语音识别已就绪 · 显卡加速' if self.backend == 'cuda' else '本地语音识别已就绪 · CPU'

    def load(self):
        from faster_whisper import WhisperModel
        if not self._gpu_disabled:
            try:
                import ctranslate2
                if enable_local_cuda() and ctranslate2.get_cuda_device_count() > 0:
                    import numpy as np
                    candidate = WhisperModel(str(model_path()), device='cuda', compute_type='int8_float32', local_files_only=True)
                    # Model loading alone does not exercise cuBLAS/cuDNN.
                    candidate.encode(np.zeros((candidate.feature_extractor.mel_filters.shape[0], 3000), dtype=np.float32))
                    self.model, self.backend = candidate, 'cuda'
                    return
            except (RuntimeError, OSError, ValueError):
                self._gpu_disabled = True
        self.model = WhisperModel(str(model_path()), device='cpu', compute_type='int8',
                                  cpu_threads=6, local_files_only=True)
        self.backend = 'cpu'

    def decode_segments(self, *args, **kwargs):
        def materialize(model, options):
            segments, _ = model.transcribe(*args, **options)
            result = list(segments)
            text = ''.join(getattr(segment, 'text', '') for segment in result)
            if re.search(r'(?:[_\.]\s*){16,}', text):
                raise UnstableDecode('语音识别出现重复字符，请重试该段。')
            return result
        def decode(model):
            try:
                return materialize(model, kwargs)
            except UnstableDecode:
                # A context hint can propagate nonsense into later chunks.
                # Re-listen once without that hint; never use the bad draft.
                self.recovered_decode = True
                return materialize(model, {**kwargs, 'initial_prompt': None,
                                           'hotwords': None, 'no_repeat_ngram_size': 3})
        try:
            # Materialize before returning; never emit half a failed GPU pass.
            return decode(self.model)
        except RuntimeError:
            if self.backend != 'cuda':
                raise
            self.model = None
            self._gpu_disabled = True
            self.load()
            return decode(self.model)
