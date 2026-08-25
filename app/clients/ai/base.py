import os
from abc import ABC, abstractmethod

from app.core.logger import obter_logger
from app.core.paths import caminho_dados, caminho_recurso

log = obter_logger(__name__)

_cache_contexto: dict | None = None
_assinatura_cache: tuple | None = None


class BaseAIAgent(ABC):
    """Contrato comum a qualquer agente de IA (Gemini, Claude, Mock...)."""

    @staticmethod
    def carregar_contexto() -> dict:
        """Lê a pasta `ai_context/` que fica ao lado do executável.

        Todo arquivo `.md`/`.txt` da pasta entra no prompt. Arquivos cujo nome
        começa com "regras" são tratados como REGRAS DO PROJETO (prioridade
        máxima no prompt); o restante entra como exemplos de calibração.

        Devolve {"regras": str, "exemplos": str, "fontes": [nomes]}.
        """
        global _cache_contexto, _assinatura_cache

        pasta = caminho_dados(os.getenv("CONTEXTO_PASTA", "ai_context") or "ai_context")
        max_caracteres = _inteiro(os.getenv("CONTEXTO_MAX_CARACTERES"), 60000)

        arquivos = _listar_arquivos(pasta)
        if not arquivos:
            embutido = caminho_recurso(
                "ai_context/exemplos_treinamento.md",
                "app/ai_context/exemplos_treinamento.md",
            )
            arquivos = [embutido] if embutido else []

        assinatura = tuple((caminho, _mtime(caminho)) for caminho in arquivos) + (max_caracteres,)
        if _cache_contexto is not None and assinatura == _assinatura_cache:
            return _cache_contexto

        regras: list[str] = []
        exemplos: list[str] = []
        fontes: list[str] = []

        for caminho in arquivos:
            conteudo = _ler(caminho)
            if not conteudo:
                continue
            nome = os.path.basename(caminho)
            fontes.append(nome)
            bloco = f"### Fonte: {nome}\n\n{conteudo}"
            if nome.lower().startswith("regras"):
                regras.append(bloco)
            else:
                exemplos.append(bloco)

        contexto = {
            "regras": _limitar("\n\n".join(regras), max_caracteres, "regras"),
            "exemplos": _limitar("\n\n".join(exemplos), max_caracteres, "exemplos"),
            "fontes": fontes,
        }

        if fontes:
            log.info("Contexto carregado de %s: %s", pasta, ", ".join(fontes))
        else:
            log.warning("Nenhum arquivo de contexto encontrado em %s", pasta)

        _cache_contexto = contexto
        _assinatura_cache = assinatura
        return contexto

    @staticmethod
    def _carregar_exemplos() -> str:
        """Compatibilidade com a versão anterior: contexto num único texto."""
        contexto = BaseAIAgent.carregar_contexto()
        return "\n\n".join(parte for parte in (contexto["regras"], contexto["exemplos"]) if parte)

    @abstractmethod
    def analyze_pr(
        self,
        pr_diff: str,
        commit_messages: list,
        contexto_arquivos: list = None,
        modo: str = "clean_code",
        **kwargs,
    ) -> dict:
        """Analisa o PR e devolve o dicionário de resposta padronizado.

        Modos: 'clean_code' | 'resolver_conflito'
        """

    @property
    def modelo(self) -> str:
        """Modelo em uso, para registro no log de execuções."""
        return getattr(self, "_modelo", type(self).__name__)


def _listar_arquivos(pasta: str) -> list[str]:
    if not os.path.isdir(pasta):
        return []
    nomes = sorted(
        nome for nome in os.listdir(pasta)
        if nome.lower().endswith((".md", ".txt")) and not nome.lower().endswith(".example.md")
    )
    return [os.path.join(pasta, nome) for nome in nomes]


def _ler(caminho: str) -> str:
    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            return arquivo.read().strip()
    except (OSError, UnicodeDecodeError) as erro:
        log.warning("Não foi possível ler o arquivo de contexto %s: %s", caminho, erro)
        return ""


def _mtime(caminho: str) -> float:
    try:
        return os.path.getmtime(caminho)
    except OSError:
        return 0.0


def _inteiro(valor, padrao: int) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return padrao


def _limitar(texto: str, maximo: int, rotulo: str) -> str:
    if not texto or len(texto) <= maximo:
        return texto
    log.warning(
        "Contexto de %s tem %d caracteres e foi cortado em %d (ajuste [contexto] max_caracteres)",
        rotulo, len(texto), maximo,
    )
    return texto[:maximo] + "\n\n[... contexto truncado por limite de caracteres ...]"
