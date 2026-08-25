"""Utilitários de leitura do diff unificado do Bitbucket.

O ponto central deste módulo é o mapa de linhas válidas. O Bitbucket interpreta
`inline.to` como a linha do arquivo **de destino**, e não como um deslocamento
dentro do diff. Sem validar o número devolvido pela IA, o comentário cai numa
linha aleatória (ou é descartado silenciosamente pela API).
"""

import re

_CABECALHO_ARQUIVO = re.compile(r'^diff --git a/(?P<origem>.+?) b/(?P<destino>.+?)$')
_CABECALHO_DESTINO = re.compile(r'^\+\+\+ (?:b/)?(?P<caminho>.+?)(?:\t.*)?$')
_CABECALHO_HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(?P<inicio>\d+)(?:,(?P<tamanho>\d+))? @@')

_LINHA_CERCA = re.compile(r'^\s*```[a-zA-Z0-9_+#-]*\s*$')


def extrair_arquivos_do_diff(pr_diff: str) -> list[str]:
    """Caminhos (lado destino) de todos os arquivos alterados no diff."""
    arquivos: list[str] = []
    for linha in (pr_diff or "").splitlines():
        encontrado = _CABECALHO_ARQUIVO.match(linha)
        if encontrado:
            caminho = encontrado.group("destino").strip().strip('"')
            if caminho != "/dev/null" and caminho not in arquivos:
                arquivos.append(caminho)
    return arquivos


def mapear_linhas_validas(pr_diff: str) -> dict[str, dict]:
    """Mapa {arquivo: {"adicionadas": [...], "visiveis": [...]}}.

    - `adicionadas`: linhas introduzidas pelo PR — as melhores âncoras.
    - `visiveis`: adicionadas + contexto, ou seja, tudo que o Bitbucket consegue
      exibir como comentário inline naquele arquivo.
    """
    mapa: dict[str, dict] = {}
    arquivo_atual: str | None = None
    numero_destino = 0
    dentro_hunk = False

    for linha in (pr_diff or "").splitlines():
        cabecalho = _CABECALHO_ARQUIVO.match(linha)
        if cabecalho:
            arquivo_atual = cabecalho.group("destino").strip().strip('"')
            dentro_hunk = False
            if arquivo_atual == "/dev/null":
                arquivo_atual = None
            elif arquivo_atual not in mapa:
                mapa[arquivo_atual] = {"adicionadas": [], "visiveis": []}
            continue

        # `+++ b/arquivo` só é cabeçalho antes do primeiro hunk; dentro de um hunk
        # uma linha começando com "+++" é código adicionado que começa com "++".
        if not dentro_hunk:
            destino = _CABECALHO_DESTINO.match(linha)
            if destino:
                caminho = destino.group("caminho").strip().strip('"')
                if caminho == "/dev/null":
                    arquivo_atual = None
                else:
                    arquivo_atual = caminho
                    mapa.setdefault(arquivo_atual, {"adicionadas": [], "visiveis": []})
                continue

        if arquivo_atual is None:
            continue

        hunk = _CABECALHO_HUNK.match(linha)
        if hunk:
            numero_destino = int(hunk.group("inicio"))
            dentro_hunk = True
            continue

        if not dentro_hunk:
            continue

        if linha.startswith("+"):
            mapa[arquivo_atual]["adicionadas"].append(numero_destino)
            mapa[arquivo_atual]["visiveis"].append(numero_destino)
            numero_destino += 1
        elif linha.startswith("-"):
            continue  # remoção não avança a numeração do destino
        elif linha.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:
            # Contexto. Linha de contexto vazia deveria vir como " ", mas parte das
            # ferramentas remove o espaço final e ela chega totalmente vazia — se
            # não contarmos, toda a numeração do hunk sai deslocada.
            mapa[arquivo_atual]["visiveis"].append(numero_destino)
            numero_destino += 1

    return mapa


def ajustar_linha(mapa: dict[str, dict], arquivo: str, linha) -> int | None:
    """Valida a linha devolvida pela IA e a encaixa na âncora válida mais próxima.

    Devolve None quando o arquivo não tem nenhuma linha comentável — nesse caso o
    chamador deve postar um comentário geral em vez de inline.
    """
    dados = mapa.get(arquivo)
    if not dados:
        return None

    candidatas = dados["adicionadas"] or dados["visiveis"]
    if not candidatas:
        return None

    try:
        alvo = int(linha)
    except (TypeError, ValueError):
        return candidatas[0]

    if alvo in dados["adicionadas"]:
        return alvo
    if alvo in dados["visiveis"]:
        return alvo
    return min(candidatas, key=lambda numero: (abs(numero - alvo), numero))


def resumir_ancoras(mapa: dict[str, dict], max_por_arquivo: int = 60) -> str:
    """Trecho legível com as linhas que a IA pode usar, para entrar no prompt."""
    partes: list[str] = []
    for arquivo, dados in mapa.items():
        linhas = dados["adicionadas"] or dados["visiveis"]
        if not linhas:
            partes.append(f"- {arquivo}: (sem linhas comentáveis)")
            continue
        amostra = linhas[:max_por_arquivo]
        sufixo = f" ... (+{len(linhas) - len(amostra)} linhas)" if len(linhas) > len(amostra) else ""
        partes.append(f"- {arquivo}: {', '.join(str(numero) for numero in amostra)}{sufixo}")
    return "\n".join(partes) if partes else "- (nenhuma linha identificada)"


def remover_cercas_markdown(texto: str) -> str:
    """Remove cercas ``` de qualquer linguagem (pascal, delphi, python, sql...).

    O código resolvido pela IA vai direto para um commit; uma cerca esquecida
    quebra a compilação do arquivo no repositório do cliente.
    """
    if not texto:
        return ""

    # Caso comum: a resposta inteira é um único bloco cercado.
    bloco = re.match(
        r'^\s*```[a-zA-Z0-9_+#-]*[ \t]*\r?\n(?P<conteudo>.*?)\r?\n?[ \t]*```\s*$',
        texto,
        re.DOTALL,
    )
    if bloco:
        return bloco.group("conteudo").strip("\r\n") + "\n"

    # Caso residual: cercas soltas no meio. Nenhuma linguagem de programação tem
    # uma linha que seja exatamente ``` — remover é seguro.
    linhas = [linha for linha in texto.splitlines() if not _LINHA_CERCA.match(linha)]
    limpo = "\n".join(linhas).strip("\r\n")
    return limpo + "\n" if limpo else ""


def truncar_conteudo(conteudo: str, max_caracteres: int) -> tuple[str, bool]:
    """Corta o conteúdo de um arquivo grande, sinalizando o corte."""
    if not conteudo or max_caracteres <= 0 or len(conteudo) <= max_caracteres:
        return conteudo or "", False
    corte = conteudo[:max_caracteres]
    return corte + "\n\n[... arquivo truncado por limite de contexto ...]\n", True
