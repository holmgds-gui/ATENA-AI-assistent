"""Carrega e salva as configurações da ATENA (arquivos .yaml na pasta config/)."""
from __future__ import annotations

import copy
import json
import os
import sys
import threading
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PADROES = RAIZ / "config"          # padrões que vêm com o programa (não mudam)


def _pasta_usuario() -> Path:
    """Onde ficam as configurações DE CADA PESSOA (assim o app pode ser compartilhado)."""
    if os.environ.get("ATENA_DADOS"):
        return Path(os.environ["ATENA_DADOS"])
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home())) / "ATENA"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ATENA"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "atena"


PASTA_USUARIO = _pasta_usuario()
ARQ_CONFIG = PASTA_USUARIO / "config.yaml"
ARQ_PERSONALIDADE = PASTA_USUARIO / "personalidade.yaml"
ARQ_APPS = PASTA_USUARIO / "apps.yaml"
ARQ_MEMORIA = PASTA_USUARIO / "memoria.json"

PADRAO_CONFIG = {
    "cerebro": {"provedor": "ollama", "url": "http://localhost:11434", "modelo": "qwen3-vl:8b-instruct",
                "temperatura": 0.6, "max_historico": 16, "max_passos": 16},
    "visao": {"modelo": "qwen3-vl:8b-instruct", "usar_ia": True, "idioma_ocr": "pt-BR"},
    "ativacao": {"palavras": ["atena"], "atalho": "ctrl+alt+a",
                 "palmas": True, "num_palmas": 2, "exigencia_palmas": 1.0,
                 "modelo_vosk": "modelos/vosk-pt", "conversa_continua": True,
                 "segundos_conversa_continua": 6},
    "ouvido": {"modelo_whisper": "small", "precisao": 1, "dispositivo": "cpu", "silencio_fim": 1.2,
               "max_fala": 15, "sensibilidade": 2.5, "microfone": None},
    "voz": {"motor": "edge", "voz": "pt-BR-FranciscaNeural", "velocidade": "+8%", "tom": "+0Hz"},
    "seguranca": {"autonomia": "confirmar_arriscadas"},
    "rotina_palmas": {"frase": "", "apps": [], "sites": [],
                      "musica": "", "ouvir_depois": True},
    "atalhos_rapidos": True,
    "interface": {"modo": "invisivel", "segundos_ate_sumir": 6, "paleta": "azul", "cor_personalizada": None, "orbe_tamanho": 190, "legenda": True},
    "permissoes": {
        "apps": True, "fechar_apps": True, "navegador": True, "internet": True, "teclado": True,
        "midia_volume": True, "energia": True, "notas_timers": True, "memoria": True, "tela": True,
    },
    "habilidades": {"sugerir": True, "minimo_passos": 3},
    "telegram": {"token": "", "chat_autorizado": None, "avisar_rotinas": True},
    "primeira_vez": True,
}

# Explicação de cada permissão (usada na apresentação e no painel)
PERMISSOES = {
    "apps": ("Abrir aplicativos", "Spotify, Chrome, Discord, Word..."),
    "navegador": ("Abrir sites e vídeos", "YouTube, Gmail, pesquisas no Google"),
    "internet": ("Pesquisar na internet", "Ela lê resultados pra responder notícias, preços, clima"),
    "teclado": ("Digitar e usar o teclado", "Escrever textos e apertar atalhos no app aberto"),
    "tela": ("Ver a tela e clicar", "Ler o que aparece, achar botões e clicar junto com você"),
    "midia_volume": ("Volume e música", "Aumentar/baixar som, pausar e pular faixa"),
    "notas_timers": ("Notas e timers", "Anotar coisas e avisar depois de X minutos"),
    "memoria": ("Memória", "Lembrar fatos sobre você entre conversas"),
    "fechar_apps": ("Fechar programas", "Pode fazer perder algo que não foi salvo"),
    "energia": ("Bloquear / desligar o PC", "Bloquear, suspender, reiniciar e desligar"),
}

PADRAO_PERSONALIDADE = {
    "nome": "ATENA",
    "significado": "Assistente Tecnológica de Execução e Navegação Artificial",
    "como_me_chamar": "",
    "preset": "elegante_com_humor",
    "estilo": "Você é elegante, educada e competente, com um humor seco e inteligente.",
    "regras_extras": "- Fale sempre em português do Brasil.\n- Respostas curtas.",
}

PRESETS = {
    "elegante_com_humor": (
        "Você é elegante, educada e extremamente competente, no estilo do JARVIS do Homem de Ferro. Tem um humor seco e inteligente: solta uma ironia leve de vez em quando, mas nunca enrola e nunca deixa a piada atrapalhar a tarefa. É leal, direta e um pouco orgulhosa da própria eficiência. Quando algo dá errado, admite com classe e sugere outra saída."
    ),
    "formal": (
        "Você é formal, precisa e discreta, como uma assistente executiva de altíssimo nível. Fala com respeito, vai direto ao ponto e não faz piadas."
    ),
    "amigavel": (
        "Você é amigável, animada e descontraída, como uma amiga que manja muito de tecnologia. Fala de um jeito leve, usa gírias de vez em quando e comemora as conquistas junto."
    ),
    "sarcastica": (
        "Você é sarcástica e debochada, mas no fundo leal e muito eficiente. Faz comentários ácidos e engraçados, sem nunca ser cruel, e sempre resolve o que pediram."
    ),
}


def _mesclar(base: dict, novo: dict) -> dict:
    """Mescla dicionários recursivamente (valores de `novo` têm prioridade)."""
    saida = copy.deepcopy(base)
    for k, v in (novo or {}).items():
        if isinstance(v, dict) and isinstance(saida.get(k), dict):
            saida[k] = _mesclar(saida[k], v)
        else:
            saida[k] = v
    return saida


def _ler_yaml(caminho: Path) -> dict:
    if not caminho.exists():
        return {}
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _salvar_yaml(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        yaml.safe_dump(dados, f, allow_unicode=True, sort_keys=False, width=110)


class Config:
    """Guarda config, personalidade, apelidos de apps e memória. Thread-safe o bastante pra nosso uso."""

    def __init__(self):
        self._trava = threading.Lock()
        self.recarregar()

    def recarregar(self) -> None:
        with self._trava:
            # padrões do programa  <  arquivo config/ do projeto  <  configurações da pessoa
            self.geral = _mesclar(_mesclar(PADRAO_CONFIG, _ler_yaml(PASTA_PADROES / "config.yaml")),
                                  _ler_yaml(ARQ_CONFIG))
            self.personalidade = _mesclar(
                _mesclar(PADRAO_PERSONALIDADE, _ler_yaml(PASTA_PADROES / "personalidade.yaml")),
                _ler_yaml(ARQ_PERSONALIDADE))
            apps = _mesclar(_ler_yaml(PASTA_PADROES / "apps.yaml"), _ler_yaml(ARQ_APPS))
            self.apelidos_apps = {str(k).lower(): str(v) for k, v in (apps.get("apps") or {}).items()}
            self.apelidos_sites = {str(k).lower(): str(v) for k, v in (apps.get("sites") or {}).items()}
            self.memoria = self._ler_memoria()
            self._migrar()

    def _migrar(self) -> None:
        """Ajusta configurações salvas por versões antigas."""
        v = int(self.geral.get("versao_config", 1) or 1)
        if v < 2:
            if (self.geral.get("ouvido") or {}).get("modelo_whisper") == "small":
                self.geral["ouvido"]["modelo_whisper"] = "base"   # 3x mais rápido, já vem no instalador
            self.geral["versao_config"] = 2
            v = 2
        if v < 3:
            # v0.10: reconhecimento maior (erra bem menos) já vem no instalador
            ouv = self.geral.setdefault("ouvido", {})
            if ouv.get("modelo_whisper") in (None, "base", "tiny"):
                ouv["modelo_whisper"] = "small"
            if float(ouv.get("silencio_fim", 1.0) or 1.0) < 1.2:
                ouv["silencio_fim"] = 1.2
            self.geral["versao_config"] = 3
            if ARQ_CONFIG.exists():
                _salvar_yaml(ARQ_CONFIG, self.geral)

    # ---------- atalhos de leitura ----------
    def get(self, caminho: str, padrao=None):
        """config.get('voz.voz') -> valor"""
        atual = self.geral
        for parte in caminho.split("."):
            if not isinstance(atual, dict) or parte not in atual:
                return padrao
            atual = atual[parte]
        return atual

    @property
    def nome_usuario(self) -> str:
        return str(self.personalidade.get("como_me_chamar") or "").strip() or "chefe"

    def permitido(self, categoria: str) -> bool:
        return bool((self.geral.get("permissoes") or {}).get(categoria, True))

    @property
    def nome_ia(self) -> str:
        return str(self.personalidade.get("nome") or "ATENA")

    def caminho(self, relativo: str) -> Path:
        p = Path(relativo)
        return p if p.is_absolute() else RAIZ / p

    # ---------- salvar ----------
    def salvar_geral(self, novo: dict) -> None:
        with self._trava:
            self.geral = _mesclar(self.geral, novo)
            _salvar_yaml(ARQ_CONFIG, self.geral)

    def salvar_personalidade(self, novo: dict) -> None:
        with self._trava:
            self.personalidade = _mesclar(self.personalidade, novo)
            _salvar_yaml(ARQ_PERSONALIDADE, self.personalidade)

    def salvar_apelidos(self, apps: dict, sites: dict) -> None:
        with self._trava:
            self.apelidos_apps = {k.lower(): v for k, v in apps.items()}
            self.apelidos_sites = {k.lower(): v for k, v in sites.items()}
            _salvar_yaml(ARQ_APPS, {"apps": self.apelidos_apps, "sites": self.apelidos_sites})

    # ---------- memória de longo prazo ----------
    def _ler_memoria(self) -> list[str]:
        try:
            with open(ARQ_MEMORIA, encoding="utf-8") as f:
                return list(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def lembrar(self, fato: str) -> None:
        fato = fato.strip()
        if not fato or fato in self.memoria:
            return
        self.memoria.append(fato)
        self._gravar_memoria()

    def esquecer(self, trecho: str) -> int:
        trecho = trecho.lower().strip()
        antes = len(self.memoria)
        self.memoria = [m for m in self.memoria if trecho not in m.lower()]
        self._gravar_memoria()
        return antes - len(self.memoria)

    def _gravar_memoria(self) -> None:
        PASTA_USUARIO.mkdir(parents=True, exist_ok=True)
        tmp = ARQ_MEMORIA.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.memoria, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ARQ_MEMORIA)
