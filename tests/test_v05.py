"""Habilidades, rotinas agendadas e Telegram."""
import datetime as dt
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ATENA_DADOS", tempfile.mkdtemp(prefix="atena_teste_"))

from atena import cerebro, habilidades, sistema  # noqa: E402
from atena.agenda import Agenda, descrever  # noqa: E402
from atena.habilidades import Habilidades, converter_passos, descrever_passos  # noqa: E402


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    for nome in ("config", "personalidade", "apps"):
        monkeypatch.setattr(f"atena.config.ARQ_{nome.upper()}", tmp_path / f"{nome}.yaml")
    monkeypatch.setattr("atena.config.ARQ_MEMORIA", tmp_path / "memoria.json")
    monkeypatch.setattr("atena.config.PASTA_USUARIO", tmp_path)
    monkeypatch.setattr("atena.assistente.PASTA_USUARIO", tmp_path)
    from atena.config import Config
    c = Config()
    c.salvar_personalidade({"como_me_chamar": "Gui"})
    return c


@pytest.fixture
def pc(monkeypatch):
    log = []
    monkeypatch.setattr(sistema, "abrir_app", lambda n, ap=None: log.append(("app", n)) or (True, n.title()))
    monkeypatch.setattr(sistema, "tocar_no_youtube", lambda q: log.append(("yt", q)) or q)
    monkeypatch.setattr(sistema, "volume", lambda a, p=5: log.append(("vol", a)) or "ok")
    monkeypatch.setattr(sistema, "abrir_site", lambda u, ap=None: log.append(("site", u)) or (True, u))
    monkeypatch.setattr(habilidades.time, "sleep", lambda s: None)
    return log


# ================================================================ habilidades
def test_converter_passos():
    ex = [("abrir_app", {"nome": "notion"}, "Aberto: Notion"),
          ("ver_tela", {}, "{...}"),
          ("clicar", {"alvo": "12", "_resolvido": (1, 2, "x")}, "Clique (esquerdo) em 'Nova página' na posição 3,4."),
          ("clicar", {"alvo": "7"}, "Não achei '7' na tela."),
          ("tocar_youtube", {"consulta": "lofi"}, "Tocando: lofi girl"),
          ("abrir_app", {"nome": "photoshop"}, "Falhou: não encontrei nenhum app chamado photoshop")]
    passos = converter_passos(ex)
    assert passos == [{"ferramenta": "abrir_app", "args": {"nome": "notion"}},
                      {"ferramenta": "clicar", "args": {"alvo": "Nova página"}},
                      {"ferramenta": "tocar_youtube", "args": {"consulta": "lofi"}}]
    assert descrever_passos(passos) == "abrir notion, clicar em Nova página, tocar lofi"


@pytest.mark.parametrize("frase", ["modo estudo", "Modo Estudo!", "ativa o modo estudo", "atena, ativa modo estudo",
                                   "executa modo estudo", "estudo", "liga o modo estudo"])
def test_procurar_habilidade(tmp_path, frase):
    h = Habilidades(tmp_path)
    h.salvar("modo estudo", [{"ferramenta": "abrir_app", "args": {"nome": "notion"}}])
    assert h.procurar(frase)["nome"] == "modo estudo"


@pytest.mark.parametrize("frase", ["abre o spotify", "como tá o tempo", "modo", "estudar matemática"])
def test_nao_confunde_habilidade(tmp_path, frase):
    h = Habilidades(tmp_path)
    h.salvar("modo estudo", [{"ferramenta": "abrir_app", "args": {"nome": "notion"}}])
    assert h.procurar(frase) is None


def test_habilidade_persiste_e_apaga(tmp_path):
    Habilidades(tmp_path).salvar("Modo Foco.", [{"ferramenta": "volume", "args": {"acao": "mudo"}}])
    h = Habilidades(tmp_path)
    assert h.lista[0]["nome"] == "modo foco"
    assert h.apagar("modo foco") and Habilidades(tmp_path).lista == []


def test_executar_para_no_panico():
    cancelar = threading.Event()
    feitos = []

    def executor(nome, args):
        feitos.append(nome)
        cancelar.set()
        return "ok"

    hab = {"passos": [{"ferramenta": "a", "args": {}}, {"ferramenta": "b", "args": {}}]}
    r = habilidades.executar(hab, executor, cancelar)
    assert feitos == ["a"] and r[-1] == "cancelado"


# ================================================================ agenda
def _ag(tmp_path, agora):
    a = Agenda(tmp_path)
    return a


def test_agenda_diaria(tmp_path):
    seg_6h = dt.datetime(2026, 11, 16, 6, 0)          # segunda
    a = Agenda(tmp_path)
    r = a.adicionar("7h", pedido="me dá o resumo do dia", dias="todo_dia", agora=seg_6h)
    assert descrever(r) == "todo dia às 07:00: “me dá o resumo do dia”"
    assert a.vencidas(seg_6h.replace(hour=6, minute=59)) == []
    assert a.vencidas(seg_6h.replace(hour=7, minute=1)) == [r]
    a.marcar_rodada(r, seg_6h.replace(hour=7, minute=1))
    assert a.vencidas(seg_6h.replace(hour=7, minute=2)) == []           # não repete no mesmo dia
    assert a.vencidas(seg_6h.replace(hour=7, minute=30)) == []          # passou da tolerância
    terca = seg_6h + dt.timedelta(days=1, hours=1)
    assert a.vencidas(terca) == [r]
    assert Agenda(tmp_path).lista[0]["pedido"] == "me dá o resumo do dia"  # salvou no arquivo


def test_agenda_dias_uteis(tmp_path):
    a = Agenda(tmp_path)
    r = a.adicionar("08:30", habilidade="modo estudo", dias="dias_uteis")
    sabado = dt.datetime(2026, 11, 21, 8, 30)
    assert a.vencidas(sabado) == [] and a.vencidas(sabado + dt.timedelta(days=2)) == [r]


def test_agenda_uma_vez_amanha(tmp_path):
    agora = dt.datetime(2026, 11, 16, 21, 0)
    a = Agenda(tmp_path)
    r = a.adicionar("9:00", pedido="lembra da prova", agora=agora)       # 9h já passou hoje -> amanhã
    assert r["data"] == "2026-11-17"
    alvo = dt.datetime(2026, 11, 17, 9, 0)
    assert a.vencidas(alvo) == [r]
    a.marcar_rodada(r, alvo)
    assert r["ativa"] is False and a.vencidas(alvo) == []


def test_agenda_perdida_desliga(tmp_path):
    agora = dt.datetime(2026, 11, 16, 10, 0)
    a = Agenda(tmp_path)
    r = a.adicionar("11:00", pedido="x", agora=agora)
    assert a.vencidas(agora.replace(hour=15)) == [] and r["ativa"] is False


def test_agenda_cancelar(tmp_path):
    a = Agenda(tmp_path)
    a.adicionar("7:00", pedido="resumo do dia", dias="todo_dia")
    a.adicionar("8:00", pedido="beber água", dias="todo_dia")
    assert a.cancelar("água") == 1 and len(a.lista) == 1


def test_hora_invalida(tmp_path):
    with pytest.raises(ValueError):
        Agenda(tmp_path).adicionar("25:00", pedido="x")


# ================================================================ assistente: habilidade por voz/texto
class Resp:
    def __init__(self, d):
        self._d, self.status_code, self.ok, self.text = d, 200, True, ""

    def json(self):
        return self._d


def _assistente(cfg):
    from atena.assistente import Assistente
    a = Assistente(cfg, usar_microfone=False)
    falas = []
    a.voz.falar = lambda t, ao_comecar=None: falas.append(t)
    a._origem_texto = True
    return a, falas


def test_rodar_habilidade_pelo_nome(cfg, pc):
    a, falas = _assistente(cfg)
    a.habilidades.salvar("modo estudo", [{"ferramenta": "abrir_app", "args": {"nome": "notion"}},
                                         {"ferramenta": "tocar_youtube", "args": {"consulta": "lofi"}}])
    a.processar("ativa o modo estudo")
    assert pc == [("app", "notion"), ("yt", "lofi")]
    assert falas[0] == "Ativando modo estudo." and falas[-1] in ("Modo estudo pronto.", "Tudo pronto.", "Feito.")
    assert a.habilidades.lista[0]["usos"] == 1


def test_sugere_e_salva_habilidade(cfg, pc, monkeypatch):
    a, falas = _assistente(cfg)
    chamada = lambda n, **k: {"content": "", "tool_calls": [{"function": {"name": n, "arguments": k}}]}  # noqa
    fila = [chamada("abrir_app", nome="notion"), chamada("tocar_youtube", consulta="lofi"),
            chamada("volume", acao="diminuir"), {"content": "Tudo pronto pra estudar."}]
    monkeypatch.setattr(cerebro.requests, "post", lambda *x, **k: Resp({"message": fila.pop(0)}))
    a._textos.put(("sim, salva como modo foco", None))      # a resposta da pessoa
    a.processar("prepara tudo pra eu estudar")
    assert "Quer que eu salve isso como uma habilidade?" in falas[0]
    assert a.habilidades.procurar("modo foco") is not None
    assert falas[-1].startswith("Salvei como modo foco")
    assert [p["ferramenta"] for p in a.habilidades.lista[0]["passos"]] == ["abrir_app", "tocar_youtube", "volume"]


def test_nao_sugere_para_tarefa_curta(cfg, pc, monkeypatch):
    a, falas = _assistente(cfg)
    fila = [{"content": "", "tool_calls": [{"function": {"name": "abrir_app", "arguments": {"nome": "discord"}}}]},
            {"content": "Discord aberto."}]
    monkeypatch.setattr(cerebro.requests, "post", lambda *x, **k: Resp({"message": fila.pop(0)}))
    a.processar("prepara o discord pra mim")
    assert falas == ["Discord aberto."]


def test_recusa_salvar(cfg, pc, monkeypatch):
    a, falas = _assistente(cfg)
    chamada = lambda n, **k: {"content": "", "tool_calls": [{"function": {"name": n, "arguments": k}}]}  # noqa
    fila = [chamada("abrir_app", nome="a"), chamada("abrir_app", nome="b"), chamada("abrir_app", nome="c"),
            {"content": "Feito."}]
    monkeypatch.setattr(cerebro.requests, "post", lambda *x, **k: Resp({"message": fila.pop(0)}))
    a._textos.put(("não precisa", None))
    a.processar("prepara a, b e c")
    assert a.habilidades.lista == [] and falas[-1] == "Tudo bem, não salvei."


def test_rotina_agendada_vira_pedido(cfg, pc):
    a, falas = _assistente(cfg)
    a.habilidades.salvar("modo estudo", [{"ferramenta": "volume", "args": {"acao": "mudo"}}])
    a._ao_disparar_agenda({"habilidade": "modo estudo", "pedido": ""})
    texto, canal = a._textos.get_nowait()
    assert texto == "modo estudo" and canal.nome == "agenda" and canal.confirmar("x") is False


# ================================================================ Telegram
class TelegramFalso:
    def __init__(self):
        self.enviadas = []

    def post(self, url, json=None, data=None, files=None, timeout=None):
        self.enviadas.append((url.rsplit("/", 1)[-1], json or data))
        return Resp({"ok": True})


@pytest.fixture
def tg(cfg, monkeypatch):
    from atena import telegram
    falso = TelegramFalso()
    monkeypatch.setattr(telegram.requests, "post", falso.post)
    cfg.salvar_geral({"telegram": {"token": "123:abc"}})
    recebidos = []
    canal = telegram.CanalTelegram(cfg, ao_receber=lambda t, c: recebidos.append(t))
    return canal, falso, recebidos, cfg


def test_telegram_pareamento(tg):
    canal, falso, recebidos, cfg = tg
    canal._tratar({"chat": {"id": 555}, "text": "abre o spotify"})
    assert recebidos == [] and "Acesso negado" in falso.enviadas[-1][1]["text"]
    canal._tratar({"chat": {"id": 555}, "text": canal.codigo})
    assert cfg.get("telegram.chat_autorizado") == 555
    canal._tratar({"chat": {"id": 555}, "text": "abre o spotify"})
    assert recebidos == ["abre o spotify"]
    canal._tratar({"chat": {"id": 999}, "text": "abre o spotify"})   # estranho continua bloqueado
    assert recebidos == ["abre o spotify"]


def test_telegram_confirmacao(tg):
    canal, falso, recebidos, cfg = tg
    cfg.salvar_geral({"telegram": {"chat_autorizado": 555}})
    resultado = []
    t = threading.Thread(target=lambda: resultado.append(canal.confirmar("Posso desligar o PC?", espera=5)))
    t.start()
    time.sleep(0.2)
    canal._tratar({"chat": {"id": 555}, "text": "sim"})
    t.join(3)
    assert resultado == [True] and recebidos == []        # o "sim" não virou um pedido novo
    assert "Posso desligar o PC?" in falso.enviadas[0][1]["text"]


def test_telegram_panico(tg):
    canal, falso, recebidos, cfg = tg
    cfg.salvar_geral({"telegram": {"chat_autorizado": 555}})
    parou = []
    canal.ao_panico = lambda: parou.append(True)
    canal._tratar({"chat": {"id": 555}, "text": "/parar"})
    assert parou == [True] and recebidos == []


def test_assistente_responde_no_telegram(cfg, pc):
    a, falas = _assistente(cfg)

    class Canal:
        nome = "telegram"
        msgs = []

        def enviar(self, t):
            self.msgs.append(t)

    c = Canal()
    a.canal = c
    a.processar("aumenta o volume")
    assert falas == [] and c.msgs and pc == [("vol", "aumentar")]
