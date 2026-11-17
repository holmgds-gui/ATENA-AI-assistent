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
