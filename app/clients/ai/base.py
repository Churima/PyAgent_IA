import os
from abc import ABC, abstractmethod

class BaseAIAgent(ABC):
    """
    Classe base que define o contrato para qualquer agente de IA.
    Seja Claude, Llama 3 ou Gemini, todos devem seguir este modelo.
    """
    
    @staticmethod
    def _carregar_exemplos() -> str:
        caminho = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', 'ai_context', 'exemplos_treinamento.md')
        )
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return ""

    @abstractmethod
    def analyze_pr(self, pr_diff: str, commit_messages: list, contexto_arquivos: list = None) -> dict:
        """
        Recebe o diff do código, as mensagens de commit e opcionalmente o conteúdo
        completo dos arquivos alterados, e retorna um dicionário com a análise.
        """
        pass