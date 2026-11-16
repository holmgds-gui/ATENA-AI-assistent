# ATHENA

**Assistente Tecnológica de Execução e Navegação Artificial**

Assistente de voz para o computador, no estilo do JARVIS. Você diz **"Atena"** e faz o pedido; ela responde em voz, pesquisa na internet, abre apps e sites, digita, controla música e volume, cria timers e notas. O "cérebro" é uma IA que roda no seu próprio PC (Ollama), então não tem mensalidade e as conversas ficam na sua máquina.

> Versão 0.1: Windows primeiro. macOS e Linux têm suporte básico.

---

## Instalação (Windows)

1. Instale o **Python 3.12** em [python.org](https://www.python.org/downloads/) e marque **"Add python.exe to PATH"**.
2. Baixe este projeto (botão verde **Code → Download ZIP**) e extraia numa pasta.
3. Dê dois cliques em **`instalar.bat`**. Ele vai:
   - instalar as bibliotecas;
   - baixar o detector da palavra "Atena" (~30 MB);
   - instalar o **Ollama** se ele ainda não estiver no PC, e baixar o modelo de IA;
   - criar um atalho na Área de Trabalho (e, se você quiser, abrir junto com o Windows).
4. Abra a ATHENA pelo atalho. Na primeira vez aparece a **apresentação**, onde você escolhe seu nome, a personalidade dela, as permissões e a voz.

### Qual modelo escolher?

| Seu PC | Modelo | Download |
|---|---|---|
| Placa de vídeo com 8 GB ou mais | `qwen3:8b` | ~5 GB |
| Placa mais fraca ou sem placa dedicada | `qwen3:4b` | ~2,5 GB |

Dá pra trocar depois em **Configurações → Cérebro**.

**Placas AMD Radeon:** o Ollama usa a placa automaticamente. As RX 7000 usam ROCm; as outras (RX 6000, 5000...) usam Vulkan. Pra conferir se está usando a placa, rode `ollama ps` no terminal enquanto ela responde: a coluna **PROCESSOR** deve mostrar **GPU**. Se aparecer só CPU, atualize o driver da AMD (Adrenalin).

---

## Como usar

| Você fala | O que acontece |
|---|---|
| "Atena, abre o Spotify" | abre o app (sem gastar IA: é instantâneo) |
| "Atena, toca lo-fi no YouTube" | abre o vídeo |
| "Atena, quanto tá o dólar hoje?" | pesquisa na internet e responde |
| "Atena, escreve um e-mail pedindo reunião amanhã" | digita no app que está aberto |
| "Atena, me avisa em 20 minutos pra tirar o bolo" | cria um timer falado |
| "Atena, lembra que eu prefiro respostas curtas" | guarda na memória |
| "Atena, desliga o PC" | pede confirmação antes |

- **Uma frase só:** dá pra falar "Atena" e o pedido de uma vez.
- **Conversa contínua:** depois de responder, ela ainda ouve por uns 6 segundos, então dá pra emendar outro pedido.
- **Sem falar:** clique duas vezes no orbe ou use **Ctrl+Alt+A**.
- **Interromper:** clique no orbe enquanto ela fala.
- **Por texto:** Configurações → aba **Conversa**.
- **Botão direito no orbe:** configurações, microfone liga/desliga, sair.

### Cores do orbe

🔵 esperando · 🩵 ouvindo · 🟣 pensando · 🔵 com ondas falando · ⚪ microfone desligado · 🔴 erro

---

## Compartilhar com outras pessoas

Cada pessoa que instala tem a **própria configuração** (nome, personalidade, permissões, memória), salva em:

- Windows: `%APPDATA%\ATHENA`
- macOS: `~/Library/Application Support/ATHENA`
- Linux: `~/.config/athena`

A pasta do projeto só tem os padrões. Pra rever a apresentação: **Configurações → Sobre → Rever apresentação**, ou rode `python main.py --apresentacao`.

---

## Como funciona por dentro

```
 microfone ─► Vosk (escuta "Atena", leve e offline)
                 │
                 ▼
            Whisper (transcreve a frase, offline)
                 │
                 ▼
     comandos rápidos? ──sim──► executa direto (abrir app, volume, horas...)
                 │ não
                 ▼
     Ollama / qwen3 (cérebro local) ──► ferramentas (abrir, pesquisar, digitar...)
                 │                         └─ ações arriscadas pedem confirmação
                 ▼
          Edge TTS (voz neural grátis) ──► alto-falante
```

| Pasta / arquivo | O que é |
|---|---|
| `athena/assistente.py` | o maestro: liga ouvido, cérebro e voz |
| `athena/ouvido.py` | microfone, palavra "Atena" e transcrição |
| `athena/cerebro.py` | conversa com o Ollama e usa as ferramentas |
| `athena/ferramentas.py` | **as habilidades** (é aqui que se adicionam novas) |
| `athena/atalhos.py` | comandos rápidos sem IA |
| `athena/sistema.py` | o que realmente mexe no PC (Windows/mac/Linux) |
| `athena/voz.py` | a voz dela |
| `athena/ui/` | orbe, apresentação e painel de configurações |
| `config/` | configurações padrão |

### Criar uma habilidade nova

Em `athena/ferramentas.py`:

```python
@ferramenta("cotacao_dolar", "Diz a cotação atual do dólar.", permissao="internet")
def _dolar(ctx):
    ...
    return "R$ 5,10"
```

A IA passa a usar sozinha quando fizer sentido.

---

## Comandos úteis

```bat
iniciar.bat debug              :: abre mostrando as mensagens (pra achar erros)
.venv\Scripts\python main.py --terminal        :: conversa só por texto no terminal
.venv\Scripts\python main.py --sem-microfone   :: abre sem microfone
.venv\Scripts\python -m pytest -q              :: roda os testes
```

## Problemas comuns

- **"Não estou encontrando o Ollama":** abra o app do Ollama (fica perto do relógio do Windows).
- **Ela não ouve "Atena":** em Configurações → Voz e ativação, diminua a **Exigência de volume**. Confira também se o microfone certo é o padrão do Windows.
- **Ela acorda sozinha:** aumente a **Exigência de volume**.
- **Respostas lentas:** troque pra `qwen3:4b` ou use o reconhecimento `base`.
- **Voz robótica:** a voz neural precisa de internet; sem internet ela usa a voz do Windows.

---

## Próximas fases

- [ ] **Visão da tela:** clicar em botões e ler o que está aparecendo
- [ ] Cérebros de nuvem opcionais (Gemini / Claude) pra tarefas difíceis
- [ ] Integração com WhatsApp, e-mail e agenda
- [ ] App de celular pra falar com a ATHENA do PC
- [ ] Instalador `.exe` de um clique
