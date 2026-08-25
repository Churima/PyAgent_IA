"""Resolução de caminhos que funciona tanto rodando pelo Python quanto pelo .exe.

Sob o PyInstaller, `__file__` aponta para uma pasta temporária que é apagada ao
final da execução. Tudo que o usuário precisa editar (config.ini, ai_context/,
logs/) tem que ser resolvido a partir da pasta do executável, e não do bundle.
"""

import os
import sys


def esta_congelado() -> bool:
    """True quando o código está rodando dentro do executável do PyInstaller."""
    return getattr(sys, "frozen", False)


def diretorio_base() -> str:
    """Pasta onde ficam os arquivos editáveis pelo usuário.

    - Congelado: a pasta onde está o .exe.
    - Desenvolvimento: a raiz do repositório.
    """
    if esta_congelado():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def caminho_dados(*partes: str) -> str:
    """Caminho de um arquivo/pasta dentro do diretório base."""
    return os.path.join(diretorio_base(), *partes)


def caminho_recurso(*candidatos: str) -> str | None:
    """Primeiro caminho existente entre os candidatos.

    Procura no bundle do PyInstaller (_MEIPASS) e depois no diretório base, o que
    permite passar o caminho do bundle e o caminho de desenvolvimento juntos:

        caminho_recurso("ai_context/exemplos.md", "app/ai_context/exemplos.md")
    """
    bases = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(meipass)
    bases.append(diretorio_base())

    for base in bases:
        for candidato in candidatos:
            caminho = os.path.join(base, candidato)
            if os.path.exists(caminho):
                return caminho
    return None


def garantir_pasta(*partes: str) -> str:
    """Cria (se preciso) e devolve uma pasta dentro do diretório base."""
    caminho = caminho_dados(*partes)
    os.makedirs(caminho, exist_ok=True)
    return caminho
