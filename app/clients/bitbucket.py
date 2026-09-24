import os
import urllib.parse

import requests

from app.core.encoding import decodificar, decodificar_diff, encoding_configurado
from app.core.logger import obter_logger

log = obter_logger(__name__)


class BitbucketClient:
    def __init__(self):
        # Autenticação básica da Atlassian: e-mail + API token
        self.email = os.getenv("BITBUCKET_EMAIL")
        self.token = os.getenv("BITBUCKET_API_TOKEN")
        self.workspace = os.getenv("BITBUCKET_WORKSPACE")
        self.repo_slug = os.getenv("BITBUCKET_REPO_SLUG")

        self.base_url = f"https://api.bitbucket.org/2.0/repositories/{self.workspace}/{self.repo_slug}"
        self.auth = (self.email, self.token)
        self.timeout = _inteiro("BITBUCKET_TIMEOUT", 60)

    def get_pr_state(self, pr_id: int) -> str:
        """Estado do PR: OPEN, MERGED, DECLINED, SUPERSEDED, NAO_ENCONTRADO ou "".

        Devolve "" quando não deu para descobrir (rede fora, 5xx, token sem
        permissão). Quem chama trata isso como "siga em frente": uma falha
        passageira de API não pode ser motivo para parar de revisar.
        """
        url = f"{self.base_url}/pullrequests/{pr_id}"

        try:
            resposta = requests.get(url, auth=self.auth, timeout=self.timeout)
        except requests.RequestException as erro:
            log.warning("Falha de rede ao consultar o estado do PR #%s: %s", pr_id, erro)
            return ""

        if resposta.status_code == 200:
            try:
                return str((resposta.json() or {}).get("state") or "").upper()
            except ValueError:
                log.warning("Resposta não-JSON ao consultar o estado do PR #%s.", pr_id)
                return ""

        if resposta.status_code == 404:
            return "NAO_ENCONTRADO"

        log.warning("Falha ao consultar o estado do PR #%s: HTTP %s",
                    pr_id, resposta.status_code)
        return ""

    def get_pr_diff(self, pr_id: int) -> str:
        log.info("Buscando diff do PR #%s", pr_id)
        url = f"{self.base_url}/pullrequests/{pr_id}/diff"

        try:
            resposta = requests.get(url, auth=self.auth, timeout=self.timeout)
        except requests.RequestException as erro:
            log.error("Falha de rede ao buscar diff do PR #%s: %s", pr_id, erro)
            return ""

        if resposta.status_code == 200:
            # Linha a linha: o diff mistura arquivos de codificações diferentes.
            return decodificar_diff(resposta.content)

        log.error("Falha ao buscar diff: %s - %s", resposta.status_code, resposta.text[:300])
        return ""

    def post_comment(self, pr_id: int, content: str, filepath: str = None, line: int = None) -> bool:
        destino = f"{filepath}:{line}" if filepath and line else "comentário geral"
        log.info("Postando comentário no PR #%s (%s)", pr_id, destino)
        url = f"{self.base_url}/pullrequests/{pr_id}/comments"

        payload = {"content": {"raw": content}}
        if filepath and line:
            payload["inline"] = {"path": filepath, "to": line}

        try:
            resposta = requests.post(url, json=payload, auth=self.auth, timeout=self.timeout)
        except requests.RequestException as erro:
            log.error("Falha de rede ao postar comentário no PR #%s: %s", pr_id, erro)
            return False

        if resposta.status_code in (200, 201):
            return True

        log.error("Falha ao postar comentário: %s - %s",
                  resposta.status_code, resposta.text[:300])
        return False

    def create_commit(self, branch_name: str, filepath: str, new_content: str, message: str) -> bool:
        """Cria um commit diretamente na branch via API (sem histórico de merge)."""
        log.info("Criando commit na branch '%s' para o arquivo '%s'", branch_name, filepath)
        url = f"{self.base_url}/src"

        data = {"message": message, "branch": branch_name}
        files = {filepath: (None, new_content)}

        try:
            resposta = requests.post(
                url, data=data, files=files, auth=self.auth, timeout=self.timeout
            )
        except requests.RequestException as erro:
            log.error("Falha de rede ao criar commit: %s", erro)
            return False

        if resposta.status_code in (200, 201):
            log.info("Commit criado com sucesso em '%s'", branch_name)
            return True

        log.error("Falha ao criar commit: %s - %s", resposta.status_code, resposta.text[:300])
        return False

    def get_file_raw(self, branch_name: str, filepath: str) -> str:
        """Baixa o conteúdo completo de um arquivo em uma branch específica."""
        return self.get_file(branch_name, filepath)[0]

    def get_file(self, branch_name: str, filepath: str) -> tuple[str, str]:
        """Conteúdo do arquivo e a codificação em que ele está no repositório.

        O Bitbucket devolve os bytes crus. Ler tudo como UTF-8 transformava cada
        acento de um `.pas` windows-1252 em `�` antes de o texto chegar à
        IA — ver `app/core/encoding.py`.
        """
        log.info("Baixando '%s' da branch '%s'", filepath, branch_name)
        encoded_branch = urllib.parse.quote(branch_name, safe="")
        url = f"{self.base_url}/src/{encoded_branch}/{filepath}"

        try:
            resposta = requests.get(url, auth=self.auth, timeout=self.timeout)
        except requests.RequestException as erro:
            log.warning("Falha de rede ao baixar '%s': %s", filepath, erro)
            return "", encoding_configurado()

        if resposta.status_code == 200:
            return decodificar(resposta.content, origem=filepath)

        log.warning("Arquivo '%s' indisponível na branch '%s': HTTP %s",
                    filepath, branch_name, resposta.status_code)
        return "", encoding_configurado()

    def get_recent_commit_messages(self, branch_name: str, limit: int = 5) -> list:
        """Mensagens dos commits mais recentes da branch."""
        encoded_branch = urllib.parse.quote(branch_name, safe="")
        url = f"{self.base_url}/commits/{encoded_branch}"

        try:
            resposta = requests.get(url, auth=self.auth, timeout=self.timeout)
        except requests.RequestException as erro:
            log.warning("Falha de rede ao buscar commits de '%s': %s", branch_name, erro)
            return []

        if resposta.status_code == 200:
            commits = resposta.json().get("values", [])
            return [commit.get("message", "").strip() for commit in commits[:limit]]

        log.warning("Falha ao buscar commits de '%s': HTTP %s", branch_name, resposta.status_code)
        return []


def _inteiro(variavel: str, padrao: int) -> int:
    try:
        return int(str(os.getenv(variavel, padrao)).strip())
    except (TypeError, ValueError):
        return padrao
