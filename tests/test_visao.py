"""Lógica dos 'olhos' da ATENA, sem precisar de Windows nem de tela."""
import os
import sys
import tempfile
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ATENA_DADOS", tempfile.mkdtemp(prefix="atena_teste_"))

from atena import cerebro, ferramentas, visao  # noqa: E402
from atena.visao import Elemento, achar, interpretar_ponto, mesclar, parece_perigoso  # noqa: E402

UI = [("Enviar", "ButtonControl", 900, 700, 80, 30), ("Digite uma mensagem", "EditControl", 300, 700, 500, 30),
      ("Configurações", "MenuItemControl", 10, 40, 120, 24), ("Excluir conversa", "MenuItemControl", 10, 70, 140, 24)]
OCR = [("Enviar", 905, 705, 40, 18),               # repetido (já está na UI) -> some
       ("João Silva", 320, 120, 90, 20),            # texto só do OCR -> entra
       ("Chego em 10 minutos", 340, 400, 160, 20)]


def test_mesclar_e_ordenar():
    elems = mesclar(UI, OCR, (0, 0))
    textos = [e.texto for e in elems]
    assert textos.count("Enviar") == 1
    assert "João Silva" in textos and "Chego em 10 minutos" in textos
    assert [e.id for e in elems] == list(range(1, len(elems) + 1))
    assert elems[0].texto == "Configurações"  # ordem de leitura: de cima pra baixo


def test_mesclar_com_monitor_deslocado():
    elems = mesclar([], [("Oi", 10, 10, 20, 10)], (-1920, 0))
    assert elems[0].x == -1910


@pytest.mark.parametrize("alvo,esperado", [
    ("Enviar", "Enviar"), ("enviar", "Enviar"), ("botão enviar", "Enviar"), ("configuracoes", "Configurações"),
    ("joao silva", "João Silva"), ("Configuraçoes", "Configurações"), ("photoshop", None),
])
def test_achar_por_texto(alvo, esperado):
    elems = mesclar(UI, OCR, (0, 0))
    e = achar(alvo, elems)
    assert (e.texto if e else None) == esperado


def test_achar_por_numero():
    elems = mesclar(UI, OCR, (0, 0))
    alvo = next(e for e in elems if e.texto == "Enviar")
    assert achar(str(alvo.id), elems) is alvo
    assert achar(f"#{alvo.id}", elems) is alvo
    assert achar("999", elems) is None


def test_centro():
    assert Elemento(1, "x", "ButtonControl", 100, 200, 50, 20, "ui").centro == (125, 210)


@pytest.mark.parametrize("resp,esperado", [
    ('{"x": 500, "y": 250}', (640, 180)),                  # escala 0-1000 do Qwen3-VL
    ('```json\n{"x": 0.5, "y": 0.5}\n```', (640, 360)),    # 0..1
    ('{"bbox_2d": [100, 100, 300, 300]}', (256, 144)),      # caixa 0-1000
    ('{"x": 1100, "y": 600}', (1100, 600)),                # pixels
    ('{"nao_encontrado": true}', None),
    ("não sei", None),
])
def test_interpretar_ponto(resp, esperado):
    assert interpretar_ponto(resp, 1280, 720) == esperado


@pytest.mark.parametrize("texto,perigo", [
    ("Excluir conversa", True), ("Enviar", True), ("Finalizar compra", True), ("Desinstalar", True),
    ("Configurações", False), ("Abrir", False), ("Salvar", False),
])
def test_parece_perigoso(texto, perigo):
    assert parece_perigoso(texto) is perigo


# ---------------------------------------------------------------- clique pelo cérebro, com Visao falsa
class VisaoFalsa:
    def __init__(self):
        self.cliques = []
        self.elems = mesclar(UI, OCR, (0, 0))

    def resolver_alvo(self, alvo):
        e = achar(alvo, self.elems)
        return (*e.centro, e.texto) if e else None

    def clicar(self, x, y, tipo="esquerdo", mira=None, rotulo=""):
        if mira:
            mira(x, y, rotulo)
        self.cliques.append((x, y, tipo, rotulo))


class Resp:
    def __init__(self, d):
        self._d, self.status_code, self.ok, self.text = d, 200, True, ""

    def json(self):
        return self._d


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for nome in ("config", "personalidade", "apps"):
        monkeypatch.setattr(f"atena.config.ARQ_{nome.upper()}", tmp_path / f"{nome}.yaml")
    monkeypatch.setattr("atena.config.ARQ_MEMORIA", tmp_path / "memoria.json")
    from atena.config import Config
    c = Config()
    c.salvar_personalidade({"como_me_chamar": "Gui"})
    return c


@pytest.fixture
def olhos(monkeypatch):
    v = VisaoFalsa()
    monkeypatch.setattr(visao, "obter", lambda config: v)
    monkeypatch.setattr(ferramentas.time, "sleep", lambda s: None)
    return v


def _roteiro(monkeypatch, *mensagens):
    fila = [{"message": m} for m in mensagens]
    monkeypatch.setattr(cerebro.requests, "post", lambda *a, **k: Resp(fila.pop(0)))


def _chamada(nome, **args):
    return {"content": "", "tool_calls": [{"function": {"name": nome, "arguments": args}}]}


def test_clique_seguro_nao_pergunta(cfg, olhos, monkeypatch):
    _roteiro(monkeypatch, _chamada("clicar", alvo="Configurações"), {"content": "Abri as configurações."})
    perguntas, miras = [], []
    ctx = ferramentas.Contexto(config=cfg, extras={"mira": lambda x, y, r: miras.append(r)})
    r = cerebro.CerebroOllama(cfg).responder("clica em configurações", ctx, confirmar=lambda p: perguntas.append(p))
    assert perguntas == [] and olhos.cliques[0][3] == "Configurações" and miras == ["Configurações"]
    assert r == "Abri as configurações."


def test_clique_perigoso_pergunta_com_nome_do_botao(cfg, olhos, monkeypatch):
    excluir = next(e for e in olhos.elems if e.texto == "Excluir conversa")
    _roteiro(monkeypatch, _chamada("clicar", alvo=str(excluir.id)), {"content": "Ok, não excluí."})
    perguntas = []
    cerebro.CerebroOllama(cfg).responder("apaga essa conversa", ferramentas.Contexto(config=cfg),
                                         confirmar=lambda p: perguntas.append(p) or False)
    assert perguntas == ["Posso clicar em Excluir conversa?"]
    assert olhos.cliques == []


def test_clique_perigoso_autorizado(cfg, olhos, monkeypatch):
    _roteiro(monkeypatch, _chamada("clicar", alvo="Enviar"), {"content": "Mensagem enviada."})
    cerebro.CerebroOllama(cfg).responder("manda", ferramentas.Contexto(config=cfg), confirmar=lambda p: True)
    assert olhos.cliques and olhos.cliques[0][3] == "Enviar"


def test_modo_livre_nao_pergunta(cfg, olhos, monkeypatch):
    cfg.salvar_geral({"seguranca": {"autonomia": "livre"}})
    _roteiro(monkeypatch, _chamada("clicar", alvo="Enviar"), {"content": "Enviado."})
    perguntas = []
    cerebro.CerebroOllama(cfg).responder("manda", ferramentas.Contexto(config=cfg),
                                         confirmar=lambda p: perguntas.append(p) or True)
    assert perguntas == [] and olhos.cliques


def test_tecla_de_panico_para_no_meio(cfg, olhos, monkeypatch):
    cancelar = threading.Event()
    ctx = ferramentas.Contexto(config=cfg, extras={"cancelar": cancelar})
    fila = [_chamada("clicar", alvo="Configurações"), _chamada("clicar", alvo="Enviar"), {"content": "fim"}]

    def post(*a, **k):
        m = fila.pop(0)
        if len(fila) == 1:      # depois do 1º clique, a pessoa aperta Esc
            cancelar.set()
        return Resp({"message": m})

    monkeypatch.setattr(cerebro.requests, "post", post)
    r = cerebro.CerebroOllama(cfg).responder("faz coisas", ctx, confirmar=lambda p: True)
    assert len(olhos.cliques) == 1 and r == "Parei, como você pediu."


def test_permissao_tela_desligada_esconde_ferramentas(cfg):
    cfg.salvar_geral({"permissoes": {"tela": False}})
    nomes = {e["function"]["name"] for e in ferramentas.esquemas(cfg)}
    assert not ({"ver_tela", "clicar", "rolar", "ler_tela", "focar_janela"} & nomes)
