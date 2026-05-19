from abc import ABC, abstractmethod

class BaseAIAgent(ABC):
    """
    Classe base que define o contrato para qualquer agente de IA.
    Seja Claude, Llama 3 ou Gemini, todos devem seguir este modelo.
    """
    
    @abstractmethod
    def analyze_pr(self, pr_diff: str, commit_messages: list, contexto_arquivos: list = None) -> dict:
        """
        Recebe o diff do código, as mensagens de commit e opcionalmente o conteúdo
        completo dos arquivos alterados, e retorna um dicionário com a análise.
        """
        pass