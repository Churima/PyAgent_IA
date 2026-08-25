@echo off
REM ---------------------------------------------------------------------------
REM  Gera o executavel do PyAgent IA.
REM
REM  Use ESTE arquivo, e nao o build.ps1 diretamente:
REM    - no cmd.exe (ou no duplo clique) o Windows ABRE o .ps1 no Bloco de Notas
REM      em vez de executar, porque .ps1 tem o Notepad como programa associado;
REM    - a ExecutionPolicy padrao do Windows (Restricted) bloqueia .ps1 mesmo
REM      dentro do PowerShell.
REM
REM  Uso:
REM    build.bat            -> build normal
REM    build.bat -Limpar    -> recria a venv de build do zero
REM ---------------------------------------------------------------------------

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*

set CODIGO=%ERRORLEVEL%
echo.
if %CODIGO% NEQ 0 (
    echo [ERRO] O build falhou com codigo %CODIGO%.
) else (
    echo [OK] Build concluido.
)
echo.
pause
exit /b %CODIGO%
