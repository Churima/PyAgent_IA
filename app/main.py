import os
from flask import Flask, jsonify
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

app = Flask(__name__)

# Rota básica apenas para testar se o servidor está online
@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "Servidor Flask rodando!", "versao": "1.0"}), 200

if __name__ == '__main__':
    # Pega a porta do .env ou usa 5000 como padrão
    port = int(os.environ.get("FLASK_RUN_PORT", 5000))

    print(f"Iniciando o microserviço na porta {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)