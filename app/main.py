"""Aplicação Flask.

A subida do servidor fica em `run.py` (com waitress) — aqui só existe a app WSGI,
para que o PyInstaller e qualquer servidor externo possam importá-la.
"""

from flask import Flask, jsonify

from app.core.config import carregar_configuracao, esta_carregado, resumo_configuracao
from app.core.logger import configurar_logging

# `run.py` já faz isso antes de importar este módulo. A repetição aqui (ambas as
# chamadas são idempotentes) cobre o caso de a app ser importada direto por um
# servidor WSGI externo, quando ninguém teria carregado a configuração.
if not esta_carregado():
    carregar_configuracao(verboso=False)
configurar_logging()

from app.api.webhook import webhook_bp  # noqa: E402  (precisa da config já carregada)

VERSAO = "2.0"

app = Flask(__name__)
app.register_blueprint(webhook_bp, url_prefix="/webhook")


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({
        "status": "PyAgent IA em execução",
        "versao": VERSAO,
        "configuracao": resumo_configuracao(),
    }), 200


if __name__ == "__main__":
    # Mantém `python -m app.main` funcionando, delegando para o entrypoint oficial.
    import sys

    from run import main

    sys.exit(main())
