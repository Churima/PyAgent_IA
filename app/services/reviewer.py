from app.clients.ai.mock import MockAIAgent
from app.clients.bitbucket import BitbucketClient

def process_pull_request(pr_id: int, pr_title: str):
    print(f"\n[Reviewer Service] Iniciando processamento do PR #{pr_id} - '{pr_title}'")
    
    # 1. Instanciamos nossos "trabalhadores"
    bitbucket_client = BitbucketClient()
    ai_agent = MockAIAgent()
    
    # 2. Vamos buscar o código real do Bitbucket
    pr_diff = bitbucket_client.get_pr_diff(pr_id)
    
    if not pr_diff:
        print(f"[Reviewer Service] Não foi possível obter o diff do PR #{pr_id}. Encerrando.")
        return {"erro": "Diff não encontrado"}
        
    # (No futuro, podemos criar uma função no bitbucket_client para buscar commits reais)
    fake_commits = ["Comentário de commit simulado"]
    
    # 3. Mandamos para a IA analisar
    print("[Reviewer Service] Enviando código para análise da IA...")
    analise = ai_agent.analyze_pr(pr_diff=pr_diff, commit_messages=fake_commits)
    
    # 4. Agimos na resposta da IA e postamos de volta no Bitbucket
    print("[Reviewer Service] Análise concluída. Processando e postando resultados...")
    
    # Se a IA disser que tem conflito:
    if analise.get("possui_conflito"):
        msg = "🤖 **IA Agent:** Atenção, detectei que este Pull Request possui conflitos de merge que precisam ser resolvidos."
        bitbucket_client.post_comment(pr_id=pr_id, content=msg)
        
    # Se a IA der sugestões de Clean Code:
    sugestoes = analise.get("sugestoes_clean_code", [])
    for sugestao in sugestoes:
        arquivo = sugestao.get("arquivo")
        linha = sugestao.get("linha")
        comentario_ia = f"🤖 **IA Agent (Clean Code):**\n{sugestao.get('comentario')}"
        
        # O post_comment vai tentar colocar o comentário exatamente na linha do arquivo!
        bitbucket_client.post_comment(
            pr_id=pr_id, 
            content=comentario_ia, 
            filepath=arquivo, 
            line=linha
        )
        
    print("[Reviewer Service] Processamento finalizado com sucesso!\n")
    return analise