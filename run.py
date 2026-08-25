"""Ponto de entrada do PyAgent IA (executável e execução local).

    python run.py

Códigos de saída:
    0  encerrado normalmente
    1  configuração inválida
    2  primeira execução — arquivos de configuração recém-criados
"""

import os
import sys

BANNER = r"""
  ____        _                    _     ___    _
 |  _ \ _   _| |    __ _  ___ _ __| |_  |_ _|  / \
 | |_) | | | | |   / _` |/ _ \ '__| __|  | |  / _ \
 |  __/| |_| | |__| (_| |  __/ |  | |_   | | / ___ \
 |_|    \__, |_____\__, |\___|_|   \__| |___/_/   \_\
        |___/      |___/     Revisor de PR + merge automático
"""


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    print(BANNER)

    from app.core.config import (
        caminho_ini,
        carregar_configuracao,
        garantir_arquivos_iniciais,
        obter,
        obter_int,
        validar_configuracao,
    )

    criados = garantir_arquivos_iniciais()
    if criados:
        print("Arquivos criados nesta primeira execução:")
        for caminho in criados:
            print(f"  + {caminho}")

    precisa_configurar = any(caminho == caminho_ini() for caminho in criados)
    if precisa_configurar:
        print(
            "\nPreencha o config.ini (chaves de API e credenciais do Bitbucket) "
            "e execute novamente."
        )
        return 2

    carregar_configuracao(verboso=True)

    from app.core.logger import configurar_logging, obter_logger
    configurar_logging()
    log = obter_logger("run")

    erros, avisos = validar_configuracao()
    for aviso in avisos:
        log.warning("%s", aviso)
    if erros:
        for erro in erros:
            log.error("%s", erro)
        log.error("Corrija os itens acima em %s e execute novamente.", caminho_ini())
        return 1

    host = obter("FLASK_RUN_HOST", "0.0.0.0")
    porta = obter_int("FLASK_RUN_PORT", 5000)
    threads = max(1, obter_int("SERVER_THREADS", 4))

    from app.main import VERSAO, app

    log.info("PyAgent IA %s — IA ativa: %s", VERSAO, obter("ACTIVE_AI"))
    log.info("Repositório alvo: %s/%s", obter("BITBUCKET_WORKSPACE"), obter("BITBUCKET_REPO_SLUG"))
    log.info("Escutando em http://%s:%s  (webhook: POST /webhook/bitbucket)", host, porta)

    from waitress import serve

    try:
        serve(app, host=host, port=porta, threads=threads, ident="PyAgent IA")
    except KeyboardInterrupt:
        log.info("Encerrado pelo usuário.")
    except OSError as erro:
        log.error("Não foi possível abrir a porta %s: %s", porta, erro)
        return 1

    return 0


if __name__ == "__main__":
    # Necessário para que o executável do PyInstaller não reabra a si mesmo
    # caso alguma dependência use multiprocessing.
    import multiprocessing

    multiprocessing.freeze_support()

    # Permite `python run.py` a partir de qualquer diretório.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    sys.exit(main())
