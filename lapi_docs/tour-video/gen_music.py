"""A soft, original music bed: warm pads over a gentle plucked arpeggio, quiet enough to sit under a voice."""
import math, pathlib, sys, wave
import numpy as np

OUT = pathlib.Path(__file__).parent
SR = 44100
LENGTH = float(sys.argv[1]) if len(sys.argv) > 1 else 75.0
BPM = 72
BEAT = 60 / BPM
# Chord loop (two bars each): C major 7, A minor 7, F major 7, G major add9 — calm and hopeful.
CHORDS = [[261.63, 329.63, 392.00, 493.88], [220.00, 261.63, 329.63, 392.00], [174.61, 220.00, 261.63, 329.63], [196.00, 246.94, 293.66, 440.00]]
BAR = BEAT * 4


def pad(freq, t, attack=1.6, release=1.4, length=BAR * 2):
    env = np.clip(t / attack, 0, 1) * np.clip((length - t) / release, 0, 1)
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t + 0.3) + 0.18 * np.sin(2 * np.pi * freq * 3 * t)
    shimmer = 1 + 0.03 * np.sin(2 * np.pi * 0.21 * t)  # slow movement
    return env * tone * shimmer


def pluck(freq, t, length=0.9):
    env = np.exp(-4.2 * t) * (t < length)
    return env * (np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 2 * t) * np.exp(-6 * t))


n = int(SR * LENGTH)
mix = np.zeros(n, dtype=np.float64)
time_axis = np.arange(n) / SR
chord_len = BAR * 2
for k in range(int(math.ceil(LENGTH / chord_len)) + 1):
    chord = CHORDS[k % len(CHORDS)]
    start = k * chord_len
    s0 = int(start * SR); s1 = min(n, int((start + chord_len + 1.5) * SR))
    if s0 >= n: break
    t = np.arange(s1 - s0) / SR
    for j, f in enumerate(chord):
        mix[s0:s1] += 0.11 * pad(f / 2 if j == 0 else f, t) / (1 + 0.25 * j)
    # Arpeggio: eighth notes over the chord, slightly humanised.
    for step in range(int(chord_len / (BEAT / 2))):
        at = start + step * BEAT / 2 + (0.012 if step % 2 else 0)
        a0 = int(at * SR); a1 = min(n, a0 + int(1.0 * SR))
        if a0 >= n: break
        note = chord[(step * 2) % len(chord)] * (2 if step % 4 == 3 else 1)
        mix[a0:a1] += 0.055 * pluck(note, np.arange(a1 - a0) / SR)
# Fade in and out, gentle low-pass by averaging, normalise.
fade = np.ones(n); fi = int(2.5 * SR); fo = int(4.0 * SR)
fade[:fi] = np.linspace(0, 1, fi); fade[-fo:] = np.linspace(1, 0, fo)
mix *= fade
kernel = np.ones(24) / 24
mix = np.convolve(mix, kernel, mode='same')
mix = mix / (np.max(np.abs(mix)) + 1e-9) * 0.6
stereo = np.stack([mix * (1 + 0.04 * np.sin(2 * np.pi * 0.07 * time_axis)), mix * (1 - 0.04 * np.sin(2 * np.pi * 0.07 * time_axis))], axis=1)
with wave.open(str(OUT / 'music.wav'), 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(stereo, -1, 1) * 32767).astype(np.int16).tobytes())
print('music.wav', LENGTH, 'seconds')
