import os
import json
import requests
from app.clients.ai.base import BaseAIAgent

class ClaudeAgent(BaseAIAgent):
    def __init__(self):
        self.api_key = os.getenv("CLAUDE_API_KEY")
        self.url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-sonnet-4-20250514"

    def analyze_pr(self, pr_diff: str, commit_messages: list, contexto_arquivos: list = None) -> dict:
        print("[ClaudeAgent] Iniciando Smart Review com contexto de arquivos completos...")

        arquivos_str = ""
        if contexto_arquivos:
            for item in contexto_arquivos:
                arquivos_str += f"\n--- ARQUIVO: {item['arquivo']} ---\n"
                arquivos_str += f"VERSÃO DESTINO (MAIN):\n{item['versao_destino']}\n"
                arquivos_str += f"VERSÃO ORIGEM (DEVELOPER):\n{item['versao_origem']}\n"

        system_prompt = (
            "Você é um Engenheiro de Software Sênior e Especialista em Clean Code. "
            "Sua tarefa é analisar Pull Requests e sugerir melhorias de código."
        )

        user_message = f"""
        TAREFA:
        1. Analise o DIFF e as versões dos arquivos para entender o contexto da alteração do desenvolvedor.
        2. Identifique problemas de nomenclatura, falta de tipagem (type hints), falta de docstrings, lógica duplicada ou más práticas.
        3. Retorne SUGESTÕES DE MELHORIA para as linhas que o desenvolvedor alterou ou adicionou.

        CONTEÚDO DOS ARQUIVOS:{arquivos_str}

        DIFF RESUMIDO (Foque suas sugestões nas linhas adicionadas '+'):
        {pr_diff}

        RESPONDA APENAS UM JSON VÁLIDO COM ESTA ESTRUTURA:
        {{
            "sugestoes_clean_code": [
                {{
                    "arquivo": "string (caminho do arquivo)",
                    "linha": inteiro (numero da linha no diff),
                    "comentario": "string (sua explicação clara e profissional)"
                }}
            ]
        }}
        """

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        body = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_message}
            ],
        }

        try:
            response = requests.post(self.url, json=body, headers=headers)
            data = response.json()
            texto_resposta = data["content"][0]["text"]

            texto_limpo = texto_resposta.replace("```json", "").replace("```", "").strip()
            return json.loads(texto_limpo)

        except Exception as e:
            print(f"[Erro Claude] {e}")
            return {"sugestoes_clean_code": []}
