"""Logging da aplicação e registro estruturado de execuções."""

import atexit
import json
import logging
import os
import queue
import sys
from datetime import datetime
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

from app.core.paths import caminho_dados, garantir_pasta

_configurado = False
_ouvinte_console: QueueListener | None = None

# Profundidade da fila do console. Acima disso a linha é descartada em vez de
# fazer a thread esperar — o console é diagnóstico, o arquivo é o registro.
_TAMANHO_FILA_CONSOLE = 10000


def _pasta_logs() -> str:
    return garantir_pasta(os.getenv("LOG_PASTA", "logs") or "logs")


class _ConsoleNaoBloqueante(QueueHandler):
    """Entrega para a fila do console sem nunca bloquear a thread que loga.

    O console do Windows vem com QuickEdit ligado: um clique dentro da janela
    põe o console em modo de seleção e o `WriteFile` do handle fica preso até
    alguém desfazer a seleção. Com o `StreamHandler` ligado direto na raiz, a
    thread presa segurava o lock do handler e *todas* as outras paravam junto —
    o serviço inteiro ficou 3 dias congelado por causa disso (18/09 09:18 até
    21/09 09:01), com os webhooks do Bitbucket empilhados no socket.

    Aqui a thread só enfileira. Quem escreve no console é a thread do
    `QueueListener`; se ela travar, a fila enche e as linhas passam a ser
    descartadas. O pior caso vira "a janela parou de atualizar", nunca "o
    serviço parou".

    O `emit` do `QueueHandler` padrão não serve: ao estourar a fila ele chama
    `handleError`, que escreve em `sys.stderr` — o mesmo console travado.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.enqueue(self.prepare(record))
        except Exception:  # fila cheia, console travado ou encerrando
            pass


def configurar_logging() -> None:
    """Arquivo rotativo + console (este último por fila). Idempotente."""
    global _configurado, _ouvinte_console
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

    # O arquivo entra PRIMEIRO. Os handlers são chamados em ordem, então o que
    # vier antes do console é gravado mesmo se o console estiver indisponível.
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

    if _booleano("LOG_CONSOLE", True):
        # O console do Windows costuma abrir em CP-1252 e quebra nos emojis.
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formato)

        fila: queue.Queue = queue.Queue(maxsize=_TAMANHO_FILA_CONSOLE)
        _ouvinte_console = QueueListener(fila, console, respect_handler_level=True)
        _ouvinte_console.start()  # o QueueListener já abre a thread como daemon
        atexit.register(_encerrar_console)

        # A ponte fica sem formatter de propósito: o `prepare` do QueueHandler
        # resolve a mensagem (e anexa o traceback de `log.exception`), e o
        # prefixo de data/nível continua sendo aplicado pelo console.
        raiz.addHandler(_ConsoleNaoBloqueante(fila))

    # O waitress loga cada requisição em nível INFO; só queremos os problemas.
    logging.getLogger("waitress").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _configurado = True


def _encerrar_console() -> None:
    """Drena o que sobrou na fila, mas sem apostar que o console responde.

    `QueueListener.stop()` faz `join()` sem prazo: com o console em seleção, o
    encerramento do executável ficaria pendurado exatamente pelo motivo que
    esta fila existe para evitar. A thread é daemon, então desistir é seguro.
    """
    global _ouvinte_console
    ouvinte, _ouvinte_console = _ouvinte_console, None
    if ouvinte is None:
        return

    try:
        ouvinte.enqueue_sentinel()
        thread = getattr(ouvinte, "_thread", None)
        if thread is not None:
            thread.join(timeout=2)
    except Exception:  # console travado no encerramento não deve virar traceback
        pass


def _booleano(variavel: str, padrao: bool) -> bool:
    valor = str(os.getenv(variavel, "")).strip().lower()
    if valor in ("1", "true", "sim", "yes", "on"):
        return True
    if valor in ("0", "false", "nao", "não", "no", "off"):
        return False
    return padrao


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
