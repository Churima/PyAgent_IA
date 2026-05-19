import os
import re
from app.clients.bitbucket import BitbucketClient
from app.clients.ai.mock import MockAIAgent
from app.clients.ai.gemini_agent import GeminiAgent
from app.services.git_worker import GitWorker
from app.clients.ai.claude_agent import ClaudeAgent

def obter_agente_ia():
    """Função Factory que escolhe a IA baseada no arquivo .env"""
    ia_escolhida = os.getenv("ACTIVE_AI", "mock").lower()
    
    if ia_escolhida == "gemini":
        if os.getenv("GEMINI_API_KEY"):
            print("[Sistema] IA selecionada: Google Gemini")
            return GeminiAgent()
        else:
            print("[Aviso] Chave do Gemini não encontrada. Caimos para o Mock.")
            return MockAIAgent()
    elif ia_escolhida == "claude":
        if os.getenv("CLAUDE_API_KEY"):
            print("[Sistema] IA selecionada: Claude (Anthropic)")
            return ClaudeAgent()
        else:
            print("[Aviso] Chave do Claude não encontrada.")
            return MockAIAgent()
    return MockAIAgent()

def extrair_arquivos_do_diff(pr_diff):
    """Usa regex para encontrar todos os arquivos alterados no diff."""
    return re.findall(r'diff --git a/(.*?) b/', pr_diff)

def process_pull_request(pr_id: int, pr_title: str, source_branch: str, dest_branch: str):
    print(f"\n[Reviewer Service] Iniciando Operação Especial GitWorker no PR #{pr_id}")
    
    bitbucket_client = BitbucketClient()
    
    # --- O CORTA-CORRENTE (CIRCUIT BREAKER) ---
    ultima_msg = bitbucket_client.get_latest_commit_message(source_branch)
    if "🤖 IA Auto-fix" in ultima_msg:
        print("[Reviewer Service] 🛑 O último commit foi feito pela IA. Abortando para evitar Loop Infinito!")
        return {"status": "ignorado", "motivo": "loop_infinito_prevenido"}

    ai_agent = obter_agente_ia()
    
    pr_diff = bitbucket_client.get_pr_diff(pr_id)
    if not pr_diff:
        return {"erro": "Diff não encontrado"}

    # --- Lógica de Captura de Arquivos Completos ---
    arquivos_alterados = extrair_arquivos_do_diff(pr_diff)
    contexto_arquivos = []

    for path in arquivos_alterados:
        print(f"[Reviewer Service] Capturando contexto do arquivo: {path}")
        conteudo_source = bitbucket_client.get_file_raw(source_branch, path)
        conteudo_dest = bitbucket_client.get_file_raw(dest_branch, path)
        
        contexto_arquivos.append({
            "arquivo": path,
            "versao_origem": conteudo_source,
            "versao_destino": conteudo_dest
        })

    print("[Reviewer Service] Enviando análise para a IA (Modo Smart Merge)...")
    analise = ai_agent.analyze_pr(
        pr_diff=pr_diff, 
        commit_messages=["Analise de integração"],
        contexto_arquivos=contexto_arquivos 
    )
    
    # --- NOVO BLOCO: AUTO-FIX REAL COM GIT ---
    teve_merge_real = False
    if analise.get("possui_conflito"):
        resolucoes = analise.get("resolucao_conflito", [])
        if resolucoes:
            worker = GitWorker()
            for res in resolucoes:
                print(f"[Reviewer Service] 🛠 Chamando GitWorker para {res['arquivo']}...")
                
                # Limpa crases markdown se a IA alucinar
                codigo_limpo = res["codigo_completo"].replace("```python", "").replace("```", "").strip()
                
                sucesso = worker.resolve_with_merge(
                    source_branch=source_branch,
                    dest_branch=dest_branch,
                    filepath=res["arquivo"],
                    fixed_content=codigo_limpo
                )
                
                if sucesso:
                    bitbucket_client.post_comment(pr_id, f"🤖 **Auto-fix (Real Git Merge):** Conflito em `{res['arquivo']}` resolvido com commit de merge real. A tag CONFLICTED deve sumir agora!")
                    teve_merge_real = True

    # --- Postagem de Clean Code ---
    # Só postamos sugestões textuais se a IA NÃO fez o commit de merge (para evitar confusão na UI do Bitbucket)
    if not teve_merge_real:
        sugestoes = analise.get("sugestoes_clean_code", [])
        if sugestoes:
            print(f"[Reviewer Service] Postando {len(sugestoes)} sugestões de clean code...")
            for sug in sugestoes:
                bitbucket_client.post_comment(pr_id, sug["comentario"], sug["arquivo"], sug["linha"])
        else:
            print("[Reviewer Service] Nenhuma sugestão de clean code encontrada.")
            
    print("[Reviewer Service] Processamento finalizado!")
    return {"status": "sucesso"}