from flask import Blueprint, request, jsonify
from app.services.reviewer import process_pull_request

webhook_bp = Blueprint('webhook', __name__)

@webhook_bp.route('/bitbucket', methods=['POST'])
def handle_bitbucket_webhook():
    payload = request.get_json()
    
    # Agora pegamos o evento real direto do cabeçalho que o Bitbucket envia
    evento = request.headers.get("X-Event-Key")
    
    print(f"\n--- Novo evento recebido do Bitbucket: {evento} ---")
    
    # O Bitbucket manda os dados de Pull Request (quando é PR) dentro desse bloco
    pr_data = payload.get("pullrequest", {})
    pr_id = pr_data.get("id")
    pr_title = pr_data.get("title")
    
    # Se for criação ou atualização de PR, chamamos o nosso Maestro!
    if evento in ["pullrequest:created", "pullrequest:updated"]:
        if pr_id:
            process_pull_request(pr_id, pr_title)
        else:
            print("[Aviso] Evento de PR recebido, mas não encontrei o ID do PR no JSON.")
            
    return jsonify({"status": "sucesso", "mensagem": "Webhook recebido"}), 200