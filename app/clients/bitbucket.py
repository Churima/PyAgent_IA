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
            return response.text
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