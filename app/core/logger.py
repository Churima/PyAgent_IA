"""Logging da aplicação e registro estruturado de execuções."""

import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

from app.core.paths import caminho_dados, garantir_pasta

_configurado = False


def _pasta_logs() -> str:
    return garantir_pasta(os.getenv("LOG_PASTA", "logs") or "logs")


def configurar_logging() -> None:
    """Console + arquivo rotativo. Idempotente."""
    global _configurado
    if _configurado:
        return

    nivel = getattr(logging, os.getenv("LOG_NIVEL", "INFO").upper(), logging.INFO)
    formato = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    for handler in list(raiz.handlers):
        raiz.removeHandler(handler)

    # O console do Windows costuma abrir em CP-1252 e quebra nos emojis dos logs.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formato)
    raiz.addHandler(console)

    try:
        arquivo = RotatingFileHandler(
            os.path.join(_pasta_logs(), "pyagent.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        arquivo.setFormatter(formato)
        raiz.addHandler(arquivo)
    except OSError as erro:
        raiz.warning("Não foi possível abrir o arquivo de log: %s", erro)

    # O waitress loga cada requisição em nível INFO; só queremos os problemas.
    logging.getLogger("waitress").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _configurado = True


def obter_logger(nome: str) -> logging.Logger:
    return logging.getLogger(nome)


def registrar_execucao(dados: dict) -> None:
    """Acrescenta uma linha ao histórico estruturado de execuções (JSON)."""
    log = obter_logger(__name__)
    try:
        caminho = os.getenv("LOG_PATH") or os.path.join(_pasta_logs(), "resultados_testes.json")
        os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)

        entrada = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "agente": dados.get("agente"),
            "modelo": dados.get("modelo"),
            "pr_id": dados.get("pr_id"),
            "tempo_segundos": dados.get("tempo_segundos"),
            "possui_conflito": dados.get("possui_conflito"),
            "num_resolucoes": dados.get("num_resolucoes", 0),
            "num_sugestoes_clean_code": dados.get("num_sugestoes_clean_code", 0),
            "num_descartadas": dados.get("num_descartadas", 0),
            "resolucao_resumo": dados.get("resolucao_resumo", []),
            "arquivos_ignorados": dados.get("arquivos_ignorados", []),
            "sugestoes_resumo": dados.get("sugestoes_resumo", []),
            "erro_parse": dados.get("erro_parse", False),
            "gitworker_acionado": dados.get("gitworker_acionado", False),
            "gitworker_sucesso": dados.get("gitworker_sucesso"),
            "tokens": dados.get("tokens"),
        }

        registros = []
        if os.path.isfile(caminho):
            with open(caminho, "r", encoding="utf-8") as arquivo:
                try:
                    registros = json.load(arquivo)
                except json.JSONDecodeError:
                    registros = []

        registros.append(entrada)

        with open(caminho, "w", encoding="utf-8") as arquivo:
            json.dump(registros, arquivo, ensure_ascii=False, indent=2)

        log.info("Execução registrada em %s (%d entradas no total)", caminho, len(registros))
    except Exception as erro:  # nunca derrubar a revisão por causa do log
        log.warning("Falha ao registrar execução (não crítico): %s", erro)


def caminho_debug_payloads() -> str:
    return caminho_dados("debug_payloads")
