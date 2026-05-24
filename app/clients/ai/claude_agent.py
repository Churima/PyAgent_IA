import os
import json
import requests
from app.clients.ai.base import BaseAIAgent

class ClaudeAgent(BaseAIAgent):
    def __init__(self):
        self.api_key = os.getenv("CLAUDE_API_KEY")
        self.url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-sonnet-4-20250514"

    def analyze_pr(self, pr_diff: str, commit_messages: list, contexto_arquivos: list = None, modo: str = "clean_code") -> dict:
        print(f"[ClaudeAgent] Iniciando análise — modo: {modo}...")

        exemplos = self._carregar_exemplos()
        commits_str = "\n".join(f"- {msg}" for msg in commit_messages) if commit_messages else "- Não informado"

        if modo == "resolver_conflito":
            arquivos_str = ""
            if contexto_arquivos:
                for item in contexto_arquivos:
                    arquivos_str += f"\n--- ARQUIVO: {item['arquivo']} ---\n"
                    arquivos_str += f"VERSÃO DESTINO (MAIN):\n{item['versao_destino']}\n"
                    arquivos_str += f"VERSÃO ORIGEM (DEVELOPER):\n{item['versao_origem']}\n"

            system_prompt = (
                "Você é um Engenheiro de Software Sênior especialista em resolução de conflitos de merge Git. "
                "Sua tarefa é unir duas versões de um arquivo em um resultado coeso e funcional."
            )
            if exemplos:
                system_prompt += "\n\nEXEMPLOS DE REFERÊNCIA:\n" + exemplos

            user_message = f"""
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
            arquivos_str = ""
            if contexto_arquivos:
                for item in contexto_arquivos:
                    arquivos_str += f"\n--- ARQUIVO: {item['arquivo']} ---\n"
                    arquivos_str += f"VERSÃO DESTINO (MAIN):\n{item['versao_destino']}\n"
                    arquivos_str += f"VERSÃO ORIGEM (DEVELOPER):\n{item['versao_origem']}\n"

            system_prompt = (
                "Você é um Engenheiro de Software Sênior especialista em Clean Code e revisão de código. "
                "Sua tarefa é revisar Pull Requests identificando tanto problemas de qualidade quanto "
                "inconsistências semânticas entre arquivos que o Git não detecta automaticamente."
            )
            if exemplos:
                system_prompt += "\n\nEXEMPLOS DE REFERÊNCIA:\n" + exemplos

            user_message = f"""
            CONTEXTO: Este PR não possui conflitos de merge sintáticos (sem marcadores <<<<<<<).
            No entanto, conflitos semânticos — onde duas branches alteram arquivos diferentes de forma
            logicamente incompatível — não geram marcadores e passam invisíveis pelo Git.

            TAREFA:
            1. Analise o DIFF e as versões completas dos arquivos (origem e destino) para entender
               o contexto amplo de cada alteração.
            2. Identifique oportunidades de melhoria de qualidade: nomenclatura, complexidade,
               duplicação, legibilidade e boas práticas.
            3. ADICIONALMENTE, compare ativamente as versões de origem e destino de cada arquivo
               para detectar inconsistências semânticas introduzidas pelas alterações combinadas.
               Exemplos a procurar:
               - Função que muda de assinatura em um arquivo mas seus chamadores em outros arquivos
                 ainda usam a assinatura antiga (parâmetros faltando, ordem trocada, tipo diferente).
               - Constante ou configuração redefinida de forma incompatível entre módulos.
               - Fluxo de controle ou contrato de interface que se contradiz entre arquivos distintos.
               - Lógica duplicada que divergiu entre branches e agora coexiste de forma inconsistente.
            4. IMPORTANTE: não confunda inconsistência semântica com violação de estilo. Uma
               inconsistência semântica causa comportamento incorreto em tempo de execução; uma
               violação de estilo apenas prejudica a legibilidade. Reporte ambas, mas diferencie
               claramente no comentário qual tipo cada sugestão representa.
            5. Use a linha mais relevante do diff como referência de posicionamento para cada item.
            6. Se o código estiver correto e bem escrito, retorne a lista vazia.

            MENSAGENS DE COMMIT DA BRANCH (mais recentes primeiro):
            {commits_str}

            CONTEÚDO COMPLETO DOS ARQUIVOS ALTERADOS:
            {arquivos_str}

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
                return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": [], "_erro_parse": True}

            data = response.json()

            if "content" not in data:
                print(f"\n[ALERTA CLAUDE] Resposta inesperada da Anthropic:")
                print(f"JSON Retornado: {data}\n")
                return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": [], "_erro_parse": True}

            texto_resposta = data["content"][0]["text"]
            texto_limpo = texto_resposta.replace("```json", "").replace("```", "").strip()
            return json.loads(texto_limpo)

        except Exception as e:
            print(f"[Erro Interno ClaudeAgent] Falha no parse: {e}")
            return {"possui_conflito": False, "resolucao_conflito": [], "sugestoes_clean_code": [], "_erro_parse": True}
