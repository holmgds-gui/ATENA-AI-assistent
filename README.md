# ATENA

**Assistente Tecnológica de Execução e Navegação Artificial**

Assistente de voz para o computador, no estilo do JARVIS. Você diz **"Atena"** e faz o pedido; ela responde em voz, pesquisa na internet, abre apps e sites, digita, controla música e volume, cria timers e notas. O "cérebro" é uma IA que roda no seu próprio PC (Ollama), então não tem mensalidade e as conversas ficam na sua máquina.

> Versão 0.1: Windows primeiro. macOS e Linux têm suporte básico.

---

## ⬇️ Baixar (Windows)

**[Clique aqui pra baixar o `ATENA-Setup.exe`](https://github.com/holmgds-gui/ATENA-AI-assistent/releases/latest)** (em *Assets*).

1. Abra o `ATENA-Setup.exe`. Se o Windows avisar "app desconhecido", clique em **Mais informações → Executar assim mesmo** (acontece com todo app novo sem assinatura paga).
2. Deixe marcado **Instalar o Ollama**.
3. Abra a ATENA. Na primeira vez aparece a apresentação; no fim, escolha o tamanho do modelo e clique em **BAIXAR MODELO**.

## Instalação pelo código (pra quem programa)

1. Instale o **Python 3.12** em [python.org](https://www.python.org/downloads/) e marque **"Add python.exe to PATH"**.
2. Baixe este projeto (botão verde **Code → Download ZIP**) e extraia numa pasta.
3. Dê dois cliques em **`instalar.bat`**. Ele vai:
   - instalar as bibliotecas;
   - baixar o detector da palavra "Atena" (~30 MB);
   - instalar o **Ollama** se ele ainda não estiver no PC, e baixar o modelo de IA;
   - criar um atalho na Área de Trabalho (e, se você quiser, abrir junto com o Windows).
4. Abra a ATENA pelo atalho. Na primeira vez aparece a **apresentação**, onde você escolhe seu nome, a personalidade dela, as permissões e a voz.

### Qual modelo escolher?

| Seu PC | Modelo | Download |
|---|---|---|
| Placa de vídeo com 10 GB ou mais | `qwen3-vl:8b-instruct` | ~6 GB |
| Placa com 6–8 GB | `qwen3-vl:4b-instruct` | ~3,3 GB |
| Placa fraca ou sem placa dedicada | `qwen3-vl:2b-instruct` | ~2 GB |

O Qwen3-VL pensa **e** enxerga a tela com um modelo só, então não precisa trocar de modelo na placa de vídeo.

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

- **Palmas:** bata **2 palmas** e o holograma surge. Em Configurações → Voz → Palmas dá pra montar uma **rotina**: frase de boas-vindas, apps e sites que abrem sozinhos e uma música tocando (ex: "back in black").
- **Modo invisível:** o holograma só aparece quando ela é chamada e some sozinho depois (dá pra deixar sempre na tela em Aparência).
- **Uma frase só:** dá pra falar "Atena" e o pedido de uma vez.
- **Conversa contínua:** depois de responder, ela ainda ouve por uns 6 segundos, então dá pra emendar outro pedido.
- **Sem falar:** clique duas vezes no orbe ou use **Ctrl+Alt+A**.
- **Interromper:** clique no orbe enquanto ela fala.
- **Por texto:** Configurações → aba **Conversa**.
- **Botão direito no orbe:** configurações, microfone liga/desliga, sair.

### O holograma

Globo de malha 3D + anéis de giroscópio + rede neural + partículas. Esperando: gira devagar · ouvindo: pulsa com a sua voz · pensando: pulsos correm pela rede · falando: a malha ondula e solta ondas · cinza: microfone desligado · vermelho: erro. Cor padrão azul elétrico; troque em **Aparência** (8 paletas + personalizada).

## Habilidades, rotinas e celular

- **Habilidades:** depois de uma tarefa com 3+ passos ela pergunta *"quer que eu salve isso como habilidade?"*. Responda com um nome ("sim, modo estudo") e depois é só falar **"modo estudo"**. Também dá pra criar direto: *"Atena, cria a habilidade modo jogo que abre o Discord e a Steam"*.
- **Rotinas agendadas:** *"Atena, todo dia às 7h me dá o resumo do dia"*, *"dias úteis às 19h30 ativa o modo estudo"*. Veja e apague em **Rotinas**.
- **Celular (Telegram):** em **Celular**, siga os 3 passos (criar bot no @BotFather, colar o token, mandar o código). Aí é só mandar texto ou áudio pro bot. Comandos: `/tela` (print), `/pc` (status), `/parar` (pânico). Só o seu celular pareado é atendido.

## Ela enxerga a tela e mexe junto com você

Peça coisas como *"Atena, abre o WhatsApp e manda 'chego em 10 min' pro João"* ou *"clica em configurações"*. Ela usa três "olhos":

1. **Acessibilidade do Windows:** a lista de botões, campos, menus e abas da janela ativa, com posição exata.
2. **OCR do Windows:** lê todo texto visível (sites, PDFs, jogos).
3. **IA de visão (Qwen3-VL):** olha a imagem da tela pra achar ícones sem texto e descrever o que está aparecendo.

Antes de cada clique aparece uma **mira holográfica** no ponto exato, e a legenda mostra o que ela está fazendo ("▸ clicando em Enviar").

**Segurança:**
- **Esc** enquanto ela age = para tudo na hora.
- Mouse no **canto superior esquerdo** da tela também trava os cliques.
- Antes de clicar em algo como *Excluir, Pagar, Comprar, Enviar, Desinstalar*, ela **pergunta antes** (no modo padrão de confirmação).
- Tudo isso pode ser desligado na permissão **"Ver a tela e clicar"**.

## Monitor do PC (aba SISTEMA)

Uso e temperatura de CPU e placa de vídeo, RAM, VRAM, clocks (com indicador de boost), potência, ventoinhas, discos, rede, histórico de 60 s e processos mais pesados. Também dá pra perguntar: *"Atena, como tá o PC?"*

- CPU, RAM, disco, rede e processos funcionam sempre.
- **Temperaturas, clocks, ventoinhas e GPU** precisam do [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) aberto (o instalador oferece instalar). Abra como administrador e ligue **Options → Remote Web Server → Run**.
- A ATENA **mostra** os clocks e se o boost está ativo, mas não faz overclock (isso é melhor no AMD Adrenalin).

---

## Compartilhar com outras pessoas

Cada pessoa que instala tem a **própria configuração** (nome, personalidade, permissões, memória), salva em:

- Windows: `%APPDATA%\ATENA`
- macOS: `~/Library/Application Support/ATENA`
- Linux: `~/.config/atena`

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
| `atena/assistente.py` | o maestro: liga ouvido, cérebro e voz |
| `atena/ouvido.py` | microfone, palavra "Atena" e transcrição |
| `atena/cerebro.py` | conversa com o Ollama e usa as ferramentas |
| `atena/ferramentas.py` | **as habilidades** (é aqui que se adicionam novas) |
| `atena/atalhos.py` | comandos rápidos sem IA |
| `atena/sistema.py` | o que realmente mexe no PC (Windows/mac/Linux) |
| `atena/voz.py` | a voz dela |
| `atena/palmas.py` | detector de palmas (sem IA) |
| `atena/visao.py` | olhos: acessibilidade + OCR + IA de visão |
| `atena/habilidades.py` | rotinas aprendidas |
| `atena/agenda.py` | rotinas agendadas |
| `atena/telegram.py` | canal do celular |
| `atena.spec`, `instalador/` | receita do `.exe` e do instalador |
| `.github/workflows/` | gera o `ATENA-Setup.exe` a cada versão (`git tag v0.x.y`) |
| `atena/monitor.py` | leitura de sensores do PC |
| `atena/ui/` | holograma, apresentação, painel HUD e monitor |
| `atena/ui/fontes/` | Orbitron, Rajdhani e Share Tech Mono (licença OFL) |
| `config/` | configurações padrão |

### Criar uma habilidade nova

Em `atena/ferramentas.py`:

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
- **Palmas não funcionam / disparam sozinhas:** ajuste a **Força da palma** em Configurações → Voz.
- **Ela não ouve "Atena":** em Configurações → Voz e ativação, diminua a **Exigência de volume**. Confira também se o microfone certo é o padrão do Windows.
- **Ela acorda sozinha:** aumente a **Exigência de volume**.
- **Respostas lentas:** troque pra `qwen3:4b` ou use o reconhecimento `base`.
- **Voz robótica:** a voz neural precisa de internet; sem internet ela usa a voz do Windows.

---

## Próximas fases

- [x] Visão da tela: ler, achar botões e clicar
- [x] Aprender rotinas novas (habilidades), ideia do Hermes Agent
- [x] Rotinas agendadas ("todo dia às 7h…")
- [x] Falar com ela pelo celular (Telegram)
- [ ] WhatsApp
- [ ] Cérebros de nuvem opcionais (Gemini / Claude) pra tarefas difíceis
- [ ] Integração com WhatsApp, e-mail e agenda
- [ ] App de celular pra falar com a ATENA do PC
- [ ] Instalador `.exe` de um clique
