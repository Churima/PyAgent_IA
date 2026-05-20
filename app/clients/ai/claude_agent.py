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

        exemplos = self._carregar_exemplos()

        commits_str = "\n".join(f"- {msg}" for msg in commit_messages) if commit_messages else "- Não informado"

        arquivos_str = ""
        if contexto_arquivos:
            for item in contexto_arquivos:
                arquivos_str += f"\n--- ARQUIVO: {item['arquivo']} ---\n"
                arquivos_str += f"VERSÃO DESTINO (MAIN):\n{item['versao_destino']}\n"
                arquivos_str += f"VERSÃO ORIGEM (DEVELOPER):\n{item['versao_origem']}\n"

        system_prompt = (
            "Você é um Engenheiro de Software Sênior e Especialista em Git e Clean Code. "
            "Sua tarefa é analisar Pull Requests, detectar conflitos de merge e sugerir melhorias de código."
        )
        if exemplos:
            system_prompt += (
                "\n\nEXEMPLOS DE REFERÊNCIA (use como guia para calibrar suas respostas):\n"
                + exemplos
            )

        user_message = f"""
        TAREFA:
        1. Analise o DIFF e as versões dos arquivos (Destino/Main e Origem/Branch).
        2. Detecte divergências lógicas. Se a branch de Origem altera a mesma lógica que a branch de Destino de forma incompatível, isso é um CONFLITO.
        3. SE HOUVER CONFLITO: Você deve atuar como a ferramenta 'git merge'. Una a lógica da VERSÃO DESTINO com as inovações da VERSÃO ORIGEM de forma coesa. Retorne o código final perfeitamente mesclado em 'resolucao_conflito'. IMPORTANTE: O código final não deve conter marcações markdown (```python).
        4. SE NÃO HOUVER CONFLITO: Deixe 'resolucao_conflito' vazio e sugira melhorias de Clean Code preenchendo a lista 'sugestoes_clean_code' com base no DIFF.
        5. Considere as mensagens de commit para identificar inconsistências entre a intenção declarada e as mudanças reais no código.

        MENSAGENS DE COMMIT DA BRANCH (mais recentes primeiro):
        {commits_str}

        CONTEÚDO DOS ARQUIVOS:{arquivos_str}

        DIFF RESUMIDO:
        {pr_diff}

        RESPONDA APENAS UM JSON VÁLIDO COM ESTA ESTRUTURA:
        {{
            "possui_conflito": boolean,
            "resolucao_conflito": [
                {{
                    "arquivo": "string (caminho do arquivo)",
                    "codigo_completo": "string (código inteiro do arquivo resolvido)"
                }}
            ],
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

            if response.status_code != 200:
                print(f"\n[ALERTA CLAUDE] A Anthropic recusou a requisição!")
                print(f"Status Code: {response.status_code}")
                print(f"Detalhes: {response.text}\n")
                return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": []}

            data = response.json()

            if "content" not in data:
                print(f"\n[ALERTA CLAUDE] Resposta inesperada da Anthropic:")
                print(f"JSON Retornado: {data}\n")
                return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": []}

            texto_resposta = data["content"][0]["text"]
            texto_limpo = texto_resposta.replace("```json", "").replace("```", "").strip()
            return json.loads(texto_limpo)

        except Exception as e:
            print(f"[Erro Interno ClaudeAgent] Falha no parse: {e}")
            return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": []}
