from app.clients.ai.base import BaseAIAgent
from app.core.logger import obter_logger

log = obter_logger(__name__)


class MockAIAgent(BaseAIAgent):
    """Agente falso para desenvolvimento e teste de encanamento.

    Responde no contrato completo (severidade, categoria, resumo) usando o
    primeiro arquivo e a primeira âncora reais do PR, para que a validação de
    caminho e de linha do reviewer também seja exercitada.
    """

    def __init__(self):
        self._modelo = "mock"

    def analyze_pr(
        self,
        pr_diff: str,
        commit_messages: list,
        contexto_arquivos: list = None,
        modo: str = "clean_code",
        **kwargs,
    ) -> dict:
        log.info("MockAIAgent simulando análise — modo: %s", modo)

        arquivos = kwargs.get("arquivos_alterados") or [
            item["arquivo"] for item in (contexto_arquivos or [])
        ]
        arquivo = arquivos[0] if arquivos else "src/exemplo.pas"

        mapa = kwargs.get("mapa_ancoras") or {}
        ancoras = (mapa.get(arquivo) or {}).get("adicionadas") or []
        linha = ancoras[0] if ancoras else 1

        if modo == "resolver_conflito":
            return {
                "possui_conflito": True,
                "resolucao_conflito": [],
                "sugestoes_clean_code": [],
                "resumo_geral": "Mock: nenhuma resolução real é gerada neste modo.",
                "_erro_parse": False,
                "_modelo": self._modelo,
            }

        return {
            "possui_conflito": False,
            "resolucao_conflito": [],
            "sugestoes_clean_code": [
                {
                    "arquivo": arquivo,
                    "linha": linha,
                    "severidade": "BAIXO",
                    "categoria": "nomenclatura",
                    "titulo": "Sugestão simulada do agente mock",
                    "comentario": (
                        "**🔵 BAIXO · Nomenclatura**\n\n"
                        "**O que foi encontrado:** comentário gerado pelo agente mock, sem análise real.\n\n"
                        "**Por que é um problema:** não é — este texto existe apenas para validar o "
                        "fluxo de postagem de comentários inline no Bitbucket.\n\n"
                        "**Como corrigir:** defina `[ia] ativa = gemini` no config.ini para usar a IA real."
                    ),
                    "confianca": "alta",
                }
            ],
            "resumo_geral": "Execução em modo mock — nenhuma IA real foi consultada.",
            "_erro_parse": False,
            "_modelo": self._modelo,
        }
