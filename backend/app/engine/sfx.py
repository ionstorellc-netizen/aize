"""Procedurally synthesised sound effects and an ambient music bed.

Everything here is generated from math at first run, so there is no licensing question.
Users can add their own licensed music in the B-Roll Library (kind=music).
"""
import wave

import numpy as np

from ..config import SFX_DIR, MUSIC_DIR

SR = 44100


def _write(path, x):
    x = np.clip(x, -1, 1)
    st = np.stack([x, x], axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((st * 32767 * 0.9).astype(np.int16).tobytes())


def _env(n, attack, release):
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    if a:
        e[:a] = np.linspace(0, 1, a) ** 2
    if r:
        e[-r:] *= np.linspace(1, 0, r) ** 2
    return e


def _noise(n, seed=1):
    return np.random.default_rng(seed).standard_normal(n)


def _sweep_filter(x, f0, f1):
    """Cheap time-varying one-pole low-pass to make noise 'move' (whoosh)."""
    n = len(x)
    fc = np.geomspace(f0, f1, n)
    alpha = 1 - np.exp(-2 * np.pi * fc / SR)
    y = np.zeros(n)
    acc = 0.0
    for i in range(n):
        acc += alpha[i] * (x[i] - acc)
        y[i] = acc
    return y


def whoosh(d=0.45):
    n = int(d * SR)
    x = _noise(n, 3)
    up = _sweep_filter(x, 300, 6000)
    hp = up - _sweep_filter(up, 150, 400)
    e = np.sin(np.linspace(0, np.pi, n)) ** 1.6
    y = hp * e
    return y / (np.abs(y).max() + 1e-9)


def click(d=0.05):
    n = int(d * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 140) + 0.4 * _noise(n, 5) * np.exp(-t * 400)
    return y / np.abs(y).max()


def pop(d=0.12):
    n = int(d * SR)
    t = np.arange(n) / SR
    f = 900 * np.exp(-t * 18) + 250
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35)
    return y / np.abs(y).max()


def impact(d=0.6):
    n = int(d * SR)
    t = np.arange(n) / SR
    f = 110 * np.exp(-t * 6) + 42
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
    hit = _sweep_filter(_noise(n, 9), 2000, 200) * np.exp(-t * 30)
    y = body + 0.5 * hit
    return y / np.abs(y).max()


def notify(d=0.35):
    n = int(d * SR)
    t = np.arange(n) / SR
    y = np.where(t < 0.12, np.sin(2 * np.pi * 988 * t), np.sin(2 * np.pi * 1319 * t))
    y = y * _env(n, 0.005, 0.2) * np.exp(-t * 4)
    return y / np.abs(y).max()


def ambient_pad(seconds=75.0):
    """Soft, slow-moving chord bed (Am - F - C - G), low-passed. Meant to sit ~-27 dB under the voice."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    chords = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [130.81, 196.0, 261.63], [196.0, 246.94, 293.66]]
    seg = 4.0
    y = np.zeros(n)
    for i, ch in enumerate(chords * int(np.ceil(seconds / (seg * 4)))):
        s, e = int(i * seg * SR), min(n, int((i + 1) * seg * SR + 0.8 * SR))
        if s >= n:
            break
        tt = t[s:e] - t[s]
        env = np.minimum(1, tt / 1.2) * np.minimum(1, np.maximum(0, (e - s) / SR - tt) / 1.2)
        for f in ch:
            y[s:e] += env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 2.003 * tt)) / 3
    y += 0.02 * _sweep_filter(_noise(n, 11), 800, 800)
    trem = 0.85 + 0.15 * np.sin(2 * np.pi * 0.2 * t)
    y *= trem
    return y / np.abs(y).max() * 0.8


SFX = {"whoosh": whoosh, "click": click, "pop": pop, "impact": impact, "notify": notify}


def ensure_assets():
    paths = {}
    for name, fn in SFX.items():
        p = SFX_DIR / f"{name}.wav"
        if not p.exists():
            _write(p, fn())
        paths[name] = p
    pad = MUSIC_DIR / "generated_pad.wav"
    if not pad.exists():
        _write(pad, ambient_pad())
    paths["generated_pad"] = pad
    return paths
