import os
import re
from app.clients.bitbucket import BitbucketClient
from app.clients.ai.mock import MockAIAgent
from app.clients.ai.gemini_agent import GeminiAgent

def obter_agente_ia():
    ia_escolhida = os.getenv("ACTIVE_AI", "mock").lower()
    if ia_escolhida == "gemini":
        if os.getenv("GEMINI_API_KEY"):
            print("[Sistema] IA selecionada: Google Gemini")
            return GeminiAgent()
        else:
            print("[Aviso] Chave do Gemini não encontrada.")
            return MockAIAgent()
    return MockAIAgent()

def extrair_arquivos_do_diff(pr_diff):
    return re.findall(r'diff --git a/(.*?) b/', pr_diff)

def process_pull_request(pr_id: int, pr_title: str, source_branch: str, dest_branch: str):
    print(f"\n[Reviewer Service] Processando PR #{pr_id} - '{pr_title}'")
    
    bitbucket_client = BitbucketClient()
    ai_agent = obter_agente_ia()
    
    pr_diff = bitbucket_client.get_pr_diff(pr_id)
    if not pr_diff:
        return {"erro": "Diff não encontrado"}

    # Captura de Arquivos Completos para dar Contexto à IA
    arquivos_alterados = extrair_arquivos_do_diff(pr_diff)
    contexto_arquivos = []

    for path in arquivos_alterados:
        conteudo_source = bitbucket_client.get_file_raw(source_branch, path)
        conteudo_dest = bitbucket_client.get_file_raw(dest_branch, path)
        contexto_arquivos.append({
            "arquivo": path,
            "versao_origem": conteudo_source,
            "versao_destino": conteudo_dest
        })

    print("[Reviewer Service] Enviando análise para a IA...")
    analise = ai_agent.analyze_pr(
        pr_diff=pr_diff, 
        commit_messages=["Analise de integração"],
        contexto_arquivos=contexto_arquivos
    )
    
    # --- Postagem de Clean Code ---
    sugestoes = analise.get("sugestoes_clean_code", [])
    if sugestoes:
        print(f"[Reviewer Service] Postando {len(sugestoes)} sugestões de clean code...")
        for sug in sugestoes:
            bitbucket_client.post_comment(
                pr_id=pr_id, 
                content=f"🤖 **Sugestão da IA:**\n{sug['comentario']}", 
                filepath=sug["arquivo"], 
                line=sug["linha"]
            )
    else:
        print("[Reviewer Service] O código está excelente. Nenhuma sugestão encontrada.")
            
    print("[Reviewer Service] Processamento finalizado com sucesso!")
    return {"status": "sucesso"}