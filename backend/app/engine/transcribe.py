"""Local speech recognition with word timestamps (faster-whisper). Outputs Roman script by default."""
import threading
import wave
from pathlib import Path

import numpy as np

from ..config import whisper_model_path, WHISPER_DEVICE, WHISPER_COMPUTE
from ..util import ffmpeg, StageError

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    with _lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise StageError("faster-whisper is not installed (pip install faster-whisper).") from e
            _model = WhisperModel(whisper_model_path(), device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE)
        return _model


def _load_wav(path: Path, workdir: Path):
    wav = workdir / (path.stem + "_16k.wav")
    ffmpeg("-i", str(path), "-vn", "-ac", "1", "-ar", "16000", str(wav))
    with wave.open(str(wav)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return a


def transcribe(path: Path, workdir: Path, roman=True, prompt=None):
    """Returns {"language", "words": [{"w","s","e","p"}], "segments": [{"s","e","text"}]}.

    roman=True: decode with an English language token plus a Roman-Urdu prompt. For Urdu/Hindi speech
    this makes Whisper write Roman Urdu (Latin script) instead of Urdu/Devanagari script, while
    English business terms stay in English.
    """
    audio = _load_wav(Path(path), Path(workdir))
    m = _get_model()
    kw = dict(word_timestamps=True, vad_filter=False, beam_size=5, condition_on_previous_text=True)
    if roman:
        kw.update(language="en", initial_prompt=prompt)
    segs, info = m.transcribe(audio, **kw)
    words, segments = [], []
    for s in segs:
        segments.append({"s": round(s.start, 3), "e": round(s.end, 3), "text": s.text.strip()})
        for w in s.words or []:
            t = w.word.strip()
            if t:
                words.append({"w": t, "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 3)})
    return {"language": info.language, "duration": round(len(audio) / 16000, 3), "words": words, "segments": segments}
