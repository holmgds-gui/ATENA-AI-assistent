"""Atualização automática pelo GitHub Releases (grátis, sem servidor próprio)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request

from . import __version__

REPO = "holmgds-gui/ATENA-AI-assistent"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
NOME_INSTALADOR = "ATENA-Setup.exe"


def _numeros(v: str) -> tuple:
    partes = []
    for p in v.strip().lstrip("vV").split("."):
        num = "".join(c for c in p if c.isdigit())
        partes.append(int(num) if num else 0)
    while len(partes) < 3:
        partes.append(0)
    return tuple(partes[:3])


def mais_nova(remota: str, local: str = __version__) -> bool:
    return _numeros(remota) > _numeros(local)


def verificar(timeout: float = 8.0) -> dict | None:
    """Retorna {'versao', 'url', 'tamanho', 'notas'} se houver versão nova; senão None."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"ATENA/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        dados = json.loads(r.read().decode("utf-8"))
    versao = (dados.get("tag_name") or "").lstrip("vV")
    if not versao or not mais_nova(versao):
        return None
    for a in dados.get("assets") or []:
        if a.get("name") == NOME_INSTALADOR:
            return {"versao": versao, "url": a["browser_download_url"],
                    "tamanho": int(a.get("size") or 0), "notas": dados.get("body") or ""}
    return None


def baixar(info: dict, progresso=None) -> str:
    destino = os.path.join(tempfile.gettempdir(), f"ATENA-Setup-{info['versao']}.exe")
    req = urllib.request.Request(info["url"], headers={"User-Agent": f"ATENA/{__version__}"})
    with urllib.request.urlopen(req, timeout=30) as r, open(destino + ".parcial", "wb") as f:
        total = int(r.headers.get("Content-Length") or info.get("tamanho") or 0)
        feito = 0
        while True:
            bloco = r.read(1 << 20)
            if not bloco:
                break
            f.write(bloco)
            feito += len(bloco)
            if progresso and total:
                progresso(feito / total)
    os.replace(destino + ".parcial", destino)
    return destino


def instalar(caminho: str) -> None:
    """Roda o instalador em modo silencioso; ele fecha a ATENA, atualiza e abre de novo."""
    if sys.platform != "win32":
        raise RuntimeError("Atualização automática só no Windows.")
    subprocess.Popen([caminho, "/SILENT", "/SP-", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS",
                      "/NORESTART"], close_fds=True,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
