import os
import json
import requests
from app.clients.ai.base import BaseAIAgent

class GeminiAgent(BaseAIAgent):
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={self.api_key}"
        
    def analyze_pr(self, pr_diff: str, commit_messages: list, contexto_arquivos: list = None) -> dict:
        print("[GeminiAgent] Iniciando Smart Review com contexto de arquivos completos...")
        
        arquivos_str = ""
        if contexto_arquivos:
            for item in contexto_arquivos:
                arquivos_str += f"\n--- ARQUIVO: {item['arquivo']} ---\n"
                arquivos_str += f"VERSÃO DESTINO (MAIN):\n{item['versao_destino']}\n"
                arquivos_str += f"VERSÃO ORIGEM (DEVELOPER):\n{item['versao_origem']}\n"

        prompt = f"""
        Você é um Engenheiro de Software Sênior e Especialista em Git e Clean Code.
        
        TAREFA:
        1. Analise o DIFF e as versões dos arquivos (Destino/Main e Origem/Branch).
        2. Detecte divergências lógicas. Se a branch de Origem altera a mesma lógica que a branch de Destino de forma incompatível, isso é um CONFLITO.
        3. SE HOUVER CONFLITO: Você deve atuar como a ferramenta 'git merge'. Una a lógica da VERSÃO DESTINO com as inovações da VERSÃO ORIGEM de forma coesa. Retorne o código final perfeitamente mesclado em 'resolucao_conflito'. IMPORTANTE: O código final não deve conter marcações markdown (```python).
        4. SE NÃO HOUVER CONFLITO: Deixe 'resolucao_conflito' vazio e sugira melhorias de Clean Code preenchendo a lista 'sugestoes_clean_code' com base no DIFF.

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
        
        body = {"contents": [{"parts": [{"text": prompt}]}]}

        try:
            response = requests.post(self.url, json=body, headers={'Content-Type': 'application/json'})
            
            if response.status_code != 200:
                print(f"\n[ALERTA GEMINI] O Google recusou a requisição!")
                print(f"Status Code: {response.status_code}")
                print(f"Detalhes: {response.text}\n")
                return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": []}

            data = response.json()
            
            # --- É AQUI QUE VAMOS PEGAR O ERRO ---
            if 'candidates' not in data:
                print(f"\n[ALERTA GEMINI] Resposta estranha do Google:")
                print(f"JSON Retornado: {data}\n")
                return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": []}

            texto_resposta = data['candidates'][0]['content']['parts'][0]['text']
            
            texto_limpo = texto_resposta.replace("```json", "").replace("```", "").strip()
            return json.loads(texto_limpo)
            
        except Exception as e:
            print(f"[Erro Interno GeminiAgent] Falha no parse: {e}")
            return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": []}