"""Testa o detector de palmas com sons sintéticos (palma = estalo curto e chiado; voz = tom sustentado)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from athena.palmas import DetectorPalmas  # noqa: E402

TAXA = 16000
rng = np.random.default_rng(1)


def silencio(seg):
    return rng.normal(0, 60, int(TAXA * seg))


def palma(forca=14000):
    n = int(TAXA * 0.06)
    env = np.exp(-np.arange(n) / (TAXA * 0.009))
    return rng.normal(0, 1, n) * env * forca


def voz(seg=0.5, forca=5000):
    t = np.arange(int(TAXA * seg)) / TAXA
    sinal = sum(np.sin(2 * np.pi * f * t) / (k + 1) for k, f in enumerate((140, 280, 420, 700, 1100)))
    ataque = np.minimum(1, t / 0.03)
    return sinal * ataque * forca / 2


def batida(seg=0.12, forca=15000):  # porta/mesa: grave e mais longa
    t = np.arange(int(TAXA * seg)) / TAXA
    return np.sin(2 * np.pi * 90 * t) * np.exp(-t / 0.08) * forca


def rodar(audio, quantidade=2):
    d = DetectorPalmas(quantidade)
    a = np.clip(audio, -32768, 32767).astype(np.int16)
    disparos = 0
    for i in range(0, len(a) - 480, 480):
        disparos += d.alimentar(a[i:i + 480].tobytes())
    return disparos


def seq(*partes):
    return np.concatenate(partes)


def test_duas_palmas():
    assert rodar(seq(silencio(1), palma(), silencio(0.3), palma(), silencio(1.2))) == 1


def test_duas_palmas_ritmo_lento():
    assert rodar(seq(silencio(1), palma(), silencio(0.6), palma(), silencio(1.2))) == 1


def test_uma_palma_nao_dispara_modo_2():
    assert rodar(seq(silencio(1), palma(), silencio(1.5))) == 0


def test_tres_palmas_nao_disparam_modo_2():
    assert rodar(seq(silencio(1), palma(), silencio(0.3), palma(), silencio(0.3), palma(), silencio(1.2))) == 0


def test_tres_palmas_modo_3():
    assert rodar(seq(silencio(1), palma(), silencio(0.3), palma(), silencio(0.3), palma(), silencio(1.2)), 3) == 1


def test_palmas_muito_separadas():
    assert rodar(seq(silencio(1), palma(), silencio(1.5), palma(), silencio(1.2))) == 0


@pytest.mark.parametrize("forca", [3000, 8000, 16000])
def test_voz_nao_dispara(forca):
    fala = seq(silencio(0.5), voz(0.4, forca), silencio(0.15), voz(0.3, forca), silencio(0.2), voz(0.5, forca),
               silencio(1.2))
    assert rodar(fala) == 0


def test_batida_grave_nao_dispara():
    assert rodar(seq(silencio(1), batida(), silencio(0.3), batida(), silencio(1.2))) == 0


def test_palmas_com_voz_em_volta():
    audio = seq(silencio(0.5), voz(0.6), silencio(0.9), palma(), silencio(0.35), palma(), silencio(1.2))
    assert rodar(audio) == 1
