import os
from flask import Flask, jsonify
from dotenv import load_dotenv

# Importamos o nosso recebedor de webhooks
from app.api.webhook import webhook_bp

load_dotenv()

app = Flask(__name__)

# Registramos a rota. Tudo que chegar em /webhook vai para aquele nosso arquivo
app.register_blueprint(webhook_bp, url_prefix='/webhook')

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "Servidor Flask rodando!", "versao": "1.0"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("FLASK_RUN_PORT", 5000))
    print(f"Iniciando o microserviço na porta {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)