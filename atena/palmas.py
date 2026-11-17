"""Detector de palmas (sem IA, só matemática do som).

Uma palma é um som:
  1. que começa de repente (sobe muito de um bloco de 30 ms pro outro),
  2. curtíssimo (morre em menos de ~150 ms, a voz dura bem mais),
  3. "chiado" (cheio de agudos, diferente do tom da voz).
O padrão é N palmas com 0,12–0,8 s entre elas e depois silêncio, assim
3 palmas não disparam o modo de 2, e música/aplausos contínuos não disparam.
"""
from __future__ import annotations

import numpy as np

SEG_BLOCO = 0.03  # cada bloco tem 30 ms


class DetectorPalmas:
    def __init__(self, quantidade: int = 2, sensibilidade: float = 1.0):
        self.quantidade = max(1, int(quantidade))
        self.sensibilidade = float(sensibilidade)  # >1 = precisa de palma mais forte
        self.reiniciar()

    def reiniciar(self) -> None:
        self._t = 0.0
        self._anterior = 0.0
        self._ruido = 150.0
        self._candidata = None   # (inicio, pico, blocos_desde_inicio)
        self._palmas: list[float] = []

    # ------------------------------------------------------------------
    @staticmethod
    def _agudos(a: np.ndarray, rms: float) -> float:
        """Razão de energia aguda: ~0.1–0.4 na voz, ~0.6–1.4 em palma/estalo."""
        if rms <= 1:
            return 0.0
        return float(np.sqrt(np.mean(np.diff(a) ** 2)) / rms)

    def alimentar(self, bloco: bytes | np.ndarray) -> bool:
        """Passe cada bloco de áudio (int16, 16 kHz). Devolve True quando o padrão de palmas fecha."""
        a = np.frombuffer(bloco, dtype=np.int16).astype(np.float32) if isinstance(bloco, (bytes, bytearray)) \
            else bloco.astype(np.float32)
        rms = float(np.sqrt(np.mean(a * a))) if a.size else 0.0
        self._t += SEG_BLOCO
        disparou = False

        limiar = max(1800.0, self._ruido * 9) * self.sensibilidade

        if self._candidata is None:
            subida = rms > limiar and rms > self._anterior * 3.0
            if subida and self._agudos(a, rms) > 0.45:
                self._candidata = [self._t, rms, 0]
        else:
            self._candidata[2] += 1
            inicio, pico, n = self._candidata
            pico = max(pico, rms)
            self._candidata[1] = pico
            if rms < pico * 0.28:                 # morreu rápido: é palma
                self._registrar(inicio)
                self._candidata = None
            elif n >= 5:                          # durou demais (>150 ms): é voz/barulho longo
                self._candidata = None
                self._palmas.clear()

        # fecha o padrão: passou tempo suficiente desde a última palma
        if self._palmas and self._candidata is None and self._t - self._palmas[-1] > 0.65:
            disparou = len(self._palmas) == self.quantidade
            self._palmas.clear()

        if rms < limiar:  # ruído ambiente se ajusta devagar
            self._ruido = 0.97 * self._ruido + 0.03 * max(rms, 40.0)
        self._anterior = rms
        return disparou

    def _registrar(self, instante: float) -> None:
        if self._palmas:
            intervalo = instante - self._palmas[-1]
            if intervalo < 0.12:     # eco da mesma palma
                return
            if intervalo > 0.8:      # longe demais: começa uma sequência nova
                self._palmas.clear()
        self._palmas.append(instante)
