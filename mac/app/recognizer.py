from terminology import recognition_hotwords
import time
from runtime import model_path
from profiles import profile_config

class Recognizer:
    def __init__(self):
        self.model = None

    def load(self):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(str(model_path()), device='cpu', compute_type='int8',
                                  cpu_threads=6, local_files_only=True)

    def transcribe(self, pcm, tail, context, keywords, profile='fed'):
        import numpy as np
        if self.model is None:
            self.load()
        audio = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.0
        lead = np.frombuffer(tail, dtype='<i2').astype(np.float32) / 32768.0
        lead_seconds = len(lead) / 16000
        if len(audio) < 320 or np.sqrt(np.mean(audio * audio)) < 0.00015:
            return '', 0.0, len(audio) / 16000, 0.0, False
        combined = np.concatenate([lead, audio])
        started = time.monotonic()
        segments, _ = self.model.transcribe(
            combined, language='en', beam_size=3, temperature=0,
            vad_filter=True, vad_parameters={'min_silence_duration_ms': 450},
            word_timestamps=True, condition_on_previous_text=False,
            initial_prompt=(profile_config(profile)['prompt'] + ' ' + context[-350:]),
            hotwords=recognition_hotwords(context, keywords, profile), hallucination_silence_threshold=1.5)
        words, uncertain = [], False
        for seg in segments:
            for w in seg.words or []:
                if (w.start + w.end) / 2 >= lead_seconds:
                    words.append(w)
                    uncertain = uncertain or w.probability < 0.35
        text = ''.join(w.word for w in words).strip()
        start = max(0, words[0].start - lead_seconds) if words else 0
        end = min(len(audio) / 16000, words[-1].end - lead_seconds) if words else len(audio) / 16000
        return text, float(start), float(max(start, end)), round(time.monotonic() - started, 2), bool(uncertain)
