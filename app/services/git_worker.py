import os
import subprocess
import tempfile
import shutil
import urllib.parse

class GitWorker:
    def __init__(self):
        self.username = os.getenv("BITBUCKET_USERNAME")
        self.token = os.getenv("BITBUCKET_API_TOKEN")
        self.workspace = os.getenv("BITBUCKET_WORKSPACE")
        self.repo_slug = os.getenv("BITBUCKET_REPO_SLUG")
        
        # Transforma o '@' do email em '%40' para não quebrar a URL do Git
        username_codificado = urllib.parse.quote(self.username)
        
        # Montamos a URL com o email codificado
        self.repo_url = f"https://{username_codificado}:{self.token}@bitbucket.org/{self.workspace}/{self.repo_slug}.git"

    def resolve_with_merge(self, source_branch, dest_branch, filepath, fixed_content):
        """
        Realiza um merge real em uma pasta temporária para criar um commit de 2 pais.
        """
        # Cria uma pasta temporária que se apaga sozinha no final
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                print(f"[GitWorker] 📁 Criando ambiente temporário em: {tmpdir}")
                
                # 1. Clonar o repositório (apenas o necessário)
                subprocess.run(["git", "clone", self.repo_url, "."], cwd=tmpdir, check=True, capture_output=True)
                
                # 2. Configurar um usuário fantasma para o commit não falhar
                subprocess.run(["git", "config", "user.email", "ia-bot@agent.com"], cwd=tmpdir, check=True)
                subprocess.run(["git", "config", "user.name", "🤖 IA Auto-fix Bot"], cwd=tmpdir, check=True)

                # 3. Checkout na branch do desenvolvedor
                subprocess.run(["git", "checkout", source_branch], cwd=tmpdir, check=True, capture_output=True)

                # 4. Tentar o MERGE da branch de destino (ex: main)
                # Isso vai forçar o Git a entrar em estado de conflito localmente
                print(f"[GitWorker] 🔀 Executando: git merge origin/{dest_branch}")
                subprocess.run(["git", "fetch", "origin", dest_branch], cwd=tmpdir, check=True, capture_output=True)
                
                # O merge vai "falhar" (retornar erro) se houver conflito, por isso não usamos check=True aqui
                subprocess.run(["git", "merge", f"origin/{dest_branch}"], cwd=tmpdir, capture_output=True)

                # 5. A MÁGICA: Sobrescrita do arquivo em conflito com a solução da IA
                full_path = os.path.join(tmpdir, filepath)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(fixed_content)

                # 6. Finalizar o merge com um commit real
                # Como houve um merge iniciado no passo 4, este commit terá 2 PAIS!
                subprocess.run(["git", "add", filepath], cwd=tmpdir, check=True)
                subprocess.run(["git", "commit", "-m", f"🤖 IA Auto-fix: Conflito resolvido em {filepath}"], cwd=tmpdir, check=True)

                # 7. Push de volta para o Bitbucket
                print(f"[GitWorker] 🚀 Enviando resolução (Push) para {source_branch}...")
                subprocess.run(["git", "push", "origin", source_branch], cwd=tmpdir, check=True, capture_output=True)
                
                return True

            except subprocess.CalledProcessError as e:
                err = e.stderr.decode() if e.stderr else "Erro desconhecido"
                print(f"[Erro GitWorker] Falha no Git: {err}")
                return False
            except Exception as e:
                print(f"[Erro GitWorker] Erro inesperado: {e}")
                return False