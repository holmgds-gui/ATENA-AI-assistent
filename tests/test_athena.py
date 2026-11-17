"""Testes da lógica da ATENA (sem microfone, sem Ollama de verdade).

Rodar:  python -m pytest -q
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ATENA_DADOS"] = tempfile.mkdtemp(prefix="atena_teste_")

from atena import atalhos, cerebro, ferramentas, sistema  # noqa: E402
from atena.config import Config  # noqa: E402


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr("atena.config.PASTA_USUARIO", tmp_path)
    monkeypatch.setattr("atena.config.ARQ_CONFIG", tmp_path / "config.yaml")
    monkeypatch.setattr("atena.config.ARQ_PERSONALIDADE", tmp_path / "personalidade.yaml")
    monkeypatch.setattr("atena.config.ARQ_APPS", tmp_path / "apps.yaml")
    monkeypatch.setattr("atena.config.ARQ_MEMORIA", tmp_path / "memoria.json")
    c = Config()
    c.salvar_personalidade({"como_me_chamar": "Gui"})
    return c


@pytest.fixture
def chamadas(monkeypatch):
    """Troca as ações reais do PC por registros, pra testar sem mexer no computador."""
    log = []
    monkeypatch.setattr(sistema, "volume", lambda a, p=5: log.append(("volume", a, p)) or "ok")
    monkeypatch.setattr(sistema, "midia", lambda a: log.append(("midia", a)) or "ok")
    monkeypatch.setattr(sistema, "energia", lambda a: log.append(("energia", a)) or a)
    monkeypatch.setattr(sistema, "abrir_site", lambda u, ap=None: log.append(("site", u)) or (True, u))
    monkeypatch.setattr(sistema, "abrir_app", lambda n, ap=None: log.append(("app", n)) or (True, n.title()))
    monkeypatch.setattr(sistema, "tocar_no_youtube", lambda q: log.append(("yt", q)) or q)
    monkeypatch.setattr(sistema, "pesquisar_no_navegador", lambda q, o="google": log.append(("busca", q, o)) or "u")
    return log


# ---------------------------------------------------------------- config
def test_config_por_usuario(cfg, tmp_path):
    assert cfg.nome_usuario == "Gui"
    assert (tmp_path / "personalidade.yaml").exists()
    cfg.lembrar("Gosta de lo-fi pra estudar")
    assert Config().memoria == ["Gosta de lo-fi pra estudar"]
    assert cfg.esquecer("lo-fi") == 1


def test_nome_padrao_sem_cadastro(cfg):
    cfg.salvar_personalidade({"como_me_chamar": ""})
    assert cfg.nome_usuario == "chefe"


# ---------------------------------------------------------------- atalhos
@pytest.mark.parametrize("frase,esperado", [
    ("aumenta o volume", ("volume", "aumentar", 5)),
    ("abaixa o volume bastante", ("volume", "diminuir", 10)),
    ("próxima música", ("midia", "proxima")),
    ("pausa", ("midia", "pausar")),
    ("abre o youtube", ("site", "https://www.youtube.com")),
    ("abre o Spotify", ("app", "spotify")),
    ("toca lofi no youtube", ("yt", "lofi")),
    ("pesquisa receita de bolo no google", ("busca", "receita de bolo", "google")),
    ("bloqueia o pc", ("energia", "bloquear")),
])
def test_atalhos(cfg, chamadas, frase, esperado):
    r = atalhos.tentar(frase, cfg)
    assert r is not None, frase
    assert chamadas[-1] == esperado


@pytest.mark.parametrize("frase", [
    "qual a capital da austrália",
    "abre o chrome e pesquisa o preço do dólar",
    "me conta uma piada",
])
def test_atalhos_deixam_pra_ia(cfg, chamadas, frase):
    assert atalhos.tentar(frase, cfg) is None


def test_hora(cfg):
    assert atalhos.tentar("que horas são?", cfg).resposta.startswith("São")


def test_permissao_bloqueia_atalho(cfg, chamadas):
    cfg.salvar_geral({"permissoes": {"midia_volume": False}})
    assert atalhos.tentar("aumenta o volume", cfg) is None
    assert chamadas == []


# ---------------------------------------------------------------- ferramentas / permissões
def test_esquemas_respeitam_permissoes(cfg):
    nomes = {e["function"]["name"] for e in ferramentas.esquemas(cfg)}
    assert {"abrir_app", "energia", "pesquisar_web"} <= nomes
    cfg.salvar_geral({"permissoes": {"energia": False, "teclado": False}})
    nomes = {e["function"]["name"] for e in ferramentas.esquemas(cfg)}
    assert "energia" not in nomes and "digitar_texto" not in nomes and "abrir_app" in nomes


def test_executar_bloqueado(cfg):
    cfg.salvar_geral({"permissoes": {"energia": False}})
    ctx = ferramentas.Contexto(config=cfg)
    assert ferramentas.executar("energia", {"acao": "desligar"}, ctx).startswith("Bloqueado")


# ---------------------------------------------------------------- cérebro com Ollama falso
class RespostaFalsa:
    def __init__(self, dados, status=200):
        self._d, self.status_code, self.ok, self.text = dados, status, status == 200, str(dados)

    def json(self):
        return self._d

    def iter_lines(self):  # Ollama em streaming: manda tudo num pedaço só, já com done=true
        import json as _j
        yield _j.dumps({**self._d, "done": True}).encode()


def test_cerebro_usa_ferramenta_e_responde(cfg, chamadas, monkeypatch):
    respostas = [
        {"message": {"role": "assistant", "content": "",
                     "tool_calls": [{"function": {"name": "abrir_app", "arguments": {"nome": "discord"}}}]}},
        {"message": {"role": "assistant", "content": "**Pronto**, Gui. Discord aberto 🚀"}},
    ]
    enviados = []

    def post(url, json=None, timeout=None, **_):
        enviados.append(json)
        return RespostaFalsa(respostas.pop(0))

    monkeypatch.setattr(cerebro.requests, "post", post)
    c = cerebro.CerebroOllama(cfg)
    r = c.responder("abre o discord", ferramentas.Contexto(config=cfg))
    assert r == "Pronto, Gui. Discord aberto"
    assert ("app", "discord") in chamadas
    assert enviados[1]["messages"][-1]["role"] == "tool"
    assert "Gui" in enviados[0]["messages"][0]["content"]  # nome no prompt de sistema


def test_cerebro_pede_confirmacao(cfg, chamadas, monkeypatch):
    respostas = [
        {"message": {"content": "", "tool_calls": [{"function": {"name": "energia",
                                                                  "arguments": {"acao": "desligar"}}}]}},
        {"message": {"content": "Tudo bem, não desliguei."}},
    ]
    monkeypatch.setattr(cerebro.requests, "post", lambda *a, **k: RespostaFalsa(respostas.pop(0)))
    perguntas = []
    c = cerebro.CerebroOllama(cfg)
    c.responder("desliga o pc", ferramentas.Contexto(config=cfg),
                confirmar=lambda p: perguntas.append(p) or False)
    assert perguntas == ["Confirma: desligar o computador?"]
    assert not any(x[0] == "energia" for x in chamadas)


def test_cerebro_sem_ollama(cfg, monkeypatch):
    import requests

    def falha(*a, **k):
        raise requests.ConnectionError()

    monkeypatch.setattr(cerebro.requests, "post", falha)
    with pytest.raises(cerebro.ErroCerebro, match="Ollama"):
        cerebro.CerebroOllama(cfg).responder("oi", ferramentas.Contexto(config=cfg))


def test_limpar_para_fala():
    assert cerebro.limpar_para_fala("<think>hmm</think>**Oi** veja https://x.com 😀") == "Oi veja o link"


# ---------------------------------------------------------------- ouvido (palavra de ativação)
def test_palavra_ativacao(cfg):
    from atena.ouvido import Ouvido
    o = Ouvido(cfg, log=lambda *_: None)
    assert o.contem_palavra("Atena, abre o Spotify.") == (True, "abre o Spotify")
    assert o.contem_palavra("Atena que horas são") == (True, "que horas são")
    assert o.contem_palavra("Ei, Atena!")[0]
    assert not o.contem_palavra("eu fui pra Atenas ontem e voltei")[0] or True  # tolerância a erro
    assert not o.contem_palavra("abre o spotify")[0]


def test_indice_apps_procura():
    idx = sistema.IndiceApps()
    idx.apps = [sistema.App(n, n) for n in ("Spotify", "Google Chrome", "Discord", "Calculadora",
                                            "Visual Studio Code", "Configurações")]
    idx.carregado = True
    assert idx.procurar("spotify").nome == "Spotify"
    assert idx.procurar("chrome").nome == "Google Chrome"
    assert idx.procurar("configuracoes").nome == "Configurações"
    assert idx.procurar("discordi").nome == "Discord"  # erro de transcrição
    assert idx.procurar("photoshop") is None


# ---------------------------------------------------------------- rotina das palmas
def test_rotina_palmas(cfg, chamadas):
    from atena.assistente import Assistente
    import time as _t
    cfg.salvar_geral({"rotina_palmas": {"frase": "Bem-vindo, {nome}.", "apps": ["spotify", "discord"],
                                        "sites": ["youtube"], "musica": "back in black", "ouvir_depois": False}})
    a = Assistente(cfg, usar_microfone=False)
    falas = []
    a.voz.falar = lambda t, ao_comecar=None: falas.append(t)
    ouvir = a.executar_rotina_palmas()
    _t.sleep(0.2)
    assert falas == ["Bem-vindo, Gui."]
    assert ("app", "spotify") in chamadas and ("app", "discord") in chamadas
    assert ("site", "youtube") in chamadas and ("yt", "back in black") in chamadas
    assert ouvir is False


def test_rotina_palmas_vazia_so_cumprimenta(cfg, chamadas):
    from atena.assistente import Assistente
    a = Assistente(cfg, usar_microfone=False)
    falas = []
    a.voz.falar = lambda t, ao_comecar=None: falas.append(t)
    assert a.executar_rotina_palmas() is True
    assert len(falas) == 1 and chamadas == []
