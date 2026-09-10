"""Contrato comum dos agentes e carregamento do contexto editável.

O `ai_context/` inteiro ia no prompt de toda revisão. Com os arquivos de
produção (regras + exemplos) isso passa de 60 KB, ~19 mil tokens repetidos em
cada chamada — e boa parte deles é irrelevante para o modo em execução: exemplo
de resolução de conflito não ajuda em nada numa revisão de clean code, e
vice-versa.

Agora cada bloco do arquivo pode declarar a que modo e a que linguagem pertence:

    <!-- pyagent: modo=conflito -->
    <!-- pyagent: modo=cleancode linguagem=delphi -->
    <!-- pyagent: modo=ambos linguagem=todas -->

O marcador vale da linha em que aparece até o próximo marcador do mesmo arquivo.
Arquivo sem nenhum marcador continua indo inteiro nos dois modos, exatamente
como antes — instalação antiga não quebra.

Há outras duas formas de escopar, para material novo que já nasce de um modo só:
o nome do arquivo (`exemplos.conflito.md`, `regras.cleancode.delphi.md`) e a
subpasta (`ai_context/conflito/`, `ai_context/cleancode/delphi/`).

Precedência, do mais fraco para o mais forte: subpasta, nome do arquivo,
marcador interno. Os dois arquivos grandes de regras e exemplos são o caso em
que o marcador ganha — eles alternam de modo várias vezes, compartilham a seção
de contexto do sistema entre os dois modos e se citam por identificador de
regra. Pasta serve para o que é autocontido e de um modo só.
"""

import os
import re
from abc import ABC, abstractmethod

from app.core.logger import obter_logger
from app.core.paths import caminho_dados, caminho_recurso

log = obter_logger(__name__)

MODO_CLEAN_CODE = "clean_code"
MODO_CONFLITO = "resolver_conflito"

_MARCADOR = re.compile(r'^\s*<!--\s*pyagent\s*:\s*(?P<atributos>[^>]*?)\s*-->\s*$', re.IGNORECASE)
_ATRIBUTO = re.compile(r'(?P<chave>\w+)\s*=\s*(?P<valor>[^\s]+)')
_CERCA = re.compile(r'^(`{3,}|~{3,})')

_APELIDOS_MODO = {
    "cleancode": MODO_CLEAN_CODE,
    "clean_code": MODO_CLEAN_CODE,
    "clean": MODO_CLEAN_CODE,
    "revisao": MODO_CLEAN_CODE,
    "conflito": MODO_CONFLITO,
    "conflict": MODO_CONFLITO,
    "merge": MODO_CONFLITO,
    "resolver_conflito": MODO_CONFLITO,
    "ambos": "",
    "todos": "",
    "todas": "",
    "all": "",
}

_LINGUAGENS_CONHECIDAS = {
    "delphi", "pascal", "sql", "csharp", "javascript", "typescript",
    "python", "java", "php", "c", "web", "config",
}

_cache_blocos: list | None = None
_assinatura_cache: tuple | None = None


class BaseAIAgent(ABC):
    """Contrato comum a qualquer agente de IA (Gemini, Claude, Mock...)."""

    @staticmethod
    def carregar_contexto(modo: str = "", linguagens=None) -> dict:
        """Lê a pasta `ai_context/` que fica ao lado do executável.

        Todo arquivo `.md`/`.txt` da pasta entra no prompt. Arquivos cujo nome
        começa com "regras" são tratados como REGRAS DO PROJETO (prioridade
        máxima no prompt); o restante entra como exemplos de calibração.

        `modo` e `linguagens` filtram os blocos marcados. Sem eles, devolve tudo.

        Devolve {"regras": str, "exemplos": str, "fontes": [nomes]}.
        """
        blocos = _carregar_blocos()
        max_caracteres = _inteiro(os.getenv("CONTEXTO_MAX_CARACTERES"), 60000)
        idiomas = {str(item).lower() for item in (linguagens or ())}

        regras: list[str] = []
        exemplos: list[str] = []
        fontes: list[str] = []
        descartados = 0

        for bloco in blocos:
            if not _aplicavel(bloco, modo, idiomas):
                descartados += len(bloco["texto"])
                continue

            destino = regras if bloco["tipo"] == "regras" else exemplos
            destino.append(f"### Fonte: {bloco['rotulo']}\n\n{bloco['texto']}")
            if bloco["nome"] not in fontes:
                fontes.append(bloco["nome"])

        if descartados:
            log.info(
                "Contexto filtrado para o modo '%s': %d caracteres fora de escopo não foram enviados.",
                modo or "todos", descartados,
            )

        return {
            "regras": _limitar("\n\n".join(regras), max_caracteres, "regras"),
            "exemplos": _limitar("\n\n".join(exemplos), max_caracteres, "exemplos"),
            "fontes": fontes,
        }

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


# --------------------------------------------------------------------------- #
# Leitura e segmentação dos arquivos de contexto                               #
# --------------------------------------------------------------------------- #

def _carregar_blocos() -> list[dict]:
    """Lê a pasta e devolve os blocos já segmentados pelos marcadores.

    O cache é do resultado da leitura (invalidado por mtime), não do texto final:
    o filtro por modo é barato e roda a cada chamada.
    """
    global _cache_blocos, _assinatura_cache

    pasta = caminho_dados(os.getenv("CONTEXTO_PASTA", "ai_context") or "ai_context")
    arquivos = _listar_arquivos(pasta)
    if not arquivos:
        embutido = caminho_recurso(
            "ai_context/exemplos_treinamento.md",
            "app/ai_context/exemplos_treinamento.md",
        )
        arquivos = [(embutido, os.path.basename(embutido))] if embutido else []

    assinatura = tuple((caminho, _mtime(caminho)) for caminho, _ in arquivos)
    if _cache_blocos is not None and assinatura == _assinatura_cache:
        return _cache_blocos

    blocos: list[dict] = []
    for caminho, relativo in arquivos:
        conteudo = _ler(caminho)
        if not conteudo:
            continue
        escopo = _escopo_do_caminho(relativo)
        blocos += _segmentar(relativo, conteudo, escopo)
        log.info("Contexto: %s -> %s", relativo, _rotulo(escopo))

    if blocos:
        log.info("Contexto carregado de %s: %d arquivo(s), %d bloco(s)",
                 pasta, len(arquivos), len(blocos))
    else:
        log.warning("Nenhum arquivo de contexto encontrado em %s", pasta)

    _cache_blocos = blocos
    _assinatura_cache = assinatura
    return blocos


def _segmentar(nome: str, conteudo: str, escopo_arquivo: dict | None = None) -> list[dict]:
    """Divide o arquivo nos trechos delimitados pelos marcadores `<!-- pyagent: -->`."""
    # Continua sendo o nome do arquivo que decide regra x exemplo, mesmo dentro
    # de subpasta: `conflito/regras_extra.md` é regra de projeto.
    tipo = "regras" if os.path.basename(nome).lower().startswith("regras") else "exemplos"
    escopo_arquivo = escopo_arquivo if escopo_arquivo is not None else _escopo_do_caminho(nome)

    blocos: list[dict] = []
    escopo_atual = dict(escopo_arquivo)
    acumulado: list[str] = []

    def fechar():
        nonlocal acumulado
        texto = "\n".join(acumulado).strip()
        acumulado = []
        if not texto:
            return
        escopo_explicito = escopo_atual.get("modo") or escopo_atual.get("linguagens")
        rotulo = f"{nome} [{_rotulo(escopo_atual)}]" if escopo_explicito else nome
        blocos.append({
            "nome": nome,
            "rotulo": rotulo,
            "tipo": tipo,
            "texto": texto,
            "modo": escopo_atual.get("modo", ""),
            "linguagens": escopo_atual.get("linguagens", set()),
        })

    cerca = ""
    dentro_comentario = False

    for linha in conteudo.splitlines():
        despojada = linha.strip()

        # Dentro de cerca de código nada é interpretado: o exemplo pode conter
        # `<!--` de verdade (um trecho de XML, por exemplo).
        achado_cerca = _CERCA.match(despojada)
        if achado_cerca:
            marca = achado_cerca.group(0)
            if not cerca:
                cerca = marca
            elif len(marca) >= len(cerca):
                cerca = ""
            acumulado.append(linha)
            continue

        if cerca:
            acumulado.append(linha)
            continue

        if dentro_comentario:
            dentro_comentario = "-->" not in despojada
            continue

        marcador = _MARCADOR.match(linha)
        if marcador:
            fechar()
            escopo_atual = _interpretar_marcador(marcador.group("atributos"), escopo_arquivo)
            continue

        # Comentário HTML é nota para quem mantém o arquivo, não instrução para
        # o modelo — fica fora do prompt e não custa token.
        if despojada.startswith("<!--"):
            dentro_comentario = "-->" not in despojada
            continue

        acumulado.append(linha)

    fechar()
    return blocos


def _interpretar_marcador(atributos: str, padrao: dict) -> dict:
    escopo = {"modo": padrao.get("modo", ""), "linguagens": set(padrao.get("linguagens", set()))}

    for achado in _ATRIBUTO.finditer(atributos or ""):
        chave = achado.group("chave").lower()
        valor = achado.group("valor").strip().lower()

        if chave in ("modo", "mode"):
            if valor in _APELIDOS_MODO:
                escopo["modo"] = _APELIDOS_MODO[valor]
            else:
                log.warning("Marcador pyagent com modo desconhecido: '%s'. Ignorado.", valor)
        elif chave in ("linguagem", "linguagens", "lang"):
            itens = {item for item in valor.split(",") if item}
            escopo["linguagens"] = set() if itens & {"todas", "todos", "all"} else itens

    return escopo


def _escopo_do_caminho(relativo: str) -> dict:
    """Escopo que vem do caminho: primeiro as subpastas, depois o nome.

        conflito/exemplos.md            -> modo conflito
        cleancode/delphi/regras.md      -> modo clean code, linguagem delphi
        exemplos.conflito.delphi.md     -> modo conflito, linguagem delphi

    Segmento que não seja um modo nem uma linguagem conhecida é apenas
    organização e não escopa nada — `conflito/fiscal/` continua sendo conflito.
    O nome do arquivo é mais específico que a pasta e sobrepõe.
    """
    partes = relativo.replace("\\", "/").split("/")
    escopo: dict = {"modo": "", "linguagens": set()}

    for subpasta in partes[:-1]:
        _aplicar_token(escopo, subpasta.lower())

    for token in os.path.splitext(partes[-1])[0].lower().split(".")[1:]:
        _aplicar_token(escopo, token)

    return escopo


def _aplicar_token(escopo: dict, token: str) -> None:
    if token in _APELIDOS_MODO:
        escopo["modo"] = _APELIDOS_MODO[token]
    elif token in _LINGUAGENS_CONHECIDAS:
        escopo["linguagens"].add(token)


def _aplicavel(bloco: dict, modo: str, linguagens: set) -> bool:
    if bloco["modo"] and modo and bloco["modo"] != modo:
        return False
    # Sem linguagem detectada no PR, não dá para filtrar por linguagem sem risco
    # de esvaziar o contexto — nesse caso tudo passa.
    if bloco["linguagens"] and linguagens and not (bloco["linguagens"] & linguagens):
        return False
    return True


def _rotulo(escopo: dict) -> str:
    partes = []
    if escopo.get("modo"):
        partes.append(escopo["modo"])
    if escopo.get("linguagens"):
        partes.append("/".join(sorted(escopo["linguagens"])))
    return " · ".join(partes) or "ambos os modos"


def _listar_arquivos(pasta: str) -> list[tuple[str, str]]:
    """Arquivos de contexto da pasta e de suas subpastas.

    Devolve (caminho_absoluto, caminho_relativo). O relativo é o que aparece no
    log e no rodapé do comentário do PR, então `conflito/regras_extra.md` e
    `cleancode/regras_extra.md` não se confundem.
    """
    if not os.path.isdir(pasta):
        return []

    encontrados: list[tuple[str, str]] = []
    for raiz, subpastas, nomes in os.walk(pasta):
        # Pastas de trabalho e de controle de versão não são contexto.
        subpastas[:] = sorted(s for s in subpastas if not s.startswith((".", "_")))
        for nome in sorted(nomes):
            minusculo = nome.lower()
            if not minusculo.endswith((".md", ".txt")) or minusculo.endswith(".example.md"):
                continue
            caminho = os.path.join(raiz, nome)
            encontrados.append((caminho, os.path.relpath(caminho, pasta).replace("\\", "/")))

    return encontrados


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
