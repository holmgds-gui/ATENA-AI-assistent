from atena import atualizador


def test_comparar_versoes():
    assert atualizador.mais_nova("v0.7.0", "0.6.0")
    assert atualizador.mais_nova("0.10.0", "0.9.9")
    assert not atualizador.mais_nova("0.6.0", "0.6.0")
    assert not atualizador.mais_nova("v0.5.1", "0.6.0")


def test_migracao_whisper(tmp_path, monkeypatch):
    import yaml
    monkeypatch.setenv("ATENA_DADOS", str(tmp_path))
    import importlib, atena.config as c
    importlib.reload(c)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"ouvido": {"modelo_whisper": "small"}}), encoding="utf-8")
    importlib.reload(c)
    cfg = c.Config()
    assert cfg.get("ouvido.modelo_whisper") == "base"
    assert cfg.geral.get("versao_config") == 2


def test_separa_frases_prontas():
    from atena.cerebro import _separar_frases_prontas
    assert _separar_frases_prontas("Abrindo o Spotify. Já vai toc") == (["Abrindo o Spotify."], "Já vai toc")
    assert _separar_frases_prontas("Oi") == ([], "Oi")


def test_atalho_so_nome_do_app_e_abriu(monkeypatch, tmp_path):
    from atena import atalhos, sistema
    from atena.sistema import App
    monkeypatch.setattr(sistema.INDICE, "apps", [App("Spotify", "x"), App("WhatsApp", "y")])
    monkeypatch.setattr(sistema.INDICE, "carregado", True)
    abertos = []
    monkeypatch.setattr(sistema, "abrir_app", lambda n, ap=None: abertos.append(n) or (True, n.title()))

    class Cfg:
        nome_usuario, nome_ia, apelidos_apps, apelidos_sites = "Gui", "atena", {}, {}
        permitido = staticmethod(lambda p: True)
    assert atalhos.tentar("Spotify.", Cfg)
    assert atalhos.tentar("Abriu o WhatsApp.", Cfg)
    assert atalhos.tentar("Atena, abre o spotify por favor", Cfg)
    assert atalhos.tentar("qual a capital da frança", Cfg) is None
    assert abertos == ["spotify", "whatsapp", "spotify"]


def test_variante_rapida():
    from atena.cerebro import CerebroOllama as C
    assert C.variante_rapida("qwen3-vl:4b") == "qwen3-vl:4b-instruct"
    assert C.variante_rapida("qwen3-vl:8b-thinking") == "qwen3-vl:8b-instruct"
    assert C.variante_rapida("qwen3-vl:8b-instruct") is None
    assert C.variante_rapida("llama3.2:3b") is None


def test_modelo_pensador_troca_para_rapido(monkeypatch, tmp_path):
    import json as _j
    import os
    os.environ["ATENA_DADOS"] = str(tmp_path)
    import importlib, atena.config as c
    importlib.reload(c)
    from atena import cerebro
    importlib.reload(cerebro)
    cfg = c.Config()
    cfg.salvar_geral({"cerebro": {"modelo": "qwen3-vl:4b"}, "visao": {"modelo": "qwen3-vl:4b"}})
    usados = []

    class R:
        status_code, ok, text = 200, True, ""

        def __init__(self, modelo):
            self.modelo = modelo

        def close(self):
            pass

        def iter_lines(self):
            if self.modelo.endswith("instruct"):
                yield _j.dumps({"message": {"content": "Oi, Gui."}, "done": True}).encode()
            else:
                yield _j.dumps({"message": {"thinking": "hmm"}}).encode()

        def json(self):
            return {"models": [{"name": "qwen3-vl:4b"}, {"name": "qwen3-vl:4b-instruct"}]}

    def post(url, json=None, **k):
        usados.append(json["model"])
        return R(json["model"])
    monkeypatch.setattr(cerebro.requests, "post", post)
    monkeypatch.setattr(cerebro.requests, "get", lambda *a, **k: R(""))
    monkeypatch.setattr(cerebro.threading, "Thread", lambda *a, **k: type("T", (), {"start": lambda s: None})())
    cb = cerebro.CerebroOllama(cfg)
    msg = cb._chamar([{"role": "user", "content": "oi"}])
    assert msg["content"] == "Oi, Gui."
    assert usados == ["qwen3-vl:4b", "qwen3-vl:4b-instruct"]
    assert cfg.get("cerebro.modelo") == "qwen3-vl:4b-instruct" and cfg.get("visao.modelo") == "qwen3-vl:4b-instruct"
