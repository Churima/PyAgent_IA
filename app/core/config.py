"""Camada de configuração do PyAgent IA.

Lê o `config.ini` que fica ao lado do executável e injeta os valores em
`os.environ`, de forma que todo o código existente continue usando `os.getenv`
sem alteração.

Precedência (do mais forte para o mais fraco):
    1. Variável de ambiente já definida no sistema
    2. config.ini
    3. .env (fallback para desenvolvimento local)
    4. Valor padrão embutido
"""

import configparser
import os
import shutil
from typing import Any

from dotenv import load_dotenv

from app.core.paths import caminho_dados, caminho_recurso, diretorio_base

NOME_ARQUIVO_INI = "config.ini"

# (seção, opção) -> (variável de ambiente, valor padrão)
MAPA_CONFIG: dict[tuple[str, str], tuple[str, str]] = {
    ("ia", "ativa"): ("ACTIVE_AI", "mock"),
    ("ia", "gemini_api_key"): ("GEMINI_API_KEY", ""),
    ("ia", "gemini_modelo"): ("GEMINI_MODEL", "gemini-3.1-flash-lite"),
    ("ia", "claude_api_key"): ("CLAUDE_API_KEY", ""),
    ("ia", "claude_modelo"): ("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
    ("ia", "max_tokens"): ("AI_MAX_TOKENS", "16000"),
    ("ia", "temperatura"): ("AI_TEMPERATURA", "0.0"),
    ("ia", "timeout_segundos"): ("AI_TIMEOUT", "180"),
    ("ia", "tentativas"): ("AI_TENTATIVAS", "3"),
    ("ia", "usar_schema_estrito"): ("AI_SCHEMA_ESTRITO", "true"),

    ("bitbucket", "email"): ("BITBUCKET_EMAIL", ""),
    ("bitbucket", "usuario"): ("BITBUCKET_USERNAME", ""),
    ("bitbucket", "api_token"): ("BITBUCKET_API_TOKEN", ""),
    ("bitbucket", "workspace"): ("BITBUCKET_WORKSPACE", ""),
    ("bitbucket", "repo_slug"): ("BITBUCKET_REPO_SLUG", ""),
    ("bitbucket", "timeout_segundos"): ("BITBUCKET_TIMEOUT", "60"),

    ("servidor", "host"): ("FLASK_RUN_HOST", "0.0.0.0"),
    ("servidor", "porta"): ("FLASK_RUN_PORT", "5000"),
    ("servidor", "threads"): ("SERVER_THREADS", "4"),
    ("servidor", "token_webhook"): ("WEBHOOK_TOKEN", ""),
    ("servidor", "processamento_assincrono"): ("WEBHOOK_ASSINCRONO", "true"),

    ("contexto", "pasta"): ("CONTEXTO_PASTA", "ai_context"),
    ("contexto", "max_caracteres"): ("CONTEXTO_MAX_CARACTERES", "60000"),
    ("contexto", "linguagem_predominante"): ("CONTEXTO_LINGUAGEM", ""),

    ("revisao", "max_sugestoes"): ("REVISAO_MAX_SUGESTOES", "15"),
    ("revisao", "severidade_minima"): ("REVISAO_SEVERIDADE_MINIMA", "BAIXO"),
    ("revisao", "idioma_comentarios"): ("REVISAO_IDIOMA", "pt-BR"),
    ("revisao", "postar_resumo"): ("REVISAO_POSTAR_RESUMO", "true"),
    ("revisao", "extensoes_bloqueadas"): (
        "REVISAO_EXTENSOES_BLOQUEADAS",
        ".dfm,.dproj,.res,.dpr,.groupproj,.bpl,.dcu",
    ),
    ("revisao", "max_caracteres_arquivo"): ("REVISAO_MAX_CARACTERES_ARQUIVO", "80000"),

    ("git", "executavel"): ("GIT_EXECUTAVEL", ""),

    ("log", "pasta"): ("LOG_PASTA", "logs"),
    ("log", "nivel"): ("LOG_NIVEL", "INFO"),
    ("log", "salvar_payloads"): ("LOG_SALVAR_PAYLOADS", "false"),
}

# Variáveis cujo valor nunca deve aparecer inteiro no log
SEGREDOS = {
    "GEMINI_API_KEY",
    "CLAUDE_API_KEY",
    "BITBUCKET_API_TOKEN",
    "WEBHOOK_TOKEN",
}

_origens: dict[str, str] = {}
_carregado = False


# --------------------------------------------------------------------------- #
# Leitura                                                                      #
# --------------------------------------------------------------------------- #

def caminho_ini() -> str:
    return caminho_dados(NOME_ARQUIVO_INI)


def _ler_ini() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    caminho = caminho_ini()
    if os.path.isfile(caminho):
        # utf-8-sig porque o Bloco de Notas do Windows grava BOM por padrão
        parser.read(caminho, encoding="utf-8-sig")
    return parser


def carregar_configuracao(verboso: bool = True) -> dict[str, str]:
    """Popula `os.environ` a partir do config.ini / .env / padrões.

    Devolve um dicionário {variável: origem} para fins de diagnóstico.
    """
    global _carregado

    # Snapshot antes do .env, para conseguir distinguir "veio do sistema"
    # de "veio do arquivo .env" e respeitar a precedência.
    env_sistema = {k: v for k, v in os.environ.items() if v}

    load_dotenv()  # não sobrescreve o que já existe em os.environ
    ini = _ler_ini()

    for (secao, opcao), (variavel, padrao) in MAPA_CONFIG.items():
        if env_sistema.get(variavel):
            _origens[variavel] = "ambiente"
            continue

        valor_ini = ini.get(secao, opcao, fallback="").strip() if ini.has_section(secao) else ""
        if valor_ini:
            os.environ[variavel] = valor_ini
            _origens[variavel] = "config.ini"
        elif os.environ.get(variavel):
            _origens[variavel] = ".env"
        else:
            os.environ[variavel] = padrao
            _origens[variavel] = "padrão"

    _carregado = True

    if verboso:
        _imprimir_origens(ini)

    return dict(_origens)


def _imprimir_origens(ini: configparser.ConfigParser) -> None:
    existe_ini = os.path.isfile(caminho_ini())
    print(f"[Config] Diretório base: {diretorio_base()}")
    print(f"[Config] config.ini: {'encontrado' if existe_ini else 'NÃO encontrado'} ({caminho_ini()})")

    for (_secao, _opcao), (variavel, _padrao) in MAPA_CONFIG.items():
        origem = _origens.get(variavel, "?")
        valor = os.environ.get(variavel, "")
        if variavel in SEGREDOS:
            valor = f"<definido: {len(valor)} caracteres>" if valor else "<vazio>"
        elif valor == "":
            valor = "<vazio>"
        print(f"[Config]   {variavel:<32} = {valor:<40} (origem: {origem})")


# --------------------------------------------------------------------------- #
# Acesso tipado                                                                #
# --------------------------------------------------------------------------- #

def esta_carregado() -> bool:
    """True depois que `carregar_configuracao()` rodou nesta sessão."""
    return _carregado


def obter(variavel: str, padrao: str = "") -> str:
    return os.getenv(variavel, padrao) or padrao


def obter_int(variavel: str, padrao: int) -> int:
    try:
        return int(str(os.getenv(variavel, padrao)).strip())
    except (TypeError, ValueError):
        return padrao


def obter_float(variavel: str, padrao: float) -> float:
    try:
        return float(str(os.getenv(variavel, padrao)).strip().replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def obter_bool(variavel: str, padrao: bool = False) -> bool:
    valor = str(os.getenv(variavel, "")).strip().lower()
    if valor in ("1", "true", "sim", "yes", "on"):
        return True
    if valor in ("0", "false", "nao", "não", "no", "off"):
        return False
    return padrao


def obter_lista(variavel: str, padrao: list[str] | None = None) -> list[str]:
    bruto = os.getenv(variavel, "")
    itens = [item.strip() for item in bruto.split(",") if item.strip()]
    return itens or (padrao or [])


def resumo_configuracao() -> dict[str, Any]:
    """Usado pelo health check para mostrar o estado sem vazar segredos."""
    return {
        "ia_ativa": obter("ACTIVE_AI", "mock"),
        "modelo_gemini": obter("GEMINI_MODEL"),
        "modelo_claude": obter("CLAUDE_MODEL"),
        "workspace": obter("BITBUCKET_WORKSPACE"),
        "repositorio": obter("BITBUCKET_REPO_SLUG"),
        "pasta_contexto": obter("CONTEXTO_PASTA"),
        "webhook_protegido": bool(obter("WEBHOOK_TOKEN")),
        "processamento_assincrono": obter_bool("WEBHOOK_ASSINCRONO", True),
        "diretorio_base": diretorio_base(),
    }


# --------------------------------------------------------------------------- #
# Validação                                                                    #
# --------------------------------------------------------------------------- #

def caminho_git() -> str:
    """Executável do Git a ser usado (configurado ou o do PATH)."""
    configurado = obter("GIT_EXECUTAVEL").strip()
    return configurado or "git"


def validar_configuracao() -> tuple[list[str], list[str]]:
    """Devolve (erros, avisos). Erros impedem a subida do servidor."""
    erros: list[str] = []
    avisos: list[str] = []

    obrigatorios_bitbucket = {
        "BITBUCKET_EMAIL": "[bitbucket] email",
        "BITBUCKET_USERNAME": "[bitbucket] usuario",
        "BITBUCKET_API_TOKEN": "[bitbucket] api_token",
        "BITBUCKET_WORKSPACE": "[bitbucket] workspace",
        "BITBUCKET_REPO_SLUG": "[bitbucket] repo_slug",
    }
    for variavel, rotulo in obrigatorios_bitbucket.items():
        if not obter(variavel):
            erros.append(f"config.ini: {rotulo} está vazio")

    ia = obter("ACTIVE_AI", "mock").lower()
    if ia not in ("gemini", "claude", "mock"):
        erros.append(f"config.ini: [ia] ativa = '{ia}' é inválido (use gemini, claude ou mock)")
    elif ia == "gemini" and not obter("GEMINI_API_KEY"):
        erros.append("config.ini: [ia] ativa = gemini mas gemini_api_key está vazio")
    elif ia == "claude" and not obter("CLAUDE_API_KEY"):
        erros.append("config.ini: [ia] ativa = claude mas claude_api_key está vazio")
    elif ia == "mock":
        avisos.append("[ia] ativa = mock — nenhuma IA real será chamada (modo de teste)")

    git = caminho_git()
    if git == "git":
        if not shutil.which("git"):
            erros.append(
                "git não encontrado no PATH — o GitWorker não conseguirá resolver conflitos. "
                "Instale o Git ou preencha [git] executavel no config.ini"
            )
    elif not os.path.isfile(git):
        erros.append(f"config.ini: [git] executavel aponta para um arquivo inexistente: {git}")

    porta = obter_int("FLASK_RUN_PORT", 5000)
    if not 1 <= porta <= 65535:
        erros.append(f"config.ini: [servidor] porta = {porta} está fora da faixa 1-65535")

    if not obter("WEBHOOK_TOKEN"):
        avisos.append(
            "[servidor] token_webhook está vazio — o endpoint aceita qualquer requisição. "
            "Recomendado preencher antes de expor via ngrok"
        )

    pasta_contexto = caminho_dados(obter("CONTEXTO_PASTA", "ai_context"))
    if not os.path.isdir(pasta_contexto):
        avisos.append(f"pasta de contexto não encontrada: {pasta_contexto} — usando exemplos embutidos")
    else:
        arquivos = [
            nome for nome in os.listdir(pasta_contexto)
            if nome.lower().endswith((".md", ".txt"))
        ]
        if not arquivos:
            avisos.append(f"pasta de contexto vazia: {pasta_contexto}")
        elif not any(nome.lower().startswith("regras") for nome in arquivos):
            avisos.append(
                "nenhum arquivo 'regras_*.md' na pasta de contexto — "
                "a IA vai trabalhar apenas com os exemplos genéricos"
            )

    return erros, avisos


# --------------------------------------------------------------------------- #
# Primeira execução                                                            #
# --------------------------------------------------------------------------- #

def garantir_arquivos_iniciais() -> list[str]:
    """Cria config.ini e ai_context/ ao lado do executável, se não existirem.

    Devolve a lista de arquivos criados (vazia quando já estava tudo no lugar).
    """
    criados: list[str] = []

    destino_ini = caminho_ini()
    if not os.path.isfile(destino_ini):
        modelo = caminho_recurso("config.ini.example", "config.ini.example")
        if modelo:
            shutil.copyfile(modelo, destino_ini)
        else:
            with open(destino_ini, "w", encoding="utf-8") as arquivo:
                arquivo.write(_INI_EMBUTIDO)
        criados.append(destino_ini)

    pasta_contexto = caminho_dados(obter("CONTEXTO_PASTA", "ai_context") or "ai_context")
    if not os.path.isdir(pasta_contexto):
        os.makedirs(pasta_contexto, exist_ok=True)
        criados.append(pasta_contexto)

    modelos_contexto = [
        (
            "exemplos_treinamento.md",
            ("ai_context/exemplos_treinamento.md", "app/ai_context/exemplos_treinamento.md"),
        ),
        (
            "regras_projeto.md",
            ("ai_context/regras_projeto.example.md", "app/ai_context/regras_projeto.example.md"),
        ),
    ]
    for nome_destino, candidatos in modelos_contexto:
        destino = os.path.join(pasta_contexto, nome_destino)
        if os.path.isfile(destino):
            continue
        origem = caminho_recurso(*candidatos)
        if origem:
            shutil.copyfile(origem, destino)
            criados.append(destino)

    return criados


_INI_EMBUTIDO = """\
[ia]
ativa            = gemini
gemini_api_key   =
gemini_modelo    = gemini-3.1-flash-lite
claude_api_key   =
claude_modelo    = claude-sonnet-4-20250514
max_tokens       = 16000
temperatura      = 0.0
timeout_segundos = 180

[bitbucket]
email     =
usuario   =
api_token =
workspace =
repo_slug =

[servidor]
host          = 0.0.0.0
porta         = 5000
token_webhook =

[contexto]
pasta          = ai_context
max_caracteres = 60000

[revisao]
max_sugestoes        = 15
idioma_comentarios   = pt-BR
extensoes_bloqueadas = .dfm,.dproj,.res,.dpr,.groupproj,.bpl,.dcu

[git]
executavel =

[log]
pasta           = logs
nivel           = INFO
salvar_payloads = false
"""
