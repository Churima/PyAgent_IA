# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller para gerar o PyAgentIA.exe.

Gere com:
    pyinstaller pyagent.spec --clean --noconfirm

Modo onedir: o resultado é dist/PyAgentIA/ com o PyAgentIA.exe e a pasta
_internal/ (interpretador, DLLs, certifi...). O .exe não roda sem ela.

Não voltar para onefile. O onefile se extrai em %TEMP%\\_MEIxxxxx e roda de lá
enquanto o processo viver; a limpeza de temporários do Windows apaga o que está
há 7 dias sem acesso, e em 09/10/2026 levou o certifi\\cacert.pem de um processo
iniciado em 01/10. Toda chamada HTTPS passou a falhar ("Could not find a suitable
TLS CA certificate bundle") enquanto o webhook seguia respondendo 202, e os PRs
foram perdidos sem aviso. As DLLs já carregadas sobrevivem porque ficam travadas;
arquivos de dados e módulos ainda não importados, não.

Os arquivos em `datas` são usados apenas como MODELO: na primeira execução eles
são copiados para a pasta ao lado do .exe, onde o usuário pode editá-los.
"""

import os

datas = [
    ("config.ini.example", "."),
    ("app/ai_context/exemplos_treinamento.md", "ai_context"),
    ("app/ai_context/regras_projeto.example.md", "ai_context"),
]

# Módulos que o analisador estático do PyInstaller não enxerga sozinho.
hiddenimports = [
    "waitress",
    "waitress.server",
    "json_repair",
]

# Nada disso é usado pelo serviço; excluir mantém o binário pequeno.
excludes = [
    "tkinter",
    "unittest",
    "pydoc_data",
    "matplotlib",
    "numpy",
    "pandas",
    "PIL",
    "pytest",
    "setuptools",
    "sqlite3",
]

a = Analysis(
    ["run.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # binários e dados vão para o COLLECT (onedir)
    name="PyAgentIA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX aumenta muito o falso positivo de antivírus
    console=True,       # serviço de console: os logs aparecem na janela
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icone.ico" if os.path.isfile("assets/icone.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PyAgentIA",
)
