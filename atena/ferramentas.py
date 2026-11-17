"""Ferramentas que o cérebro (IA) pode usar. Cada uma vira uma 'função' que o modelo chama.

Pra criar uma habilidade nova: escreva a função e registre com @ferramenta(...).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
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
    risco: Callable | None = None  # risco(ctx, args) -> bool: arriscada só em certos casos
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
    """O que as ferramentas recebem pra conversar com o resto da ATENA."""
    config: object
    falar: Callable[[str], None] = lambda t: None
    extras: dict = field(default_factory=dict)


REGISTRO: dict[str, Ferramenta] = {}


def ferramenta(nome, descricao, parametros=None, arriscada=False, pergunta="", permissao="", risco=None):
    def deco(fn):
        REGISTRO[nome] = Ferramenta(nome, descricao, parametros or {}, fn, arriscada, permissao, risco, pergunta)
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


@ferramenta("criar_nota", "Salva uma anotação num arquivo de notas (Documentos/ATENA/notas.txt).",
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


# ======================================================================
#  Visão e controle da tela
# ======================================================================
def _visao(ctx):
    from . import visao
    return visao.obter(ctx.config)


@ferramenta("ver_tela",
            "Olha a tela agora. Devolve a janela em foco e uma lista numerada de botões, campos, menus e textos "
            "visíveis. Use antes de clicar. Se passar 'pergunta', a IA de visão também descreve a imagem "
            "(útil pra ícones, imagens, jogos ou quando a lista não basta).",
            {"pergunta": _txt(desc="O que você quer saber da tela (opcional)", opcional=True)},
            permissao="tela")
def _ver_tela(ctx: Contexto, pergunta: str = ""):
    v = _visao(ctx).escanear()
    saida = {"janela_em_foco": v.janela or "?", "total_elementos": len(v.elementos),
             "elementos": [e.resumo() for e in v.elementos[:90]]}
    if len(v.elementos) > 90:
        saida["obs"] = "lista cortada; use ler_tela ou role a página"
    if pergunta or not v.elementos:
        try:
            saida["visao_ia"] = _visao(ctx).descrever(pergunta)
        except Exception as e:
            saida["visao_ia"] = f"indisponível: {e}"
    return json.dumps(saida, ensure_ascii=False)


@ferramenta("ler_tela", "Lê em voz alta/retorna TODO o texto visível na tela (OCR), em ordem de leitura.",
            permissao="tela")
def _ler_tela(ctx: Contexto):
    v = _visao(ctx).escanear()
    texto = "\n".join(e.texto for e in v.elementos)
    return texto[:3500] or "Não encontrei texto na tela."


def _risco_clique(ctx, args) -> bool:
    from . import visao
    try:
        r = _visao(ctx).resolver_alvo(str(args.get("alvo", "")))
    except Exception:
        return False
    if r:
        args["_resolvido"] = r  # evita procurar duas vezes
        args["_rotulo"] = r[2]
        return visao.parece_perigoso(r[2])
    return visao.parece_perigoso(str(args.get("alvo", "")))


@ferramenta("clicar",
            "Clica num elemento da tela. 'alvo' pode ser o número que apareceu em ver_tela (ex: '12') ou o texto "
            "do botão/link (ex: 'Enviar'). Se não achar pelo texto, a IA de visão procura na imagem.",
            {"alvo": _txt(desc="Número do elemento ou texto dele"),
             "tipo": _txt(desc="esquerdo, direito ou duplo", enum=["esquerdo", "direito", "duplo"], opcional=True)},
            permissao="tela", risco=_risco_clique, pergunta="Posso clicar em {_rotulo}?")
def _clicar(ctx: Contexto, alvo: str, tipo: str = "esquerdo", _resolvido=None, _rotulo=None):
    vis = _visao(ctx)
    r = _resolvido or vis.resolver_alvo(str(alvo))
    if not r:
        return f"Não achei '{alvo}' na tela. Use ver_tela pra ver o que existe."
    x, y, rotulo = r
    vis.clicar(x, y, tipo or "esquerdo", ctx.extras.get("mira"), rotulo)
    time.sleep(0.5)
    return f"Clique ({tipo or 'esquerdo'}) em '{rotulo}' na posição {x},{y}."


@ferramenta("rolar", "Rola a página/janela pra cima ou pra baixo.",
            {"direcao": _txt(desc="cima ou baixo", enum=["cima", "baixo"]),
             "quantidade": _txt("integer", "Quanto rolar (1 a 30). Padrão 5", opcional=True)},
            permissao="tela")
def _rolar(ctx: Contexto, direcao: str, quantidade: int = 5):
    _visao(ctx).rolar(direcao, quantidade)
    return f"Rolei pra {direcao}."


@ferramenta("focar_janela", "Traz pra frente uma janela que já está aberta (ex: 'WhatsApp', 'Chrome', 'Word').",
            {"nome": _txt(desc="Parte do título da janela")}, permissao="tela")
def _focar(ctx: Contexto, nome: str):
    r = _visao(ctx).focar_janela(nome)
    return f"Janela em foco: {r}" if r else f"Não achei janela aberta com '{nome}'."


# ======================================================================
#  Habilidades (rotinas que ela aprende) e agenda
# ======================================================================
_PASSO = {"type": "object", "properties": {
    "ferramenta": {"type": "string", "description": "abrir_app, abrir_site, tocar_youtube, digitar_texto, "
                                                    "apertar_teclas, volume, controle_midia, clicar, focar_janela, timer..."},
    "args": {"type": "object", "description": "argumentos dessa ferramenta, ex: {\"nome\": \"spotify\"}"}}}


@ferramenta("salvar_habilidade",
            "Cria/atualiza uma habilidade: uma sequência de ações com um nome (ex: 'modo estudo' = abrir Notion, "
            "tocar lo-fi). Depois o usuário só fala o nome que tudo roda.",
            {"nome": _txt(desc="Nome curto, ex: 'modo estudo'"),
             "passos": {"type": "array", "items": _PASSO, "description": "Lista de ações em ordem"}},
            permissao="memoria")
def _salvar_hab(ctx: Contexto, nome: str, passos: list):
    from .habilidades import descrever_passos
    validos = [p for p in (passos or []) if isinstance(p, dict) and p.get("ferramenta") in REGISTRO]
    if not validos:
        return "Nenhum passo válido. Use nomes de ferramentas existentes."
    h = ctx.extras["habilidades"].salvar(nome, [{"ferramenta": p["ferramenta"], "args": p.get("args") or {}}
                                               for p in validos])
    return f"Habilidade '{h['nome']}' salva: {descrever_passos(h['passos'])}."


@ferramenta("listar_habilidades", "Lista as habilidades salvas e o que cada uma faz.", permissao="memoria")
def _listar_hab(ctx: Contexto):
    from .habilidades import descrever_passos
    lista = ctx.extras["habilidades"].lista
    if not lista:
        return "Nenhuma habilidade salva ainda."
    return "\n".join(f"- {h['nome']}: {descrever_passos(h['passos'])}" for h in lista)


@ferramenta("executar_habilidade", "Roda uma habilidade salva pelo nome.",
            {"nome": _txt(desc="Nome da habilidade")}, permissao="memoria")
def _executar_hab(ctx: Contexto, nome: str):
    hab = ctx.extras["habilidades"].procurar(nome)
    if not hab:
        return f"Não existe habilidade '{nome}'."
    return ctx.extras["rodar_habilidade"](hab)


@ferramenta("apagar_habilidade", "Apaga uma habilidade salva.", {"nome": _txt(desc="Nome da habilidade")},
            permissao="memoria", arriscada=True, pergunta="Apagar a habilidade {nome}?")
def _apagar_hab(ctx: Contexto, nome: str):
    return "Apagada." if ctx.extras["habilidades"].apagar(nome) else f"Não achei '{nome}'."


@ferramenta("agendar",
            "Agenda algo pra um horário. O 'pedido' é o que o usuário diria na hora (ex: 'me dá o resumo do dia', "
            "'lembra de tomar água') OU o nome de uma habilidade. 'repetir': nao, todo_dia, dias_uteis, fim_de_semana "
            "ou dias separados por vírgula (seg,qua,sex).",
            {"hora": _txt(desc="HH:MM, ex: 07:00"),
             "pedido": _txt(desc="O que fazer na hora", opcional=True),
             "habilidade": _txt(desc="Nome de habilidade salva pra rodar", opcional=True),
             "repetir": _txt(desc="nao | todo_dia | dias_uteis | fim_de_semana | seg,ter,...", opcional=True),
             "data": _txt(desc="AAAA-MM-DD, só pra uma vez num dia específico", opcional=True)},
            permissao="notas_timers")
def _agendar(ctx: Contexto, hora: str, pedido: str = "", habilidade: str = "", repetir: str = "nao", data: str = ""):
    from .agenda import descrever
    dias = "" if str(repetir).lower() in ("", "nao", "não", "false", "no") else repetir
    try:
        r = ctx.extras["agenda"].adicionar(hora, pedido=pedido, habilidade=habilidade, dias=dias, data=data)
    except ValueError as e:
        return f"Não consegui agendar: {e}"
    return f"Agendado ({r['id']}): {descrever(r)}"


@ferramenta("listar_agendamentos", "Lista as rotinas agendadas.", permissao="notas_timers")
def _listar_ag(ctx: Contexto):
    from .agenda import descrever
    lista = [r for r in ctx.extras["agenda"].lista if r.get("ativa", True)]
    return "\n".join(f"- ({r['id']}) {descrever(r)}" for r in lista) or "Nada agendado."


@ferramenta("cancelar_agendamento", "Cancela rotinas agendadas por id ou por parte do texto.",
            {"chave": _txt(desc="id (ex: a1b2c3) ou palavra do pedido")}, permissao="notas_timers")
def _cancelar_ag(ctx: Contexto, chave: str):
    n = ctx.extras["agenda"].cancelar(chave)
    return f"{n} agendamento(s) cancelado(s)." if n else "Não achei esse agendamento."


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
        cancelar = ctx.extras.get("cancelar")
        if cancelar is not None and cancelar.is_set():
            return "Cancelado pelo usuário (tecla de pânico)."
        return str(f.funcao(ctx, **(args or {})))
    except TypeError as e:
        return f"Argumentos inválidos para {nome}: {e}"
    except Exception as e:
        if type(e).__name__ == "FailSafeException":
            return "Parado: o mouse foi pro canto da tela (trava de segurança)."
        return f"Erro em {nome}: {e}"
