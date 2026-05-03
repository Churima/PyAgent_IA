from abc import ABC, abstractmethod

class BaseAIAgent(ABC):
    """
    Classe base que define o contrato para qualquer agente de IA.
    Seja Claude, Llama 3 ou Gemini, todos devem seguir este modelo.
    """
    
    @abstractmethod
    def analyze_pr(self, pr_diff: str, commit_messages: list) -> dict:
        """
        Recebe o diff do código e as mensagens de commit, e retorna um dicionário
        com a análise (conflitos, clean code, etc).
        """
        pass