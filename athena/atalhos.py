"""Comandos rápidos que NÃO precisam de IA: respondem na hora, grátis e offline.

Se nenhum atalho reconhecer a frase (ou o atalho falhar), a frase vai pro cérebro.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

from . import ferramentas, sistema
from .sistema import normalizar


@dataclass
class ResultadoAtalho:
    resposta: str
    acao: str = ""


_ARTIGOS = r"(?:o |a |os |as |um |uma |no |na |meu |minha )?"


def _limpa(alvo: str) -> str:
    alvo = re.sub(r"^(o|a|os|as|um|uma|meu|minha|pra mim|por favor)\s+", "", alvo.strip())
    alvo = re.sub(r"\s+(pra mim|por favor|ai|aí|agora)$", "", alvo)
    return alvo.strip(" .,!?")


def _ok(usuario: str) -> str:
    return random.choice(["Feito.", "Pronto.", f"Pronto, {usuario}.", "Às ordens.", "Feito, com a eficiência de sempre."])


def tentar(frase: str, config) -> ResultadoAtalho | None:
    usuario = config.nome_usuario
    t = normalizar(frase)
    if not t:
        return None
    # pedidos compostos ("abre o chrome e pesquisa X") ficam pra IA
    if re.search(r"\b(e|depois|entao) (abre|abra|fecha|toca|pesquisa|digita|escreve|manda|coloca|aperta)\b", t):
        return None

    # ---- hora / data
    if re.search(r"\b(que horas sao|que hora e|me diz as horas|horas agora)\b", t):
        from datetime import datetime
        h = datetime.now()
        return ResultadoAtalho(f"São {h.hour} e {h.minute:02d}, {usuario}." if h.minute
                               else f"São {h.hour} horas em ponto, {usuario}.")
    if re.search(r"\b(que dia e hoje|qual a data|que data e hoje|dia de hoje)\b", t):
        return ResultadoAtalho(f"Hoje é {ferramentas.descrever_data_hora().rsplit(',', 1)[0]}.")

    pode = config.permitido

    # ---- volume
    m = pode("midia_volume") and re.search(r"\b(aumenta|aumentar|sobe|subir|abaixa|abaixar|diminui|diminuir|baixa)\b.*\bvolume\b", t) \
        or (pode("midia_volume") and re.search(r"\bvolume\b.*\b(mais alto|mais baixo|pra cima|pra baixo)\b", t))
    if m:
        sobe = any(p in t for p in ("aumenta", "sobe", "subir", "mais alto", "pra cima"))
        passos = 10 if "bastante" in t or "muito" in t else 5
        sistema.volume("aumentar" if sobe else "diminuir", passos)
        return ResultadoAtalho(_ok(usuario), "volume")
    if pode("midia_volume") and re.search(r"\b(muta|mutar|silencia|silenciar|tira o som|desmuta)\b", t) and "microfone" not in t:
        sistema.volume("mudo")
        return ResultadoAtalho(_ok(usuario), "volume")

    # ---- mídia
    if pode("midia_volume") and re.fullmatch(r"(pausa|pausar|pause|continua|continuar|play|despausa)( (a )?(musica|video))?", t):
        sistema.midia("pausar")
        return ResultadoAtalho(_ok(usuario), "midia")
    if pode("midia_volume") and re.fullmatch(r"(proxima|pula|pular|passa)( (a )?(musica|faixa))?", t):
        sistema.midia("proxima")
        return ResultadoAtalho(_ok(usuario), "midia")
    if pode("midia_volume") and re.fullmatch(r"(volta|voltar)( (a )?(musica|faixa))?( anterior)?|musica anterior", t):
        sistema.midia("anterior")
        return ResultadoAtalho(_ok(usuario), "midia")

    # ---- bloquear (não é perigoso, não precisa confirmar)
    if pode("energia") and re.search(r"\bbloque(ia|ar|ie) (o )?(pc|computador|tela)\b", t):
        sistema.energia("bloquear")
        return ResultadoAtalho(f"Bloqueando. Até já, {usuario}.", "energia")

    # ---- tocar no youtube
    m = re.match(r"^(toca|toque|tocar|bota|coloca|poe) (.+?)( no youtube)?$", t)
    if m and pode("navegador") and not re.search(r"\b(spotify)\b", t):
        consulta = _limpa(m.group(2))
        if consulta and consulta not in ("musica", "uma musica", "algo"):
            titulo = sistema.tocar_no_youtube(consulta)
            return ResultadoAtalho(f"Tocando {consulta}.", f"youtube:{titulo}")

    # ---- pesquisar no navegador (google/youtube)
    m = re.match(r"^(pesquisa|pesquise|pesquisar|procura|procure|busca|busque|joga) (.+?) no (google|youtube|maps|mapa)$", t)
    if m and pode("navegador"):
        onde = "maps" if m.group(3) in ("maps", "mapa") else m.group(3)
        sistema.pesquisar_no_navegador(_limpa(m.group(2)), onde)
        return ResultadoAtalho(f"Pesquisando no {m.group(3)}.", "pesquisa")

    # ---- abrir app ou site
    m = re.match(r"^(abre|abra|abrir|abri|inicia|iniciar|executa|executar|liga|entra no|entra na|vai no|vai na) (.+)$", t)
    if m:
        alvo = _limpa(m.group(2))
        if not alvo:
            return None
        # site conhecido?
        sites = {normalizar(k): v for k, v in config.apelidos_sites.items()}
        if alvo in sites and pode("navegador"):
            sistema.abrir_site(sites[alvo])
            return ResultadoAtalho(f"Abrindo {alvo}.", "site")
        if pode("navegador") and re.search(r"\.(com|br|org|net|io|ai|gov|edu)\b", alvo):
            sistema.abrir_site(alvo)
            return ResultadoAtalho(f"Abrindo o site.", "site")
        # app instalado?
        if not pode("apps"):
            return None
        ok, info = sistema.abrir_app(alvo, config.apelidos_apps)
        if ok:
            return ResultadoAtalho(f"Abrindo {info}.", "app")
        return None  # deixa a IA tentar entender

    return None
