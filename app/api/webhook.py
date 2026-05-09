from flask import Blueprint, request, jsonify
from app.services.reviewer import process_pull_request

webhook_bp = Blueprint('webhook', __name__)

@webhook_bp.route('/bitbucket', methods=['POST'])
def handle_bitbucket_webhook():
    payload = request.json
    
    if not payload:
        return jsonify({"erro": "Payload vazio"}), 400

    print("--- Novo evento recebido do Bitbucket ---")

    if 'pullrequest' in payload:
        pr_data = payload['pullrequest']
        pr_id = pr_data.get('id')
        pr_title = pr_data.get('title')
        
        # Pegamos os nomes das DUAS branches agora!
        source_branch = pr_data.get('source', {}).get('branch', {}).get('name')
        dest_branch = pr_data.get('destination', {}).get('branch', {}).get('name')
        
        if pr_id and source_branch and dest_branch:
            # Passamos as duas branches para o Maestro
            resultado = process_pull_request(pr_id, pr_title, source_branch, dest_branch)
            return jsonify(resultado), 200
        else:
            return jsonify({"erro": "Dados do PR incompletos no payload"}), 400
            
    return jsonify({"mensagem": "Evento ignorado, não é um pullrequest"}), 200