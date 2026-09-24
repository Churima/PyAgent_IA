"""Codificação dos arquivos do repositório do cliente.

A IA só trabalha com texto Unicode — pedir "responda em windows-1252" no prompt
não muda nada. A codificação é problema de transporte e é tratada aqui, nas
duas pontas: decodificar certo o que vem do Bitbucket e do Git, e codificar de
volta na mesma codificação antes de gravar no clone.

Antes, tudo era lido como UTF-8 com `errors="replace"`. Num `.pas` em
windows-1252 o `ç` (byte 0xE7) virava `�` antes de chegar ao prompt, e o arquivo
resolvido era gravado em UTF-8: todo acento do arquivo — não só os do trecho em
conflito, porque a resolução reescreve o arquivo inteiro — aparecia como `Ã§`
na IDE.

A detecção é por arquivo, porque o Delphi moderno salva alguns `.pas` em UTF-8
com BOM e o mesmo repositório pode ter os dois tipos:

    1. BOM UTF-8 / UTF-16          -> a codificação do BOM (mantido na gravação)
    2. bytes não-ASCII que formam
       UTF-8 válido                -> utf-8
    3. qualquer outro caso         -> `[repositorio] encoding` do config.ini

Arquivo só com ASCII cai no item 3 de propósito: se a IA introduzir um `ç` num
arquivo que ainda não tinha acento, ele precisa sair na codificação do
repositório, não em UTF-8.
"""

import codecs
import os

from app.core.logger import obter_logger

log = obter_logger(__name__)

ENCODING_PADRAO = "utf-8"

# Nomes que aparecem no comentário do PR e no prompt. O `codecs` normaliza
# "windows-1252" para "cp1252", que ninguém do lado Delphi reconhece de cara.
_ROTULOS = {
    "utf-8": "UTF-8",
    "utf-8-sig": "UTF-8 com BOM",
    "utf-16": "UTF-16",
    "latin-1": "ISO-8859-1",
    "iso8859-15": "ISO-8859-15",
}


def normalizar_encoding(nome: str) -> str | None:
    """Nome canônico do `codecs`, ou None se a codificação não existe."""
    try:
        return codecs.lookup((nome or "").strip()).name
    except LookupError:
        return None


def encoding_configurado() -> str:
    """Codificação padrão do repositório (`[repositorio] encoding`)."""
    bruto = os.getenv("REPOSITORIO_ENCODING", "") or ENCODING_PADRAO
    # Valor inválido já barra a subida em `validar_configuracao()`; aqui só
    # evita derrubar a revisão se alguém chamar sem passar por lá.
    return normalizar_encoding(bruto) or ENCODING_PADRAO


def rotulo_encoding(encoding: str) -> str:
    """Nome legível: `cp1252` vira `windows-1252`."""
    nome = normalizar_encoding(encoding) or encoding
    if nome.startswith("cp125"):
        return f"windows-{nome[2:]}"
    return _ROTULOS.get(nome, nome)


def eh_utf8(encoding: str) -> bool:
    return (normalizar_encoding(encoding) or "") in ("utf-8", "utf-8-sig")


def detectar_encoding(bruto: bytes) -> str:
    """Codificação de um arquivo a partir dos bytes dele."""
    if bruto.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if bruto.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"

    if not bruto.isascii():
        try:
            bruto.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            pass

    return encoding_configurado()


def decodificar(bruto: bytes, origem: str = "") -> tuple[str, str]:
    """Bytes de um arquivo -> (texto, codificação usada).

    Quando a codificação escolhida não consegue ler algum byte (config diz
    UTF-8 mas o arquivo é windows-1252, ou windows-1252 com um dos cinco bytes
    que ele não define), o texto sai com `�` e o problema vai para o log. O
    `reviewer` recusa commitar resolução que contenha `�`, então isso nunca
    chega ao repositório.
    """
    if not bruto:
        return "", encoding_configurado()

    encoding = detectar_encoding(bruto)
    try:
        return bruto.decode(encoding), encoding
    except UnicodeDecodeError as erro:
        log.warning(
            "'%s' não é %s válido (byte 0x%02X na posição %d). Os caracteres ilegíveis "
            "viram '\\ufffd'. Confira [repositorio] encoding no config.ini.",
            origem or "conteúdo", rotulo_encoding(encoding),
            bruto[erro.start], erro.start,
        )
        return bruto.decode(encoding, errors="replace"), encoding


def decodificar_diff(bruto: bytes) -> str:
    """Decodifica um diff unificado linha a linha.

    Um diff junta arquivos de codificações diferentes, então decidir uma só para
    o texto inteiro erraria metade deles. Linha que é UTF-8 válido fica em UTF-8;
    as demais usam a codificação do repositório.
    """
    if not bruto:
        return ""

    padrao = encoding_configurado()
    linhas = []
    for linha in bruto.split(b"\n"):
        if linha.isascii():
            linhas.append(linha.decode("ascii"))
            continue
        try:
            linhas.append(linha.decode("utf-8"))
        except UnicodeDecodeError:
            linhas.append(linha.decode(padrao, errors="replace"))
    return "\n".join(linhas)


def caracteres_nao_representaveis(texto: str, encoding: str, limite: int = 10) -> list[str]:
    """Caracteres de `texto` que `encoding` não consegue gravar.

    Devolve cada um já descrito como `'→' U+2192`, pronto para log e comentário
    no PR — o código do ponto evita ambiguidade quando o próprio caractere não
    aparece direito na tela de quem lê.
    """
    encontrados: list[str] = []
    vistos: set[str] = set()
    for caractere in texto:
        if caractere in vistos:
            continue
        try:
            caractere.encode(encoding)
        except UnicodeEncodeError:
            vistos.add(caractere)
            encontrados.append(f"'{caractere}' U+{ord(caractere):04X}")
            if len(encontrados) >= limite:
                break
    return encontrados


def codificar(texto: str, encoding: str) -> bytes:
    """Texto -> bytes na codificação do arquivo. Nunca substitui caractere.

    Lança `UnicodeEncodeError` se a IA devolveu algo que a codificação não
    representa (seta, `✓`, emoji num arquivo windows-1252). Trocar por `?` em
    silêncio mudaria o comportamento de uma string Delphi sem ninguém perceber;
    recusar manda o arquivo para merge manual com o motivo explicado.
    """
    # A IA às vezes devolve o BOM como caractere. Com `utf-8-sig`/`utf-16` o
    # codec já grava o BOM, e manter o da IA duplicaria.
    return texto.lstrip("﻿").encode(encoding)
