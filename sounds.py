"""用 numpy 现场合成音效，不需要外部音频文件。"""
import numpy as np
import pygame

SR = 44100


def _t(dur):
    return np.linspace(0, dur, int(SR * dur), False)


def _tone(freq, dur, decay=6.0, wave='sine'):
    t = _t(dur)
    if wave == 'square':
        sig = np.sign(np.sin(2 * np.pi * freq * t)) * 0.5
    elif wave == 'tri':
        sig = 2 * np.abs(2 * ((freq * t) % 1) - 1) - 1
    else:
        sig = np.sin(2 * np.pi * freq * t)
    env = np.exp(-decay * t) * np.minimum(1, t / 0.005)
    return sig * env


def _noise(dur, decay):
    t = _t(dur)
    return np.random.uniform(-1, 1, len(t)) * np.exp(-decay * t)


def _seq(parts, gap=0.0):
    pad = np.zeros(int(SR * gap))
    out = []
    for p in parts:
        out += [p, pad]
    return np.concatenate(out)


def _lowpass(sig, k):
    return np.convolve(sig, np.ones(k) / k, mode='same')


class Sounds:
    def __init__(self):
        self.ok = False
        self.s = {}
        try:
            init = pygame.mixer.get_init()
            if not init:
                return
            self.channels = init[2]
            self.ok = True
        except Exception:
            return
        self.s['click'] = self._make(_tone(1200, 0.05, 60) * 0.4)
        self.s['deal'] = self._make(_lowpass(_noise(0.04, 90), 4) * 0.35)
        self.s['select'] = self._make(_tone(1800, 0.03, 90) * 0.25)
        slap = _lowpass(_noise(0.12, 45), 6) * 0.8 + _tone(140, 0.12, 30) * 0.5
        self.s['play'] = self._make(slap * 0.7)
        self.s['pass'] = self._make(_seq([_tone(520, 0.1, 18, 'tri'), _tone(390, 0.16, 14, 'tri')]) * 0.35)
        self.s['bid'] = self._make(_seq([_tone(880, 0.12, 12), _tone(1175, 0.22, 10)]) * 0.35)
        boom_t = _t(1.2)
        sweep = np.sin(2 * np.pi * (90 - 50 * boom_t) * boom_t) * np.exp(-3 * boom_t)
        boom = _lowpass(_noise(1.2, 3.5), 25) * 2.2 + sweep * 0.9
        self.s['bomb'] = self._make(boom * 0.7)
        rt = _t(0.45)
        rise = np.sin(2 * np.pi * (300 + 1400 * rt) * rt) * 0.4 * np.minimum(1, rt / 0.05)
        self.s['rocket'] = self._make(np.concatenate([rise, boom]) * 0.7)
        self.s['plane'] = self._make(_seq([_tone(f, 0.08, 10, 'tri') for f in (523, 659, 784, 1047)]) * 0.35)
        self.s['warn'] = self._make(_seq([_tone(1000, 0.09, 8, 'square'), _tone(1000, 0.09, 8, 'square')], 0.05) * 0.2)
        notes = [523, 659, 784, 1047]
        win = _seq([_tone(f, 0.16, 7) + 0.4 * _tone(f * 2, 0.16, 9) for f in notes])
        win = np.concatenate([win, _tone(1047, 0.6, 3) + 0.5 * _tone(1319, 0.6, 3)])
        self.s['win'] = self._make(win * 0.35)
        lose = _seq([_tone(f, 0.25, 5, 'tri') for f in (392, 349, 311, 262)])
        self.s['lose'] = self._make(lose * 0.4)

    def _make(self, sig):
        sig = np.clip(sig, -1, 1)
        arr = (sig * 32000).astype(np.int16)
        if self.channels > 1:
            arr = np.ascontiguousarray(np.repeat(arr[:, None], self.channels, axis=1))
        return pygame.sndarray.make_sound(arr)

    def set_volume(self, v):
        for s in self.s.values():
            s.set_volume(max(0.0, min(1.0, v)))

    def play(self, name):
        if self.ok and name in self.s:
            self.s[name].play()
