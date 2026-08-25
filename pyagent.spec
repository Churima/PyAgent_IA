# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller para gerar o PyAgentIA.exe.

Gere com:
    pyinstaller pyagent.spec --clean --noconfirm

Os arquivos em `datas` viajam dentro do executável e são usados apenas como
MODELO: na primeira execução eles são copiados para a pasta ao lado do .exe,
onde o usuário pode editá-los.
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
    a.binaries,
    a.datas,
    [],
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
