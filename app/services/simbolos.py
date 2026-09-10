"""Mapa de símbolos dos arquivos do PR.

Trocar o arquivo inteiro por janelas em volta do diff resolve o custo, mas
sozinho enfraqueceria a detecção de inconsistência semântica: o caso clássico é
uma assinatura alterada num arquivo enquanto o chamador, em outro arquivo, fica
como estava — e o chamador intocado não aparece no diff nem na janela.

Este módulo cobre esse buraco por um preço muito menor que o arquivo completo:

1. `montar_mapa_simbolos` lista as declarações (rotinas, classes, interfaces) de
   cada arquivo do PR. Costuma ficar em 2-3% do tamanho do fonte.
2. `identificadores_alterados` extrai os nomes que o diff mexeu.
3. `janelas_de_referencia` procura esses nomes no conteúdo dos DEMAIS arquivos e
   devolve trechos curtos em volta de cada uso — inclusive quando aquele arquivo
   não teve nenhuma linha alterada neste PR.

O resultado é mais dirigido que o texto integral: o modelo recebe exatamente os
pontos de uso em vez de precisar varrer milhares de linhas atrás deles.
"""

import os
import re

_LINGUAGEM_POR_EXTENSAO = {
    ".pas": "delphi", ".dpr": "delphi", ".dpk": "delphi", ".inc": "delphi",
    ".pp": "delphi", ".lpr": "delphi",
    ".sql": "sql", ".fb": "sql", ".ora": "sql", ".pgs": "sql", ".pks": "sql", ".pkb": "sql",
    ".cs": "csharp",
    ".js": "javascript", ".jsx": "javascript", ".ts": "javascript", ".tsx": "javascript",
    ".py": "python",
    ".java": "java",
    ".php": "php",
}

# Delphi: declaração de rotina, tanto no `interface` quanto na `implementation`.
_DELPHI_ROTINA = re.compile(
    r'^\s*(?P<tipo>procedure|function|constructor|destructor)\s+'
    r'(?P<nome>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*'
    r'(?P<params>\([^)]*\))?\s*(?P<retorno>:\s*[\w.<>\[\], ]+?)?\s*;',
    re.IGNORECASE,
)
_DELPHI_TIPO = re.compile(
    r'^\s*(?P<nome>[A-Za-z_]\w*)\s*=\s*'
    r'(?P<tipo>packed\s+record|class\s*\([^)]*\)|class\b|interface\b|record\b)',
    re.IGNORECASE,
)

_PADROES = {
    "delphi": (_DELPHI_ROTINA, _DELPHI_TIPO),
    "python": (
        re.compile(r'^\s*(?P<tipo>def|class)\s+(?P<nome>\w+)\s*(?P<params>\([^)]*\))?'),
        None,
    ),
    "javascript": (
        re.compile(
            r'^\s*(?:export\s+)?(?:async\s+)?(?P<tipo>function|class)\s+(?P<nome>\w+)\s*'
            r'(?P<params>\([^)]*\))?'
        ),
        None,
    ),
    "csharp": (
        re.compile(
            r'^\s*(?:public|private|protected|internal)\s+'
            r'(?:static\s+|async\s+|virtual\s+|override\s+)*'
            r'(?P<retorno>[\w<>\[\],.]+)\s+(?P<nome>\w+)\s*(?P<params>\([^)]*\))'
        ),
        None,
    ),
    "java": (
        re.compile(
            r'^\s*(?:public|private|protected)\s+(?:static\s+|final\s+|abstract\s+)*'
            r'(?P<retorno>[\w<>\[\],.]+)\s+(?P<nome>\w+)\s*(?P<params>\([^)]*\))'
        ),
        None,
    ),
    "sql": (
        re.compile(
            r'^\s*CREATE\s+(?:OR\s+REPLACE\s+)?'
            r'(?P<tipo>PROCEDURE|FUNCTION|TABLE|VIEW|TRIGGER)\s+(?P<nome>[\w."]+)',
            re.IGNORECASE,
        ),
        None,
    ),
}

# Identificadores curtos ou genéricos demais para servirem de busca — procurar
# por "Create" num repositório Delphi devolve o arquivo inteiro.
_RUIDO = {
    "create", "free", "destroy", "begin", "end", "result", "self", "inherited",
    "add", "get", "set", "close", "open", "next", "first", "last", "clear",
    "execute", "value", "text", "name", "count", "item", "items", "data",
    "true", "false", "nil", "null", "string", "integer", "boolean", "double",
}
_TAMANHO_MINIMO_IDENTIFICADOR = 5


def linguagem_de(caminho: str) -> str:
    return _LINGUAGEM_POR_EXTENSAO.get(os.path.splitext(caminho or "")[1].lower(), "")


def extrair_simbolos(caminho: str, conteudo: str, maximo: int = 120) -> list[dict]:
    """Declarações do arquivo, com o número da linha em que aparecem."""
    linguagem = linguagem_de(caminho)
    padroes = _PADROES.get(linguagem)
    if not padroes or not conteudo:
        return []

    rotina, tipo = padroes
    encontrados: list[dict] = []
    vistos: set[str] = set()

    for numero, linha in enumerate(conteudo.splitlines(), start=1):
        if len(encontrados) >= maximo:
            break
        if linha.lstrip().startswith(("//", "#", "--", "*")):
            continue

        achado = rotina.match(linha)
        origem = "rotina"
        if not achado and tipo is not None:
            achado = tipo.match(linha)
            origem = "tipo"
        if not achado:
            continue

        nome = (achado.groupdict().get("nome") or "").strip()
        if not nome:
            continue

        assinatura = " ".join(achado.group(0).split()).rstrip(";")
        chave = assinatura.lower()
        if chave in vistos:
            continue
        vistos.add(chave)

        encontrados.append({
            "linha": numero,
            "nome": nome,
            "assinatura": assinatura,
            "origem": origem,
        })

    return encontrados


def montar_mapa_simbolos(contexto_arquivos: list | None, maximo_por_arquivo: int = 80) -> str:
    """Bloco textual com as declarações de todos os arquivos do PR."""
    if not contexto_arquivos:
        return "(sem símbolos extraídos)"

    partes: list[str] = []
    for item in contexto_arquivos:
        caminho = item.get("arquivo", "")
        simbolos = extrair_simbolos(
            caminho, item.get("versao_origem") or "", maximo=maximo_por_arquivo
        )
        if not simbolos:
            continue
        partes.append(f"{caminho}:")
        partes += [f"  {simbolo['linha']:>6} | {simbolo['assinatura']}" for simbolo in simbolos]

    return "\n".join(partes) if partes else "(sem símbolos extraídos)"


def identificadores_alterados(mapa_ancoras: dict | None, contexto_arquivos: list | None,
                              maximo: int = 40) -> dict[str, str]:
    """Nomes declarados em linhas que o PR alterou -> arquivo onde foram declarados.

    São esses os candidatos a quebrar chamadores: se a assinatura mudou, quem
    chama precisa mudar junto.
    """
    if not contexto_arquivos:
        return {}

    ancoras = mapa_ancoras or {}
    resultado: dict[str, str] = {}

    for item in contexto_arquivos:
        caminho = item.get("arquivo", "")
        dados = ancoras.get(caminho) or {}
        alteradas = set(dados.get("adicionadas") or ())
        if not alteradas:
            continue

        for simbolo in extrair_simbolos(caminho, item.get("versao_origem") or ""):
            if simbolo["linha"] not in alteradas:
                continue
            nome = simbolo["nome"].split(".")[-1]
            if len(nome) < _TAMANHO_MINIMO_IDENTIFICADOR or nome.lower() in _RUIDO:
                continue
            resultado.setdefault(nome, caminho)
            if len(resultado) >= maximo:
                return resultado

    return resultado


def janelas_de_referencia(identificadores: dict, contexto_arquivos: list | None,
                          margem: int = 6, maximo_por_identificador: int = 4) -> str:
    """Trechos curtos em volta de cada uso dos identificadores alterados.

    Procura apenas nos arquivos que já fazem parte do PR — o objetivo é flagrar
    incoerência dentro da própria mudança, não varrer o monorepo inteiro.
    """
    if not identificadores or not contexto_arquivos:
        return ""

    conteudos = {
        item.get("arquivo", ""): (item.get("versao_origem") or "").splitlines()
        for item in contexto_arquivos
    }

    blocos: list[str] = []
    for nome, arquivo_origem in identificadores.items():
        padrao = re.compile(r'\b' + re.escape(nome) + r'\b', re.IGNORECASE)
        ocorrencias: list[str] = []

        for caminho, linhas in conteudos.items():
            if caminho == arquivo_origem:
                continue  # a declaração já está na janela do próprio arquivo
            for numero, linha in enumerate(linhas, start=1):
                if not padrao.search(linha):
                    continue
                inicio = max(1, numero - margem)
                fim = min(len(linhas), numero + margem)
                trecho = "\n".join(
                    f"  {indice:>6} | {linhas[indice - 1]}" for indice in range(inicio, fim + 1)
                )
                ocorrencias.append(f"{caminho}, em volta da linha {numero}:\n{trecho}")
                if len(ocorrencias) >= maximo_por_identificador:
                    break
            if len(ocorrencias) >= maximo_por_identificador:
                break

        if ocorrencias:
            blocos.append(
                f"### `{nome}` — declarado/alterado em {arquivo_origem}\n\n"
                + "\n\n".join(ocorrencias)
            )

    return "\n\n".join(blocos)
