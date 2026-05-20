from app.clients.ai.base import BaseAIAgent

class MockAIAgent(BaseAIAgent):
    """
    Agente falso para testes de desenvolvimento.
    Retorna sempre uma resposta estática padronizada.
    """
    
    def analyze_pr(self, pr_diff: str, commit_messages: list, contexto_arquivos: list = None) -> dict:
        print("[MockAIAgent] Simulando análise de código com Inteligência Artificial...")
        
        # Simulamos a estrutura de resposta que a IA real nos daria
        resultado = {
            "possui_conflito": False,
            "resolucao_conflito": [],
            "sugestoes_clean_code": [
                {
                    "arquivo": "src/main.py",
                    "linha": 42,
                    "comentario": "Sugestão de Clean Code: O nome desta variável está confuso. Sugiro renomear para algo mais descritivo."
                }
            ]
        }
        
        return resultado