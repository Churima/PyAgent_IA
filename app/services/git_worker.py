import os
import subprocess
import tempfile
import urllib.parse

from app.core.logger import obter_logger

log = obter_logger(__name__)


class GitWorker:
    """Executa merges reais num clone temporário e devolve o resultado ao Bitbucket."""

    def __init__(self):
        self.username = os.getenv("BITBUCKET_USERNAME") or ""
        self.token = os.getenv("BITBUCKET_API_TOKEN") or ""
        self.workspace = os.getenv("BITBUCKET_WORKSPACE") or ""
        self.repo_slug = os.getenv("BITBUCKET_REPO_SLUG") or ""
        self.git = os.getenv("GIT_EXECUTAVEL", "").strip() or "git"

        # O '@' do e-mail precisa virar '%40' para não quebrar a URL do Git
        username_codificado = urllib.parse.quote(self.username, safe="")
        self.repo_url = (
            f"https://{username_codificado}:{self.token}"
            f"@bitbucket.org/{self.workspace}/{self.repo_slug}.git"
        )

    # ------------------------------------------------------------------ #
    # Execução de comandos                                                #
    # ------------------------------------------------------------------ #

    def _executar(self, argumentos: list[str], cwd: str, check: bool = False):
        return subprocess.run(
            [self.git, *argumentos],
            cwd=cwd,
            check=check,
            capture_output=True,
        )

    @staticmethod
    def _saida(resultado) -> str:
        partes = []
        for fluxo in (resultado.stderr, resultado.stdout):
            if fluxo:
                partes.append(fluxo.decode("utf-8", errors="replace").strip())
        return " | ".join(parte for parte in partes if parte) or "sem detalhes"

    def disponivel(self) -> bool:
        try:
            self._executar(["--version"], cwd=os.getcwd(), check=True)
            return True
        except (OSError, subprocess.CalledProcessError):
            return False

    # ------------------------------------------------------------------ #
    # Verificação de conflito                                             #
    # ------------------------------------------------------------------ #

    def verificar_conflito(self, source_branch: str, dest_branch: str) -> tuple[bool, list[str]]:
        """Detecta conflito de merge sem criar commit nem tocar no remoto.

        Devolve (tem_conflito, arquivos_em_conflito). A lista importa tanto
        quanto o booleano: só esses arquivos precisam ir completos para a IA no
        modo de resolução. Antes o método devolvia apenas `bool` e o chamador
        acabava enviando o conteúdo integral de todo arquivo do PR, mesmo os que
        o Git mesclou sozinho.
        """
        log.info("Verificando conflito entre '%s' e '%s'", source_branch, dest_branch)
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # Clone completo (sem --single-branch) para que origin/<dest> já exista.
                self._executar(
                    ["clone", "--branch", source_branch, self.repo_url, "."],
                    cwd=tmpdir, check=True,
                )
                # --no-commit verifica o merge sem exigir user.name/user.email.
                # Saída != 0 aqui significa conflito de conteúdo.
                resultado = self._executar(
                    ["merge", "--no-commit", f"origin/{dest_branch}"], cwd=tmpdir
                )
                tem_conflito = resultado.returncode != 0
                conflitantes = self._arquivos_em_conflito(tmpdir) if tem_conflito else []

                log.info("Resultado da verificação: %s", "CONFLICTED" if tem_conflito else "CLEAN")
                if conflitantes:
                    log.info("Arquivos em conflito segundo o Git: %s", ", ".join(conflitantes))
                elif tem_conflito:
                    log.warning(
                        "Merge falhou mas o Git não listou caminhos não mesclados. "
                        "O contexto vai incluir todos os arquivos do PR."
                    )

                return tem_conflito, conflitantes
            except subprocess.CalledProcessError as erro:
                log.error("Erro na verificação de conflito: %s", self._saida(erro))
                return False, []
            except OSError as erro:
                log.error("Não foi possível executar o Git ('%s'): %s", self.git, erro)
                return False, []

    # ------------------------------------------------------------------ #
    # Resolução                                                           #
    # ------------------------------------------------------------------ #

    def resolve_with_merge(self, source_branch: str, dest_branch: str, resolucoes: list) -> dict:
        """Aplica as resoluções da IA num merge real e envia de volta ao Bitbucket.

        Devolve {"sucesso", "motivo", "aplicados", "nao_resolvidos"}.

        A lista de arquivos que o Git marcou como não mesclados é a ÚNICA
        autorização de escrita, verificada nos dois sentidos:

        - faltou algum arquivo conflitante na resposta da IA? Aborta o merge, porque
          commitar assim deixaria marcadores `<<<<<<<` no repositório do cliente.
        - a IA devolveu algum arquivo que NÃO estava em conflito? É descartado sem
          ser gravado. O Git já mesclou aquele arquivo sozinho; sobrescrevê-lo com
          conteúdo gerado seria a IA "resolvendo" uma inconsistência semântica por
          conta própria, que é exatamente o que este agente não deve fazer.
        """
        resultado = {
            "sucesso": False,
            "motivo": "",
            "aplicados": [],
            "nao_resolvidos": [],
            "ignorados": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                log.info("Criando ambiente temporário em %s", tmpdir)
                self._executar(["clone", self.repo_url, "."], cwd=tmpdir, check=True)

                self._executar(["config", "user.email", "ia-bot@agent.com"], cwd=tmpdir, check=True)
                self._executar(["config", "user.name", "🤖 IA Auto-fix Bot"], cwd=tmpdir, check=True)

                self._executar(["checkout", source_branch], cwd=tmpdir, check=True)

                log.info("Executando: git merge origin/%s", dest_branch)
                self._executar(["fetch", "origin", dest_branch], cwd=tmpdir, check=True)
                merge = self._executar(["merge", f"origin/{dest_branch}"], cwd=tmpdir)

                if merge.returncode == 0:
                    log.info("O Git mesclou sem conflito. Nada a resolver.")
                    resultado["motivo"] = "merge_sem_conflito"
                    return resultado

                conflitantes = self._arquivos_em_conflito(tmpdir)
                autorizados = {_normalizar(caminho): caminho for caminho in conflitantes}

                # Sentido 1: só passa adiante o que o Git realmente marcou como
                # conflitante. O caminho usado é o que o Git reportou, não o que a
                # IA escreveu, para não depender de maiúsculas/barras da resposta.
                aplicaveis = []
                for res in resolucoes:
                    caminho_git = autorizados.get(_normalizar(res["arquivo"]))
                    if caminho_git is None:
                        resultado["ignorados"].append(res["arquivo"])
                        continue
                    aplicaveis.append({**res, "arquivo": caminho_git})

                if resultado["ignorados"]:
                    log.warning(
                        "A IA devolveu %d arquivo(s) que o Git NÃO marcou como conflitante: %s. "
                        "Descartados sem gravar.",
                        len(resultado["ignorados"]), ", ".join(resultado["ignorados"]),
                    )

                # Sentido 2: nenhum arquivo conflitante pode ficar de fora.
                cobertos = {_normalizar(res["arquivo"]) for res in aplicaveis}
                faltantes = [caminho for caminho in conflitantes if _normalizar(caminho) not in cobertos]

                if faltantes:
                    log.error(
                        "A IA não resolveu %d de %d arquivo(s) em conflito: %s. Merge abortado.",
                        len(faltantes), len(conflitantes), ", ".join(faltantes),
                    )
                    self._executar(["merge", "--abort"], cwd=tmpdir)
                    resultado["motivo"] = "resolucao_incompleta"
                    resultado["nao_resolvidos"] = faltantes
                    return resultado

                log.info("Conflito confirmado. Aplicando %d resolução(ões) da IA...", len(aplicaveis))

                for res in aplicaveis:
                    caminho_relativo = res["arquivo"].replace("\\", "/")
                    caminho_absoluto = os.path.join(tmpdir, *caminho_relativo.split("/"))
                    os.makedirs(os.path.dirname(caminho_absoluto), exist_ok=True)

                    conteudo = _preservar_quebras(caminho_absoluto, res["codigo_completo"])
                    with open(caminho_absoluto, "w", encoding="utf-8", newline="") as arquivo:
                        arquivo.write(conteudo)

                    self._executar(["add", "--", caminho_relativo], cwd=tmpdir, check=True)
                    resultado["aplicados"].append(caminho_relativo)
                    log.info("Resolução aplicada: %s", caminho_relativo)

                restantes = self._arquivos_em_conflito(tmpdir)
                if restantes:
                    log.error("Ainda há caminhos em conflito após aplicar as resoluções: %s",
                              ", ".join(restantes))
                    self._executar(["merge", "--abort"], cwd=tmpdir)
                    resultado["motivo"] = "conflito_remanescente"
                    resultado["nao_resolvidos"] = restantes
                    return resultado

                arquivos_str = ", ".join(resultado["aplicados"])
                self._executar(
                    ["commit", "-m", f"🤖 IA Auto-fix: Conflitos resolvidos em {arquivos_str}"],
                    cwd=tmpdir, check=True,
                )

                log.info("Enviando resolução (push) para '%s'...", source_branch)
                self._executar(["push", "origin", source_branch], cwd=tmpdir, check=True)

                resultado["sucesso"] = True
                resultado["motivo"] = "ok"
                return resultado

            except subprocess.CalledProcessError as erro:
                detalhe = self._saida(erro)
                log.error("Falha no Git: %s", detalhe)
                resultado["motivo"] = f"erro_git: {detalhe}"
                return resultado
            except OSError as erro:
                log.error("Não foi possível executar o Git ('%s'): %s", self.git, erro)
                resultado["motivo"] = f"git_indisponivel: {erro}"
                return resultado
            except Exception as erro:
                log.exception("Erro inesperado no GitWorker: %s", erro)
                resultado["motivo"] = f"erro_inesperado: {erro}"
                return resultado

    def _arquivos_em_conflito(self, cwd: str) -> list[str]:
        """Caminhos que o Git marcou como não mesclados (diff-filter=U)."""
        resultado = self._executar(["diff", "--name-only", "--diff-filter=U"], cwd=cwd)
        if resultado.returncode != 0:
            return []
        saida = resultado.stdout.decode("utf-8", errors="replace")
        return [linha.strip() for linha in saida.splitlines() if linha.strip()]


def _normalizar(caminho: str) -> str:
    return caminho.replace("\\", "/").strip().lstrip("./").lower()


def _preservar_quebras(caminho_absoluto: str, conteudo: str) -> str:
    """Mantém o estilo de quebra de linha original do arquivo.

    Repositórios Delphi costumam estar em CRLF. Gravar o arquivo resolvido em LF
    faria o diff do commit mostrar o arquivo inteiro como alterado, escondendo o
    que realmente mudou no merge.
    """
    conteudo = conteudo.replace("\r\n", "\n").replace("\r", "\n")

    usa_crlf = False
    try:
        with open(caminho_absoluto, "rb") as arquivo:
            bruto = arquivo.read()
        usa_crlf = bruto.count(b"\r\n") > 0 and bruto.count(b"\r\n") >= bruto.count(b"\n") / 2
    except OSError:
        pass

    if not conteudo.endswith("\n"):
        conteudo += "\n"

    return conteudo.replace("\n", "\r\n") if usa_crlf else conteudo
