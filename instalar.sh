#!/usr/bin/env bash
# Instalador da ATHENA para macOS e Linux (experimental — o foco agora é Windows)
set -e
cd "$(dirname "$0")"

echo "== ATHENA — instalador (macOS/Linux) =="
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
[ -z "$PY" ] && { echo "Instale o Python 3.11 ou 3.12 primeiro."; exit 1; }

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r requirements.txt

if [ ! -d modelos/vosk-pt ]; then
  mkdir -p modelos
  echo "Baixando detector da palavra 'Atena'..."
  curl -L -o modelos/vosk.zip https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip \
    && unzip -q modelos/vosk.zip -d modelos && rm modelos/vosk.zip \
    && mv modelos/vosk-model-small-pt-0.3 modelos/vosk-pt || echo "Não consegui baixar (opcional)."
fi

if ! command -v ollama >/dev/null; then
  echo "Instale o Ollama em https://ollama.com/download e rode de novo."
  exit 0
fi
read -rp "Modelo (1 = qwen3:8b, 2 = qwen3:4b, Enter = pular): " op
case "$op" in
  1) M=qwen3:8b ;; 2) M=qwen3:4b ;; *) M="" ;;
esac
if [ -n "$M" ]; then
  ollama pull "$M"
  .venv/bin/python -c "from athena.config import Config; Config().salvar_geral({'cerebro': {'modelo': '$M'}})"
fi
echo "Pronto! Rode: .venv/bin/python main.py"
