import os
import requests

class BitbucketClient:
    def __init__(self):
        # Agora buscamos o E-mail e o Token para a autenticação básica
        self.email = os.getenv("BITBUCKET_EMAIL")
        self.token = os.getenv("BITBUCKET_API_TOKEN")
        self.workspace = os.getenv("BITBUCKET_WORKSPACE")
        self.repo_slug = os.getenv("BITBUCKET_REPO_SLUG")
        
        self.base_url = f"https://api.bitbucket.org/2.0/repositories/{self.workspace}/{self.repo_slug}"
        
        # O pulo do gato para o Token da Atlassian: Auth com E-mail e Token
        self.auth = (self.email, self.token)

    def get_pr_diff(self, pr_id: int) -> str:
        print(f"[BitbucketClient] Buscando diff do PR #{pr_id}...")
        url = f"{self.base_url}/pullrequests/{pr_id}/diff"

        response = requests.get(url, auth=self.auth)

        if response.status_code == 200:
            return response.content.decode('utf-8')
        else:
            print(f"[Erro] Falha ao buscar diff: {response.status_code} - {response.text}")
            return ""

    def post_comment(self, pr_id: int, content: str, filepath: str = None, line: int = None):
        print(f"[BitbucketClient] Postando comentário no PR #{pr_id}...")
        url = f"{self.base_url}/pullrequests/{pr_id}/comments"
        
        payload = {
            "content": {
                "raw": content
            }
        }
        
        if filepath and line:
            payload["inline"] = {
                "path": filepath,
                "to": line
            }
            
        response = requests.post(url, json=payload, auth=self.auth)
        
        if response.status_code in [201, 200]:
            print(f"[BitbucketClient] Sucesso! Comentário postado no PR #{pr_id}.")
        else:
            print(f"[Erro] Falha ao postar comentário: {response.status_code} - {response.text}")

    def create_commit(self, branch_name: str, filepath: str, new_content: str, message: str) -> bool:
        """Cria um novo commit diretamente na branch via API."""
        print(f"[BitbucketClient] Criando commit na branch '{branch_name}' para o arquivo '{filepath}'...")
        url = f"{self.base_url}/src"
        
        # A API do Bitbucket exige o formato form-data para arquivos
        data = {
            "message": message,
            "branch": branch_name
        }
        # Enviamos o código corrigido como se fosse um arquivo virtual
        files = {
            filepath: (None, new_content)
        }
        
        # Fazemos o POST usando a mesma autenticação que já configuramos
        response = requests.post(url, data=data, files=files, auth=self.auth)
        
        if response.status_code in [200, 201]:
            print(f"[BitbucketClient] Sucesso! Conflito resolvido e commitado no Bitbucket.")
            return True
        else:
            print(f"[Erro] Falha ao criar commit: {response.status_code} - {response.text}")
            return False  

    def get_file_raw(self, branch_name: str, filepath: str) -> str:
        """Baixa o conteúdo completo de um arquivo em uma branch específica."""
        print(f"[BitbucketClient] Baixando arquivo '{filepath}' da branch '{branch_name}'...")
        url = f"{self.base_url}/src/{branch_name}/{filepath}"

        response = requests.get(url, auth=self.auth)

        if response.status_code == 200:
            return response.content.decode('utf-8')
        else:
            print(f"[Aviso] Arquivo não encontrado ou erro na branch {branch_name}: {response.status_code}")
            return ""                      
            
    def get_recent_commit_messages(self, branch_name: str, limit: int = 5) -> list:
        """Retorna as mensagens dos commits mais recentes da branch."""
        url = f"{self.base_url}/commits/{branch_name}"
        response = requests.get(url, auth=self.auth)

        if response.status_code == 200:
            commits = response.json().get('values', [])
            return [c.get('message', '').strip() for c in commits[:limit]]
        return []