"""ATHENA — Assistente Tecnológica de Execução e Navegação Artificial.

Uso:
    python main.py                  abre a ATHENA com orbe, voz e microfone
    python main.py --sem-microfone  abre sem microfone (só por texto no painel)
    python main.py --terminal       conversa pelo terminal, sem interface (bom pra testar)
    python main.py --apresentacao   mostra de novo a configuração da primeira vez
"""
import sys


def terminal():
    from athena.assistente import Assistente
    from athena.config import Config

    cfg = Config()
    if not cfg.personalidade.get("como_me_chamar"):
        nome = input("Como a ATHENA deve te chamar? ").strip()
        if nome:
            cfg.salvar_personalidade({"como_me_chamar": nome})

    def evento(tipo, dados=None):
        if tipo == "athena":
            print(f"\n{cfg.nome_ia}: {dados}")
        elif tipo == "acao" and dados:
            print(f"   [ação] {dados}")

    a = Assistente(cfg, evento=evento, usar_microfone=False)
    a.voz.falar = lambda texto, ao_comecar=None: None  # no terminal, só texto
    a._confirmar = lambda pergunta: input(f"\n{cfg.nome_ia}: {pergunta} (s/n) ").strip().lower().startswith("s")
    print(f"{cfg.nome_ia} no terminal. Escreva 'sair' pra fechar.")
    while True:
        try:
            t = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if t.lower() in ("sair", "exit", "quit"):
            break
        a.processar(t)


if __name__ == "__main__":
    if "--terminal" in sys.argv:
        terminal()
    else:
        if "--apresentacao" in sys.argv:
            from athena.config import Config
            Config().salvar_geral({"primeira_vez": True})
        from athena.ui.app import main
        main()
