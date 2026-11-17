"""O cérebro da ATENA. Hoje: Ollama (IA local). Feito pra plugar outros depois (Gemini, Claude...)."""
from __future__ import annotations

import json
import platform
import time
import re
import threading
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
abrir apps e sites, pesquisar na internet, digitar, apertar teclas, controlar volume e música, criar timers e notas,
e também ENXERGAR A TELA e CLICAR (ver_tela, ler_tela, clicar, rolar, focar_janela).

COMO MEXER EM APPS NA TELA (trabalhando junto com o usuário):
1. Se precisar, abra o app (abrir_app) ou traga a janela pra frente (focar_janela).
2. Use ver_tela pra ver a lista numerada de elementos.
3. Use clicar com o NÚMERO do elemento (mais preciso que o texto). Pra escrever: clique no campo e use digitar_texto.
4. Depois de cada ação importante, use ver_tela de novo pra confirmar que deu certo.
5. Se o que você procura não está na lista (ícone sem texto, imagem), use ver_tela com uma 'pergunta' ou clique pelo texto
   descrevendo o ícone, que a IA de visão procura.
6. Faça uma ação por vez e não invente números de elementos.

PERSONALIDADE:
{p.get('estilo', '').strip()}

REGRAS:
{p.get('regras_extras', '').strip()}
- Chame o usuário de {usuario}.
- A data e a hora atuais vêm junto de cada pedido, entre colchetes.
- Se precisar de informação atual (notícias, preços, clima, resultados), use pesquisar_web antes de responder.
- Depois de usar uma ferramenta, confirme em poucas palavras o que fez. Não invente que fez algo que falhou.
- Nunca diga o nome das ferramentas nem fale de JSON; fale como uma pessoa.
- Se pedirem algo que você não tem ferramenta pra fazer, diga que essa permissão está desligada
  ou que ainda não sabe fazer isso, sem inventar.

HABILIDADES E ROTINAS:
- Habilidades são sequências salvas (ex: "modo estudo"). Pra criar uma a partir de uma descrição, use salvar_habilidade.
- Pra coisas em horário marcado ("todo dia às 7h...", "amanhã às 9h me lembra..."), use agendar.
- Habilidades salvas agora: {", ".join(h["nome"] for h in getattr(config, "_listar_habilidades", list)()) or "nenhuma"}.

O QUE VOCÊ SABE SOBRE O {usuario.upper()}:
{memoria}
"""


_FIM_FRASE = re.compile(r"(?<=[.!?…:;])\s+(?=\S)")


def _separar_frases_prontas(buffer: str) -> tuple[list[str], str]:
    """Separa as frases já completas do texto que ainda está chegando."""
    partes = _FIM_FRASE.split(buffer)
    if len(partes) <= 1:
        return [], buffer
    return partes[:-1], partes[-1]


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
        self.ultimas_execucoes: list[tuple[str, dict, str]] = []  # (ferramenta, args, resultado) do último pedido
        self._usa_think = True
        self._ultimo_uso = 0.0
        self.estado_gpu = {"na_gpu": None, "porcentagem_gpu": None}
        self.ultima_velocidade = 0.0

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
        """Carrega o modelo na placa E já processa o prompt fixo (personalidade + ferramentas).
        Assim o primeiro pedido de verdade só precisa ler a sua frase."""
        inicio = time.time()
        try:
            corpo = self._corpo([{"role": "system", "content": montar_prompt_sistema(self.config)},
                                 {"role": "user", "content": "oi"}], stream=False)
            corpo["options"]["num_predict"] = 1
            requests.post(self.url + "/api/chat", json=corpo, timeout=300)
            self._ultimo_uso = time.time()
            print(f"[tempo] cérebro aquecido em {time.time() - inicio:.1f}s")
            self.diagnosticar()
        except requests.RequestException:
            pass

    def aquecer_se_frio(self) -> None:
        """Chamado quando você diz 'Atena': se o modelo pode ter saído da memória, recarrega em paralelo."""
        if time.time() - getattr(self, "_ultimo_uso", 0) > 50 * 60:
            self._ultimo_uso = time.time()
            threading.Thread(target=self.aquecer, daemon=True).start()

    def diagnosticar(self) -> dict:
        """Vê se o modelo está na placa de vídeo ou no processador (o que deixa tudo lento)."""
        info = {"na_gpu": None, "porcentagem_gpu": None}
        try:
            r = requests.get(self.url + "/api/ps", timeout=3).json()
            for m in r.get("models", []):
                if m.get("name", "").split(":")[0] == self.modelo.split(":")[0]:
                    total, vram = int(m.get("size") or 0), int(m.get("size_vram") or 0)
                    if total:
                        pct = round(100 * vram / total)
                        info = {"na_gpu": pct >= 90, "porcentagem_gpu": pct}
                    break
        except Exception:
            pass
        self.estado_gpu = info
        if info["porcentagem_gpu"] is not None:
            print(f"[cérebro] modelo {self.modelo}: {info['porcentagem_gpu']}% na placa de vídeo"
                  + ("" if info["na_gpu"] else "  <-- LENTO: rodando no processador"))
        return info

    def esquecer_conversa(self) -> None:
        self.historico.clear()

    # ---------------- conversa ----------------
    def _corpo(self, mensagens: list[dict], stream: bool = True) -> dict:
        corpo = {
            "model": self.modelo,
            "messages": mensagens,
            "tools": ferramentas.esquemas(self.config),
            "stream": stream,
            "keep_alive": "60m",
            "options": {"temperature": float(self.config.get("cerebro.temperatura", 0.6)),
                        "num_ctx": int(self.config.get("cerebro.contexto", 8192)),
                        "num_predict": int(self.config.get("cerebro.max_tokens", 400))},
        }
        if self._usa_think:
            corpo["think"] = False  # qwen3 e afins: desliga o "pensar alto" pra responder rápido
        return corpo

    def _chamar(self, mensagens: list[dict], ao_frase: Callable[[str], None] | None = None) -> dict:
        """Chama o Ollama em modo streaming. Cada frase completa vai pra `ao_frase` assim que fica pronta,
        então ela começa a falar antes de terminar de pensar a resposta inteira."""
        corpo = self._corpo(mensagens, stream=True)
        inicio = time.time()
        self._ultimo_uso = inicio
        try:
            r = requests.post(self.url + "/api/chat", json=corpo, timeout=(5, 300), stream=True)
        except requests.ConnectionError:
            raise ErroCerebro("O Ollama não está rodando. Abra o app do Ollama e tente de novo.")
        except requests.Timeout:
            raise ErroCerebro("O modelo demorou demais pra responder.")
        if r.status_code == 400:
            txt = r.text
            if "think" in txt.lower() and self._usa_think:
                self._usa_think = False
                return self._chamar(mensagens, ao_frase)
            if "does not support tools" in txt:
                raise ErroCerebro(f"O modelo {self.modelo} não sabe usar ferramentas. Use um como qwen3-vl.")
            raise ErroCerebro(f"Erro do Ollama: {txt[:200]}")
        if r.status_code == 404:
            raise ErroCerebro(f"O modelo {self.modelo} não está instalado. Rode: ollama pull {self.modelo}")
        if not r.ok:
            raise ErroCerebro(f"Erro do Ollama: {r.text[:200]}")

        conteudo, chamadas, buffer, final = [], [], "", {}
        primeira = None
        try:
            for linha in r.iter_lines():
                if not linha:
                    continue
                parte = json.loads(linha)
                if parte.get("error"):
                    raise ErroCerebro(f"Erro do Ollama: {str(parte['error'])[:200]}")
                msg = parte.get("message") or {}
                if msg.get("tool_calls"):
                    chamadas.extend(msg["tool_calls"])
                pedaco = msg.get("content") or ""
                if pedaco:
                    if primeira is None:
                        primeira = time.time() - inicio
                    conteudo.append(pedaco)
                    if ao_frase and not chamadas:
                        buffer += pedaco
                        frases, buffer = _separar_frases_prontas(buffer)
                        for f in frases:
                            f = limpar_para_fala(f)
                            if f:
                                ao_frase(f)
                if parte.get("done"):
                    final = parte
                    break
        except requests.RequestException:
            raise ErroCerebro("A conexão com o Ollama caiu no meio da resposta.")
        if ao_frase and not chamadas and buffer.strip():
            f = limpar_para_fala(buffer)
            if f:
                ao_frase(f)
        self._registrar_tempo(inicio, primeira, final)
        return {"role": "assistant", "content": "".join(conteudo), "tool_calls": chamadas}

    def _registrar_tempo(self, inicio, primeira, final: dict) -> None:
        total = time.time() - inicio
        try:
            pe, pd = int(final.get("prompt_eval_count") or 0), int(final.get("prompt_eval_duration") or 0) / 1e9
            ec, ed = int(final.get("eval_count") or 0), int(final.get("eval_duration") or 0) / 1e9
            ld = int(final.get("load_duration") or 0) / 1e9
            vel = ec / ed if ed else 0
            self.ultima_velocidade = vel
            print(f"[tempo] cérebro: {total:.1f}s (1ª palavra {primeira or 0:.1f}s, carregar {ld:.1f}s, "
                  f"leu {pe} tokens em {pd:.1f}s, escreveu {ec} a {vel:.0f} tokens/s)")
            if vel and vel < 12 and not getattr(self, "_avisou_lento", False):
                self._avisou_lento = True
                self.diagnosticar()
        except Exception:
            print(f"[tempo] cérebro respondeu em {total:.1f}s")

    def responder(self, texto_usuario: str, ctx: Contexto,
                  confirmar: Callable[[str], bool] | None = None,
                  ao_usar_ferramenta: Callable[[str, dict], None] | None = None,
                  ao_frase: Callable[[str], None] | None = None) -> str:
        """Manda a fala do usuário, deixa a IA usar ferramentas, e devolve a resposta final em texto."""
        self.ultimas_execucoes = []
        self.final_transmitido = False
        self.historico.append({"role": "user", "content": texto_usuario})
        mensagens = [{"role": "system", "content": montar_prompt_sistema(self.config)}] + self.historico[:-1] + [
            {"role": "user", "content": f"[{ferramentas.descrever_data_hora()}] {texto_usuario}"}]
        autonomia = self.config.get("seguranca.autonomia", "confirmar_arriscadas")

        cancelar = ctx.extras.get("cancelar")
        for _ in range(int(self.config.get("cerebro.max_passos", 16))):  # rodadas de ferramentas por pedido
            if cancelar is not None and cancelar.is_set():
                self.historico.append({"role": "assistant", "content": "Parei, como você pediu."})
                return "Parei, como você pediu."
            msg = self._chamar(mensagens, ao_frase)
            chamadas = msg.get("tool_calls") or []
            if not chamadas:
                self.final_transmitido = bool(ao_frase and limpar_para_fala(msg.get("content", "")))
                resposta = limpar_para_fala(msg.get("content", "")) or "Feito."
                self.historico.append({"role": "assistant", "content": resposta})
                self._podar()
                return resposta

            mensagens.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": chamadas})
            if msg.get("content") and ao_usar_ferramenta and ao_frase is None:
                ao_usar_ferramenta("_fala", {"texto": limpar_para_fala(msg["content"])})
            for ch in chamadas:
                fn = ch.get("function", {})
                nome = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if ao_usar_ferramenta:
                    ao_usar_ferramenta(nome, args)
                resultado = self._executar_com_seguranca(nome, args, ctx, autonomia, confirmar)
                self.ultimas_execucoes.append((nome, dict(args), resultado))
                mensagens.append({"role": "tool", "content": resultado, "tool_name": nome})

        resposta = f"Me enrolei nas etapas dessa, {self.config.nome_usuario}. Pode pedir de outro jeito?"
        self.historico.append({"role": "assistant", "content": resposta})
        return resposta

    def _executar_com_seguranca(self, nome, args, ctx, autonomia, confirmar) -> str:
        f = ferramentas.REGISTRO.get(nome)
        if f is None:
            return f"Ferramenta desconhecida: {nome}"
        arriscada = f.arriscada or (f.risco is not None and autonomia != "livre" and f.risco(ctx, args))
        precisa = (autonomia == "confirmar_tudo") or (autonomia == "confirmar_arriscadas" and arriscada)
        if precisa and confirmar is not None:
            class _Padrao(dict):
                def __missing__(self, chave):
                    return str(args.get("alvo") or args.get("nome") or "isso")
            try:
                pergunta = (f.pergunta or f"Posso executar {nome}?").format_map(_Padrao(args))
            except (IndexError, ValueError):
                pergunta = f"Posso executar {nome}?"
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
