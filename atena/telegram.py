"""Falar com a ATENA pelo celular via Telegram. Ela executa no PC e responde no chat.

Segurança: só UMA conversa autorizada. Pra conectar, a pessoa manda pro bot o código de
6 dígitos que aparece no painel da ATENA (o código muda toda vez que a ATENA abre).

Comandos:  /tela (manda print da tela) · /parar (tecla de pânico) · /pc (status do PC)
Texto e áudio funcionam como se você tivesse falado com ela.
"""
from __future__ import annotations

import io
import os
import queue
import random
import tempfile
import threading
import time

import requests

API = "https://api.telegram.org"


class CanalTelegram:
    nome = "telegram"

    def __init__(self, config, ao_receber, transcrever=None, ao_panico=None, print_tela=None, log=print):
        """ao_receber(texto, canal) manda o pedido pra ATENA; transcrever(caminho_audio) -> texto."""
        self.config = config
        self.ao_receber = ao_receber
        self.transcrever = transcrever
        self.ao_panico = ao_panico or (lambda: None)
        self.print_tela = print_tela
        self.log = log
        self.codigo = f"{random.randint(0, 999999):06d}"
        self._rodando = threading.Event()
        self._respostas: queue.Queue[str] = queue.Queue()
        self._esperando_resposta = threading.Event()
        self.conectado = False
        self.nome_bot = ""
        self.erro = ""

    # ------------------------------------------------------------------ config
    @property
    def token(self) -> str:
        return str(self.config.get("telegram.token") or "").strip()

    @property
    def chat(self) -> int | None:
        c = self.config.get("telegram.chat_autorizado")
        return int(c) if c not in (None, "", 0) else None

    def _url(self, metodo: str) -> str:
        return f"{API}/bot{self.token}/{metodo}"

    # ------------------------------------------------------------------ envio
    def enviar(self, texto: str) -> None:
        if not (self.token and self.chat and texto):
            return
        try:
            requests.post(self._url("sendMessage"), json={"chat_id": self.chat, "text": texto[:4000]}, timeout=15)
        except requests.RequestException as e:
            self.log(f"[telegram] falha ao enviar: {e}")

    def digitando(self) -> None:
        if self.token and self.chat:
            try:
                requests.post(self._url("sendChatAction"), json={"chat_id": self.chat, "action": "typing"}, timeout=5)
            except requests.RequestException:
                pass

    def enviar_foto(self, jpeg: bytes, legenda: str = "") -> None:
        if not (self.token and self.chat):
            return
        try:
            requests.post(self._url("sendPhoto"), data={"chat_id": self.chat, "caption": legenda[:1000]},
                          files={"photo": ("tela.jpg", jpeg, "image/jpeg")}, timeout=60)
        except requests.RequestException as e:
            self.log(f"[telegram] falha ao enviar foto: {e}")

    def confirmar(self, pergunta: str, espera: float = 90) -> bool:
        """Pergunta no chat e espera 'sim'/'não'."""
        while not self._respostas.empty():
            self._respostas.get_nowait()
        self._esperando_resposta.set()
        self.enviar(f"{pergunta}\n(responda sim ou não)")
        try:
            r = self._respostas.get(timeout=espera).strip().lower()
        except queue.Empty:
            self.enviar("Sem resposta, então não fiz.")
            return False
        finally:
            self._esperando_resposta.clear()
        return r.startswith(("s", "pode", "ok", "claro", "manda", "bora", "confirm", "y"))

    def perguntar(self, pergunta: str, espera: float = 90) -> str:
        while not self._respostas.empty():
            self._respostas.get_nowait()
        self._esperando_resposta.set()
        self.enviar(pergunta)
        try:
            return self._respostas.get(timeout=espera).strip()
        except queue.Empty:
            return ""
        finally:
            self._esperando_resposta.clear()

    # ------------------------------------------------------------------ recepção
    def iniciar(self) -> None:
        if self._rodando.is_set() or not self.token:
            return
        self._rodando.set()
        threading.Thread(target=self._loop, daemon=True, name="telegram").start()

    def parar(self) -> None:
        self._rodando.clear()
        self.conectado = False

    def testar(self) -> tuple[bool, str]:
        try:
            r = requests.get(self._url("getMe"), timeout=10).json()
        except Exception as e:
            return False, f"sem conexão: {e}"
        if not r.get("ok"):
            return False, "token inválido"
        return True, "@" + r["result"].get("username", "")

    def _loop(self) -> None:
        ok, info = self.testar()
        if not ok:
            self.erro = info
            self.log(f"[telegram] {info}")
            self._rodando.clear()
            return
        self.nome_bot, self.conectado, self.erro = info, True, ""
        self.log(f"[telegram] conectado como {info}")
        offset = None
        while self._rodando.is_set():
            try:
                params = {"timeout": 25, "allowed_updates": '["message"]'}
                if offset is not None:
                    params["offset"] = offset
                r = requests.get(self._url("getUpdates"), params=params, timeout=35).json()
                for upd in r.get("result", []):
                    offset = upd["update_id"] + 1
                    try:
                        self._tratar(upd.get("message") or {})
                    except Exception as e:
                        self.log(f"[telegram] erro tratando mensagem: {e}")
            except requests.RequestException:
                time.sleep(5)
            except Exception as e:
                self.log(f"[telegram] erro: {e}")
                time.sleep(5)

    def _tratar(self, msg: dict) -> None:
        chat_id = (msg.get("chat") or {}).get("id")
        texto = (msg.get("text") or "").strip()
        if chat_id is None:
            return
        # ---- pareamento
        if self.chat is None or chat_id != self.chat:
            if texto == self.codigo:
                self.config.salvar_geral({"telegram": {"chat_autorizado": chat_id}})
                nome = self.config.nome_usuario
                self.enviar(f"Conectado. A partir de agora atendo você por aqui, {nome}. "
                            "Mande texto ou áudio. Comandos: /tela /pc /parar")
                self.log(f"[telegram] conversa {chat_id} autorizada")
            else:
                try:
                    requests.post(self._url("sendMessage"), json={
                        "chat_id": chat_id, "text": "Acesso negado. Envie o código de 6 dígitos que aparece "
                                                    "no painel da ATENA (aba Celular)."}, timeout=10)
                except requests.RequestException:
                    pass
            return
        # ---- áudio
        if msg.get("voice") or msg.get("audio"):
            texto = self._transcrever_audio((msg.get("voice") or msg.get("audio"))["file_id"])
            if not texto:
                self.enviar("Não consegui entender o áudio.")
                return
            self.enviar(f"🎙 “{texto}”")
        if not texto:
            return
        # ---- resposta a uma pergunta pendente (sim/não, nome de habilidade…)
        if self._esperando_resposta.is_set():
            self._respostas.put(texto)
            return
        # ---- comandos
        cmd = texto.split()[0].lower()
        if cmd in ("/parar", "/stop", "parar", "para"):
            self.ao_panico()
            self.enviar("⛔ Parei tudo.")
            return
        if cmd == "/start":
            self.enviar("Já estamos conectados. Mande um pedido, por texto ou áudio.")
            return
        if cmd == "/tela":
            if not self.config.permitido("tela"):
                self.enviar("A permissão 'Ver a tela' está desligada no PC.")
            elif self.print_tela:
                self.digitando()
                self.enviar_foto(self.print_tela(), "Sua tela agora")
            return
        if cmd == "/pc":
            texto = "como está o PC?"
        self.digitando()
        self.ao_receber(texto, self)

    def _transcrever_audio(self, file_id: str) -> str:
        if not self.transcrever:
            return ""
        info = requests.get(self._url("getFile"), params={"file_id": file_id}, timeout=15).json()
        caminho = info.get("result", {}).get("file_path")
        if not caminho:
            return ""
        dados = requests.get(f"{API}/file/bot{self.token}/{caminho}", timeout=60).content
        arq = os.path.join(tempfile.gettempdir(), f"atena_tg_{file_id[-8:]}.ogg")
        with open(arq, "wb") as f:
            f.write(dados)
        try:
            return self.transcrever(arq)
        finally:
            try:
                os.remove(arq)
            except OSError:
                pass


def print_jpeg(largura_max: int = 1600) -> bytes:
    from PIL import Image

    from .visao import capturar_tela
    img, _ = capturar_tela()
    if img.width > largura_max:
        img = img.resize((largura_max, int(img.height * largura_max / img.width)), Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()
