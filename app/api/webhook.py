import hmac
import json
import os
import threading
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.core.logger import caminho_debug_payloads, obter_logger
from app.services.reviewer import process_pull_request

log = obter_logger(__name__)

webhook_bp = Blueprint("webhook", __name__)

# PRs em processamento. O Bitbucket reenvia o evento quando a resposta demora,
# e sem esse controle o mesmo PR seria revisado (ou mesclado) duas vezes.
_em_processamento: set[int] = set()
_trava = threading.Lock()


@webhook_bp.route("/bitbucket", methods=["POST"])
def handle_bitbucket_webhook():
    if not _token_valido(request):
        log.warning("Requisição recusada: token do webhook inválido ou ausente (origem: %s)",
                    request.remote_addr)
        return jsonify({"erro": "não autorizado"}), 401

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"erro": "Payload vazio ou não é JSON"}), 400

    log.info("Novo evento recebido do Bitbucket (%s)",
             request.headers.get("X-Event-Key", "evento não identificado"))
    _salvar_payload(payload)

    if "pullrequest" not in payload:
        return jsonify({"mensagem": "Evento ignorado, não é um pullrequest"}), 200

    pr = payload["pullrequest"]
    pr_id = pr.get("id")
    pr_title = pr.get("title")
    source_branch = (pr.get("source") or {}).get("branch", {}).get("name")
    dest_branch = (pr.get("destination") or {}).get("branch", {}).get("name")

    if not (pr_id and source_branch and dest_branch):
        log.warning("Payload de PR incompleto: id=%s source=%s dest=%s",
                    pr_id, source_branch, dest_branch)
        return jsonify({"erro": "Dados do PR incompletos no payload"}), 400

    if not _booleano("WEBHOOK_ASSINCRONO", True):
        resultado = process_pull_request(pr_id, pr_title, source_branch, dest_branch)
        return jsonify(resultado), 200

    with _trava:
        if pr_id in _em_processamento:
            log.info("PR #%s já está sendo processado. Evento duplicado descartado.", pr_id)
            return jsonify({"status": "ignorado", "motivo": "ja_em_processamento"}), 200
        _em_processamento.add(pr_id)

    threading.Thread(
        target=_processar_em_segundo_plano,
        args=(pr_id, pr_title, source_branch, dest_branch),
        name=f"revisao-pr-{pr_id}",
        daemon=True,
    ).start()

    # 202: o Bitbucket encerra a entrega imediatamente e não reenvia por timeout.
    return jsonify({"status": "aceito", "pr_id": pr_id}), 202


def _processar_em_segundo_plano(pr_id, pr_title, source_branch, dest_branch):
    try:
        process_pull_request(pr_id, pr_title, source_branch, dest_branch)
    except Exception:
        log.exception("Falha não tratada ao processar o PR #%s", pr_id)
    finally:
        with _trava:
            _em_processamento.discard(pr_id)


def _token_valido(requisicao) -> bool:
    esperado = os.getenv("WEBHOOK_TOKEN", "")
    if not esperado:
        return True  # proteção desligada; o startup já avisa sobre isso
    recebido = requisicao.headers.get("X-PyAgent-Token", "")
    return hmac.compare_digest(esperado, recebido)


def _salvar_payload(payload: dict) -> None:
    if not _booleano("LOG_SALVAR_PAYLOADS", False):
        return
    try:
        pasta = caminho_debug_payloads()
        os.makedirs(pasta, exist_ok=True)
        nome = f"payload_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
        caminho = os.path.join(pasta, nome)
        with open(caminho, "w", encoding="utf-8") as arquivo:
            json.dump(payload, arquivo, indent=2, ensure_ascii=False)
        log.debug("Payload salvo em %s", caminho)
    except OSError as erro:
        log.warning("Não foi possível salvar o payload de debug: %s", erro)


def _booleano(variavel: str, padrao: bool) -> bool:
    valor = str(os.getenv(variavel, "")).strip().lower()
    if valor in ("1", "true", "sim", "yes", "on"):
        return True
    if valor in ("0", "false", "nao", "não", "no", "off"):
        return False
    return padrao
