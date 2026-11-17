"""Rotinas agendadas: "Atena, todo dia às 7h me dá o resumo do dia".

Cada rotina guarda um pedido (texto, como se você tivesse falado) ou o nome de uma habilidade,
e quando ele roda. Um relógio em segundo plano confere a cada 15 segundos.
Se o PC estava desligado na hora, a rotina pula aquele dia (não roda atrasada horas depois).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import time
import uuid

DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
PRESETS_DIAS = {"todo_dia": DIAS, "dias_uteis": DIAS[:5], "fim_de_semana": DIAS[5:]}
TOLERANCIA_MIN = 3  # roda se o relógio passar da hora em até 3 min (PC acordando, etc.)


def _hora(texto: str) -> tuple[int, int]:
    m = re.search(r"(\d{1,2})(?:[:h](\d{2}))?", str(texto))
    if not m:
        raise ValueError(f"hora inválida: {texto}")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if not (0 <= h < 24 and 0 <= mi < 60):
        raise ValueError(f"hora inválida: {texto}")
    return h, mi


def _dias(valor) -> list[str]:
    if not valor:
        return []
    if isinstance(valor, str):
        v = valor.lower().strip()
        if v in PRESETS_DIAS:
            return PRESETS_DIAS[v]
        valor = re.split(r"[,\s]+", v)
    saida = []
    for d in valor:
        d = str(d).lower()[:3].replace("sáb", "sab").replace("sá", "sa")
        if d in DIAS and d not in saida:
            saida.append(d)
    return saida


def descrever(r: dict) -> str:
    h = r["hora"]
    dias = r.get("dias") or []
    if not dias:
        quando = f"em {r.get('data', '?')} às {h}"
    elif dias == DIAS:
        quando = f"todo dia às {h}"
    elif dias == DIAS[:5]:
        quando = f"dias úteis às {h}"
    elif dias == DIAS[5:]:
        quando = f"fim de semana às {h}"
    else:
        quando = f"{', '.join(dias)} às {h}"
    oque = f"habilidade “{r['habilidade']}”" if r.get("habilidade") else f"“{r.get('pedido', '')}”"
    return f"{quando}: {oque}"


class Agenda:
    def __init__(self, pasta, ao_disparar=None):
        self.arquivo = os.path.join(str(pasta), "agenda.json")
        self.ao_disparar = ao_disparar or (lambda rotina: None)
        self._trava = threading.Lock()
        self._rodando = threading.Event()
        self.lista: list[dict] = []
        self.carregar()

    # ---------------------------------------------------------------- arquivo
    def carregar(self) -> None:
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                self.lista = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.lista = []

    def _gravar(self) -> None:
        os.makedirs(os.path.dirname(self.arquivo), exist_ok=True)
        tmp = self.arquivo + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.lista, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.arquivo)

    # ---------------------------------------------------------------- criar / apagar
    def adicionar(self, hora: str, pedido: str = "", habilidade: str = "", dias=None, data: str = "",
                  agora: dt.datetime | None = None) -> dict:
        agora = agora or dt.datetime.now()
        h, mi = _hora(hora)
        dias = _dias(dias)
        if not pedido and not habilidade:
            raise ValueError("diga o que fazer (pedido ou habilidade)")
        r = {"id": uuid.uuid4().hex[:6], "hora": f"{h:02d}:{mi:02d}", "dias": dias,
             "pedido": pedido.strip(), "habilidade": habilidade.strip().lower(), "ativa": True,
             "ultima": None, "criada": agora.isoformat(timespec="minutes")}
        if not dias:  # uma vez só: hoje, ou amanhã se a hora já passou
            if data:
                dia = dt.date.fromisoformat(data)
            else:
                dia = agora.date()
                if (h, mi) <= (agora.hour, agora.minute):
                    dia += dt.timedelta(days=1)
            r["data"] = dia.isoformat()
        with self._trava:
            self.lista.append(r)
            self._gravar()
        return r

    def cancelar(self, chave: str) -> int:
        """Apaga por id ou por um pedaço do texto."""
        c = chave.lower().strip()
        with self._trava:
            antes = len(self.lista)
            self.lista = [r for r in self.lista if r["id"] != c and c not in (r.get("pedido", "") + " "
                                                                             + r.get("habilidade", "")).lower()]
            self._gravar()
            return antes - len(self.lista)

    # ---------------------------------------------------------------- relógio
    def vencidas(self, agora: dt.datetime | None = None) -> list[dict]:
        agora = agora or dt.datetime.now()
        saida = []
        for r in self.lista:
            if not r.get("ativa", True):
                continue
            h, mi = _hora(r["hora"])
            if r.get("dias"):
                if DIAS[agora.weekday()] not in r["dias"]:
                    continue
                alvo = agora.replace(hour=h, minute=mi, second=0, microsecond=0)
                if r.get("ultima") == agora.date().isoformat():
                    continue
            else:
                alvo = dt.datetime.fromisoformat(f"{r['data']}T{h:02d}:{mi:02d}")
            atraso = (agora - alvo).total_seconds() / 60
            if 0 <= atraso <= TOLERANCIA_MIN:
                saida.append(r)
            elif not r.get("dias") and atraso > TOLERANCIA_MIN:
                r["ativa"] = False  # perdeu a hora (PC desligado): desliga sem rodar
        return saida

    def marcar_rodada(self, r: dict, agora: dt.datetime | None = None) -> None:
        agora = agora or dt.datetime.now()
        with self._trava:
            r["ultima"] = agora.date().isoformat()
            if not r.get("dias"):
                r["ativa"] = False
            self._gravar()

    def iniciar(self) -> None:
        if self._rodando.is_set():
            return
        self._rodando.set()
        threading.Thread(target=self._loop, daemon=True, name="agenda").start()

    def parar(self) -> None:
        self._rodando.clear()

    def _loop(self) -> None:
        while self._rodando.is_set():
            try:
                for r in self.vencidas():
                    self.marcar_rodada(r)
                    self.ao_disparar(r)
                with self._trava:  # limpa as de uma vez que já rodaram há mais de 1 dia
                    antes = len(self.lista)
                    self.lista = [r for r in self.lista if r.get("dias") or r.get("ativa")
                                  or (r.get("ultima") or "") >= (dt.date.today() - dt.timedelta(days=1)).isoformat()]
                    if len(self.lista) != antes:
                        self._gravar()
            except Exception as e:
                print(f"[agenda] erro: {e}")
            time.sleep(15)
