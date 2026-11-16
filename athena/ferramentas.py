"""Ferramentas que o cérebro (IA) pode usar. Cada uma vira uma 'função' que o modelo chama.

Pra criar uma habilidade nova: escreva a função e registre com @ferramenta(...).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
from dataclasses import dataclass, field
from typing import Callable

from . import sistema

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


@dataclass
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict
    funcao: Callable
    arriscada: bool = False
    permissao: str = ""       # categoria em config.permissoes (vazio = sempre liberada)
    # texto curto que ela fala pra pedir confirmação. Pode usar {campos}
    pergunta: str = ""

    def esquema(self) -> dict:
        obrigatorios = [k for k, v in self.parametros.items() if not v.get("opcional")]
        props = {k: {kk: vv for kk, vv in v.items() if kk != "opcional"} for k, v in self.parametros.items()}
        return {"type": "function", "function": {
            "name": self.nome, "description": self.descricao,
            "parameters": {"type": "object", "properties": props, "required": obrigatorios}}}


@dataclass
class Contexto:
    """O que as ferramentas recebem pra conversar com o resto da ATHENA."""
    config: object
    falar: Callable[[str], None] = lambda t: None
    extras: dict = field(default_factory=dict)


REGISTRO: dict[str, Ferramenta] = {}


def ferramenta(nome, descricao, parametros=None, arriscada=False, pergunta="", permissao=""):
    def deco(fn):
        REGISTRO[nome] = Ferramenta(nome, descricao, parametros or {}, fn, arriscada, permissao, pergunta)
        return fn
    return deco


def _txt(tipo="string", desc="", **extra):
    return {"type": tipo, "description": desc, **extra}


# ----------------------------------------------------------------------
@ferramenta("abrir_app", "Abre um aplicativo instalado no computador (ex: Spotify, Chrome, Discord, Word).",
            {"nome": _txt(desc="Nome do aplicativo")},
            permissao="apps")
def _abrir_app(ctx: Contexto, nome: str):
    ok, info = sistema.abrir_app(nome, ctx.config.apelidos_apps)
    return f"Aberto: {info}" if ok else f"Falhou: {info}"


@ferramenta("fechar_app", "Fecha um programa que está aberto.",
            {"nome": _txt(desc="Nome do programa, ex: chrome, spotify")},
            arriscada=True, pergunta="Fechar o {nome}? Se tiver algo sem salvar, vai se perder.",
            permissao="fechar_apps")
def _fechar_app(ctx: Contexto, nome: str):
    ok, info = sistema.fechar_app(nome)
    return f"Fechado: {info}" if ok else f"Falhou: {info}"


@ferramenta("abrir_site", "Abre um site no navegador. Aceita URL ou nome conhecido (youtube, gmail, instagram...).",
            {"url": _txt(desc="URL ou nome do site")},
            permissao="navegador")
def _abrir_site(ctx: Contexto, url: str):
    _, final = sistema.abrir_site(url, ctx.config.apelidos_sites)
    return f"Aberto no navegador: {final}"


@ferramenta("pesquisar_web",
            "Pesquisa na internet e devolve os resultados pra você ler e responder. Use para fatos atuais, "
            "notícias, preços, clima, placares ou qualquer coisa que você não saiba com certeza.",
            {"consulta": _txt(desc="O que pesquisar")},
            permissao="internet")
def _pesquisar_web(ctx: Contexto, consulta: str):
    res = sistema.pesquisar_na_web(consulta)
    if not res:
        return "Nenhum resultado encontrado."
    return json.dumps(res, ensure_ascii=False)


@ferramenta("mostrar_pesquisa", "Abre uma pesquisa no navegador pro usuário ver (Google, YouTube, imagens, maps).",
            {"consulta": _txt(desc="O que pesquisar"),
             "onde": _txt(desc="google, youtube, imagens, maps ou wikipedia", opcional=True)},
            permissao="navegador")
def _mostrar_pesquisa(ctx: Contexto, consulta: str, onde: str = "google"):
    return "Aberto: " + sistema.pesquisar_no_navegador(consulta, onde)


@ferramenta("tocar_youtube", "Toca um vídeo ou música no YouTube.",
            {"consulta": _txt(desc="Nome da música/vídeo")},
            permissao="navegador")
def _tocar_youtube(ctx: Contexto, consulta: str):
    return "Tocando: " + sistema.tocar_no_youtube(consulta)


@ferramenta("digitar_texto", "Digita um texto onde o cursor estiver (no app que está aberto na frente).",
            {"texto": _txt(desc="Texto a digitar")},
            permissao="teclado")
def _digitar(ctx: Contexto, texto: str):
    sistema.digitar(texto)
    return "Texto digitado."


@ferramenta("apertar_teclas", "Aperta uma tecla ou atalho de teclado, ex: 'enter', 'ctrl+s', 'alt+tab', 'win+d'.",
            {"teclas": _txt(desc="Tecla ou combinação com +")},
            permissao="teclado")
def _teclas(ctx: Contexto, teclas: str):
    return "Apertado: " + sistema.pressionar(teclas)


@ferramenta("volume", "Controla o volume do computador.",
            {"acao": _txt(desc="aumentar, diminuir ou mudo", enum=["aumentar", "diminuir", "mudo"]),
             "passos": _txt("integer", "Quantos passos (cada um ~2%). Padrão 5", opcional=True)},
            permissao="midia_volume")
def _volume(ctx: Contexto, acao: str, passos: int = 5):
    return sistema.volume(acao, passos)


@ferramenta("controle_midia", "Pausa/continua, pula ou volta a música ou vídeo que está tocando.",
            {"acao": _txt(desc="pausar, tocar, proxima ou anterior", enum=["pausar", "tocar", "proxima", "anterior"])},
            permissao="midia_volume")
def _midia(ctx: Contexto, acao: str):
    return "Feito: " + sistema.midia(acao)


@ferramenta("energia", "Bloqueia, suspende, reinicia ou desliga o computador.",
            {"acao": _txt(desc="bloquear, suspender, reiniciar ou desligar",
                          enum=["bloquear", "suspender", "reiniciar", "desligar"])},
            arriscada=True, pergunta="Confirma: {acao} o computador?",
            permissao="energia")
def _energia(ctx: Contexto, acao: str):
    return "Executando: " + sistema.energia(acao)


_MONITOR = None


@ferramenta("info_sistema", "Estado do computador: uso e temperatura de CPU e placa de vídeo, RAM, clocks, "
            "ventoinhas, disco e o programa mais pesado.")
def _info(ctx: Contexto):
    global _MONITOR
    try:
        from .monitor import Monitor, resumo_falado
        if _MONITOR is None:
            _MONITOR = Monitor()
            import time
            time.sleep(0.5)  # a 1ª leitura de CPU precisa de um intervalo
        return json.dumps(resumo_falado(_MONITOR.ler()), ensure_ascii=False)
    except Exception:
        return json.dumps(sistema.info_sistema(), ensure_ascii=False)


@ferramenta("data_hora", "Diz a data e hora atuais.")
def _data_hora(ctx: Contexto):
    return descrever_data_hora()


@ferramenta("criar_nota", "Salva uma anotação num arquivo de notas (Documentos/ATHENA/notas.txt).",
            {"texto": _txt(desc="O que anotar")},
            permissao="notas_timers")
def _nota(ctx: Contexto, texto: str):
    arq = os.path.join(sistema.pasta_documentos(), "notas.txt")
    with open(arq, "a", encoding="utf-8") as f:
        f.write(f"[{dt.datetime.now():%d/%m/%Y %H:%M}] {texto}\n")
    return f"Anotado em {arq}"


@ferramenta("timer", "Cria um timer/lembrete que avisa em voz depois de X minutos.",
            {"minutos": _txt("number", "Daqui a quantos minutos"),
             "mensagem": _txt(desc="O que avisar", opcional=True)},
            permissao="notas_timers")
def _timer(ctx: Contexto, minutos: float, mensagem: str = ""):
    segundos = max(1, float(minutos) * 60)
    aviso = mensagem or "o seu timer acabou"
    t = threading.Timer(segundos, lambda: ctx.falar(f"{ctx.config.nome_usuario}, {aviso}."))
    t.daemon = True
    t.start()
    return f"Timer de {minutos:g} minuto(s) criado."


@ferramenta("lembrar", "Guarda um fato importante sobre o usuário pra lembrar em conversas futuras "
            "(só quando ele pedir pra lembrar, ou disser uma preferência clara).",
            {"fato": _txt(desc="O fato, curto. Ex: 'Prefere música lo-fi pra estudar'")},
            permissao="memoria")
def _lembrar(ctx: Contexto, fato: str):
    ctx.config.lembrar(fato)
    return "Guardado na memória."


@ferramenta("esquecer", "Apaga da memória fatos que contenham um trecho.",
            {"trecho": _txt(desc="Palavra ou trecho do fato a esquecer")},
            permissao="memoria")
def _esquecer(ctx: Contexto, trecho: str):
    n = ctx.config.esquecer(trecho)
    return f"{n} fato(s) apagado(s)."


# ----------------------------------------------------------------------
def descrever_data_hora(agora: dt.datetime | None = None) -> str:
    agora = agora or dt.datetime.now()
    return (f"{DIAS[agora.weekday()]}, {agora.day} de {MESES[agora.month - 1]} de {agora.year}, "
            f"{agora.hour:02d}:{agora.minute:02d}")


def disponiveis(config) -> list[Ferramenta]:
    """Só as ferramentas que a pessoa liberou nas permissões."""
    return [f for f in REGISTRO.values() if not f.permissao or config.permitido(f.permissao)]


def esquemas(config) -> list[dict]:
    return [f.esquema() for f in disponiveis(config)]


def executar(nome: str, args: dict, ctx: Contexto) -> str:
    f = REGISTRO.get(nome)
    if not f:
        return f"Ferramenta desconhecida: {nome}"
    if f.permissao and not ctx.config.permitido(f.permissao):
        return "Bloqueado: o usuário não deu permissão para isso nas configurações."
    try:
        return str(f.funcao(ctx, **(args or {})))
    except TypeError as e:
        return f"Argumentos inválidos para {nome}: {e}"
    except Exception as e:
        return f"Erro em {nome}: {e}"
