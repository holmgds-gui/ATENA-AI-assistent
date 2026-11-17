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
