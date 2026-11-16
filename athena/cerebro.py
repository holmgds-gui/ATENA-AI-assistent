"""O cérebro da ATHENA. Hoje: Ollama (IA local). Feito pra plugar outros depois (Gemini, Claude...)."""
from __future__ import annotations

import json
import platform
import re
from typing import Callable

import requests

from . import ferramentas
from .ferramentas import Contexto


def montar_prompt_sistema(config) -> str:
    p = config.personalidade
    nome, usuario = config.nome_ia, config.nome_usuario
    memoria = "\n".join(f"- {m}" for m in config.memoria) or "- (nada ainda)"
    return f"""Você é {nome} ({p.get('significado', '')}), a assistente pessoal de voz do {usuario}.
Você roda no computador dele ({platform.system()}) e consegue controlá-lo usando ferramentas:
abrir apps e sites, pesquisar na internet, digitar, apertar teclas, controlar volume e música, criar timers e notas.

PERSONALIDADE:
{p.get('estilo', '').strip()}

REGRAS:
{p.get('regras_extras', '').strip()}
- Chame o usuário de {usuario}.
- Agora é {ferramentas.descrever_data_hora()}.
- Se precisar de informação atual (notícias, preços, clima, resultados), use pesquisar_web antes de responder.
- Depois de usar uma ferramenta, confirme em poucas palavras o que fez. Não invente que fez algo que falhou.
- Nunca diga o nome das ferramentas nem fale de JSON; fale como uma pessoa.
- Se pedirem algo que você não tem ferramenta pra fazer, diga que essa permissão está desligada
  ou que ainda não sabe fazer isso, sem inventar.

O QUE VOCÊ SABE SOBRE O {usuario.upper()}:
{memoria}
"""


def limpar_para_fala(texto: str) -> str:
    """Tira markdown, pensamento e símbolos que soam estranhos falados."""
    texto = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S)
    texto = re.sub(r"```.*?```", "", texto, flags=re.S)
    texto = re.sub(r"https?://\S+", "o link", texto)
    texto = re.sub(r"[*_#`>|]+", "", texto)
    texto = re.sub(r"^\s*[-•]\s*", "", texto, flags=re.M)
    texto = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", texto)  # emojis
    return re.sub(r"\s+", " ", texto).strip()


class ErroCerebro(Exception):
    pass


class CerebroOllama:
    def __init__(self, config):
        self.config = config
        self.historico: list[dict] = []
        self._usa_think = True

    # ---------------- utilidades ----------------
    @property
    def url(self) -> str:
        return str(self.config.get("cerebro.url", "http://localhost:11434")).rstrip("/")

    @property
    def modelo(self) -> str:
        return str(self.config.get("cerebro.modelo", "qwen3:8b"))

    def esta_online(self) -> bool:
        try:
            return requests.get(self.url + "/api/tags", timeout=3).ok
        except requests.RequestException:
            return False

    def modelos_instalados(self) -> list[str]:
        try:
            r = requests.get(self.url + "/api/tags", timeout=3)
            return sorted(m["name"] for m in r.json().get("models", []))
        except Exception:
            return []

    def aquecer(self) -> None:
        """Carrega o modelo na memória da placa pra primeira resposta não demorar."""
        try:
            requests.post(self.url + "/api/generate",
                          json={"model": self.modelo, "prompt": "", "keep_alive": "30m"}, timeout=120)
        except requests.RequestException:
            pass

    def esquecer_conversa(self) -> None:
        self.historico.clear()

    # ---------------- conversa ----------------
    def _chamar(self, mensagens: list[dict]) -> dict:
        corpo = {
            "model": self.modelo,
            "messages": mensagens,
            "tools": ferramentas.esquemas(self.config),
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": float(self.config.get("cerebro.temperatura", 0.6))},
        }
        if self._usa_think:
            corpo["think"] = False  # qwen3 e afins: desliga o "pensar alto" pra responder rápido
        try:
            r = requests.post(self.url + "/api/chat", json=corpo, timeout=180)
        except requests.ConnectionError:
            raise ErroCerebro("O Ollama não está rodando. Abra o app do Ollama e tente de novo.")
        except requests.Timeout:
            raise ErroCerebro("O modelo demorou demais pra responder.")
        if r.status_code == 400 and "think" in r.text.lower() and self._usa_think:
            self._usa_think = False
            return self._chamar(mensagens)
        if r.status_code == 404:
            raise ErroCerebro(f"O modelo {self.modelo} não está instalado. Rode: ollama pull {self.modelo}")
        if r.status_code == 400 and "does not support tools" in r.text:
            raise ErroCerebro(f"O modelo {self.modelo} não sabe usar ferramentas. Use um como qwen3.")
        if not r.ok:
            raise ErroCerebro(f"Erro do Ollama: {r.text[:200]}")
        return r.json().get("message", {})

    def responder(self, texto_usuario: str, ctx: Contexto,
                  confirmar: Callable[[str], bool] | None = None,
                  ao_usar_ferramenta: Callable[[str, dict], None] | None = None) -> str:
        """Manda a fala do usuário, deixa a IA usar ferramentas, e devolve a resposta final em texto."""
        self.historico.append({"role": "user", "content": texto_usuario})
        mensagens = [{"role": "system", "content": montar_prompt_sistema(self.config)}] + self.historico
        autonomia = self.config.get("seguranca.autonomia", "confirmar_arriscadas")

        for _ in range(6):  # no máximo 6 rodadas de ferramentas por pedido
            msg = self._chamar(mensagens)
            chamadas = msg.get("tool_calls") or []
            if not chamadas:
                resposta = limpar_para_fala(msg.get("content", "")) or "Feito."
                self.historico.append({"role": "assistant", "content": resposta})
                self._podar()
                return resposta

            mensagens.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": chamadas})
            for ch in chamadas:
                fn = ch.get("function", {})
                nome = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                resultado = self._executar_com_seguranca(nome, args, ctx, autonomia, confirmar)
                if ao_usar_ferramenta:
                    ao_usar_ferramenta(nome, args)
                mensagens.append({"role": "tool", "content": resultado, "tool_name": nome})

        resposta = f"Me enrolei nas etapas dessa, {self.config.nome_usuario}. Pode pedir de outro jeito?"
        self.historico.append({"role": "assistant", "content": resposta})
        return resposta

    def _executar_com_seguranca(self, nome, args, ctx, autonomia, confirmar) -> str:
        f = ferramentas.REGISTRO.get(nome)
        if f is None:
            return f"Ferramenta desconhecida: {nome}"
        precisa = (autonomia == "confirmar_tudo") or (autonomia == "confirmar_arriscadas" and f.arriscada)
        if precisa and confirmar is not None:
            try:
                pergunta = (f.pergunta or f"Posso executar {nome}?").format(**args)
            except (KeyError, IndexError):
                pergunta = f.pergunta or f"Posso executar {nome}?"
            if not confirmar(pergunta):
                return "O usuário NÃO autorizou. Não foi executado."
        return ferramentas.executar(nome, args, ctx)

    def _podar(self) -> None:
        limite = int(self.config.get("cerebro.max_historico", 16))
        if len(self.historico) > limite:
            self.historico = self.historico[-limite:]
            while self.historico and self.historico[0]["role"] != "user":
                self.historico.pop(0)


def criar_cerebro(config):
    provedor = str(config.get("cerebro.provedor", "ollama")).lower()
    if provedor == "ollama":
        return CerebroOllama(config)
    raise ValueError(f"Provedor de IA '{provedor}' ainda não implementado (use 'ollama').")
