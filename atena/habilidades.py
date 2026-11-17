"""Habilidades: rotinas que a ATENA aprende (ideia inspirada no Hermes Agent).

Quando ela termina uma tarefa com vários passos, sugere: "quer que eu salve isso como habilidade?".
Depois é só falar o nome ("modo estudo") que ela repete tudo, sem precisar da IA pensar de novo.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import time

from .sistema import normalizar

# Passos que não fazem sentido repetir (só olham, ou dependem da conversa)
NAO_REPETIR = {"ver_tela", "ler_tela", "pesquisar_web", "info_sistema", "data_hora", "lembrar", "esquecer",
               "salvar_habilidade", "listar_habilidades", "executar_habilidade", "apagar_habilidade",
               "agendar", "listar_agendamentos", "cancelar_agendamento"}
FALHAS = ("falhou", "erro", "não achei", "nao achei", "bloqueado", "o usuário não", "cancelado", "parado",
          "ferramenta desconhecida", "argumentos inválidos", "não encontrei", "nenhum")
VERBOS = r"^(ativa|ativar|ativo|executa|executar|roda|rodar|liga|ligar|inicia|iniciar|faz|fazer|faca|bota|coloca|" \
         r"entra no|entra em|modo de)\s+"


def converter_passos(execucoes: list[tuple[str, dict, str]]) -> list[dict]:
    """[(ferramenta, args, resultado)] -> passos repetíveis (só os que deram certo)."""
    passos = []
    for nome, args, resultado in execucoes:
        if nome in NAO_REPETIR or nome.startswith("_"):
            continue
        if normalizar(resultado or "").startswith(tuple(normalizar(f) for f in FALHAS)):
            continue
        a = {k: v for k, v in (args or {}).items() if not str(k).startswith("_")}
        if nome == "clicar":  # número muda de uma tela pra outra: guarda o texto do botão
            m = re.search(r"em '(.+?)' na posição", resultado or "")
            if m:
                a["alvo"] = m.group(1)
            elif re.fullmatch(r"#?\d+", str(a.get("alvo", ""))):
                continue
        passos.append({"ferramenta": nome, "args": a})
    return passos


def descrever_passos(passos: list[dict]) -> str:
    rot = {"abrir_app": "abrir {nome}", "abrir_site": "abrir {url}", "tocar_youtube": "tocar {consulta}",
           "mostrar_pesquisa": "pesquisar {consulta}", "digitar_texto": "digitar texto", "apertar_teclas": "{teclas}",
           "volume": "volume {acao}", "controle_midia": "mídia {acao}", "clicar": "clicar em {alvo}",
           "rolar": "rolar {direcao}", "focar_janela": "ir pra {nome}", "timer": "timer {minutos} min",
           "criar_nota": "anotar", "energia": "{acao} o PC", "fechar_app": "fechar {nome}"}
    partes = []
    for p in passos:
        modelo = rot.get(p["ferramenta"], p["ferramenta"])
        try:
            partes.append(modelo.format(**{k: str(v)[:30] for k, v in p["args"].items()}))
        except (KeyError, IndexError):
            partes.append(modelo.split(" {")[0])
    return ", ".join(partes)


class Habilidades:
    def __init__(self, pasta):
        self.arquivo = os.path.join(str(pasta), "habilidades.json")
        self._trava = threading.Lock()
        self.lista: list[dict] = []
        self.carregar()

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

    def salvar(self, nome: str, passos: list[dict], gatilhos: list[str] | None = None) -> dict:
        nome = nome.strip().strip(".!?").lower()
        if not nome or not passos:
            raise ValueError("habilidade precisa de nome e de pelo menos um passo")
        with self._trava:
            self.lista = [h for h in self.lista if normalizar(h["nome"]) != normalizar(nome)]
            h = {"nome": nome, "gatilhos": [g.lower() for g in (gatilhos or [])], "passos": passos,
                 "criada": dt.datetime.now().isoformat(timespec="minutes"), "usos": 0}
            self.lista.append(h)
            self._gravar()
        return h

    def apagar(self, nome: str) -> bool:
        with self._trava:
            antes = len(self.lista)
            self.lista = [h for h in self.lista if normalizar(h["nome"]) != normalizar(nome)]
            self._gravar()
            return len(self.lista) < antes

    def procurar(self, texto: str) -> dict | None:
        """Reconhece 'modo estudo', 'ativa o modo estudo', 'executa modo estudo'..."""
        t = normalizar(texto)
        t = re.sub(r"^(atena|atena)\s+", "", t)
        t = re.sub(VERBOS, "", t)
        t = re.sub(r"^(o|a|meu|minha|a habilidade|habilidade)\s+", "", t).strip()
        if not t:
            return None
        for h in self.lista:
            nomes = [normalizar(h["nome"])] + [normalizar(g) for g in h.get("gatilhos", [])]
            if t in nomes or any(re.sub(r"^modo\s+", "", n) == t for n in nomes):
                return h
        return None

    def registrar_uso(self, h: dict) -> None:
        with self._trava:
            h["usos"] = int(h.get("usos", 0)) + 1
            h["ultimo_uso"] = dt.datetime.now().isoformat(timespec="minutes")
            self._gravar()


# esperas entre passos (apps demoram pra abrir)
ESPERA_DEPOIS = {"abrir_app": 2.5, "abrir_site": 2.0, "focar_janela": 0.8, "clicar": 0.8, "tocar_youtube": 1.5}


def executar(h: dict, executor, cancelar: threading.Event | None = None) -> list[str]:
    """Roda os passos com `executor(ferramenta, args) -> resultado`. Para se `cancelar` for ligado."""
    resultados = []
    for p in h["passos"]:
        if cancelar is not None and cancelar.is_set():
            resultados.append("cancelado")
            break
        resultados.append(executor(p["ferramenta"], dict(p.get("args") or {})))
        time.sleep(ESPERA_DEPOIS.get(p["ferramenta"], 0.3))
    return resultados
