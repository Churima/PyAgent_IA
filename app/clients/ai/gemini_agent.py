import os
import json
import requests
from app.clients.ai.base import BaseAIAgent

class GeminiAgent(BaseAIAgent):
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={self.api_key}"
        
    def analyze_pr(self, pr_diff: str, commit_messages: list, contexto_arquivos: list = None, modo: str = "clean_code") -> dict:
        print(f"[GeminiAgent] Iniciando análise — modo: {modo}...")

        exemplos = self._carregar_exemplos()
        exemplos_secao = (
            f"\n\nEXEMPLOS DE REFERÊNCIA (use como guia para calibrar suas respostas):\n{exemplos}\n---\n"
            if exemplos else ""
        )

        commits_str = "\n".join(f"- {msg}" for msg in commit_messages) if commit_messages else "- Não informado"

        if modo == "resolver_conflito":
            arquivos_str = ""
            if contexto_arquivos:
                for item in contexto_arquivos:
                    arquivos_str += f"\n--- ARQUIVO: {item['arquivo']} ---\n"
                    arquivos_str += f"VERSÃO DESTINO (MAIN):\n{item['versao_destino']}\n"
                    arquivos_str += f"VERSÃO ORIGEM (DEVELOPER):\n{item['versao_origem']}\n"

            prompt = f"""
            Você é um Engenheiro de Software Sênior especialista em resolução de conflitos de merge Git.
            {exemplos_secao}
            CONTEXTO: O Bitbucket confirmou que este PR possui conflito de merge.

            TAREFA:
            1. Analise as duas versões de cada arquivo (Destino/Main e Origem/Branch).
            2. Atue como a ferramenta 'git merge': una a lógica da VERSÃO DESTINO com as inovações da VERSÃO ORIGEM de forma coesa.
            3. Retorne o código final perfeitamente mesclado em 'resolucao_conflito'.
            4. IMPORTANTE: o código final NÃO deve conter marcações markdown (```python) nem marcadores de conflito Git (<<<, ===, >>>).
            5. Considere as mensagens de commit para entender a intenção de cada branch.

            MENSAGENS DE COMMIT DA BRANCH (mais recentes primeiro):
            {commits_str}

            CONTEÚDO DOS ARQUIVOS:
            {arquivos_str}

            DIFF RESUMIDO:
            {pr_diff}

            RESPONDA APENAS UM JSON VÁLIDO COM ESTA ESTRUTURA:
            {{
                "resolucao_conflito": [
                    {{
                        "arquivo": "string (caminho do arquivo)",
                        "codigo_completo": "string (código inteiro do arquivo resolvido)"
                    }}
                ]
            }}
            """
        else:
            prompt = f"""
            Você é um Engenheiro de Software Sênior especialista em Clean Code.
            {exemplos_secao}
            CONTEXTO: Este PR não possui conflitos de merge. Foque exclusivamente em qualidade de código.

            TAREFA:
            1. Analise o DIFF e as mensagens de commit.
            2. Identifique oportunidades de melhoria: nomenclatura, complexidade, duplicação, legibilidade, boas práticas.
            3. Para cada problema encontrado, indique o arquivo, a linha no diff e uma explicação clara e profissional.
            4. Se o código estiver bem escrito, retorne a lista vazia.

            MENSAGENS DE COMMIT DA BRANCH (mais recentes primeiro):
            {commits_str}

            DIFF:
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

        body = {"contents": [{"parts": [{"text": prompt}]}]}

        try:
            response = requests.post(self.url, json=body, headers={'Content-Type': 'application/json'})
            
            if response.status_code != 200:
                print(f"\n[ALERTA GEMINI] O Google recusou a requisição!")
                print(f"Status Code: {response.status_code}")
                print(f"Detalhes: {response.text}\n")
                return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": [], "_erro_parse": True}

            data = response.json()

            # --- É AQUI QUE VAMOS PEGAR O ERRO ---
            if 'candidates' not in data:
                print(f"\n[ALERTA GEMINI] Resposta estranha do Google:")
                print(f"JSON Retornado: {data}\n")
                return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": [], "_erro_parse": True}

            texto_resposta = data['candidates'][0]['content']['parts'][0]['text']

            texto_limpo = texto_resposta.replace("```json", "").replace("```", "").strip()
            return json.loads(texto_limpo)

        except Exception as e:
            print(f"[Erro Interno GeminiAgent] Falha no parse: {e}")
            return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": [], "_erro_parse": True}