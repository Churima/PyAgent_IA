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
    print(f"\n[Reviewer Service] Iniciando revisão do PR #{pr_id}: '{pr_title}'")

    bitbucket_client = BitbucketClient()

    # --- CIRCUIT BREAKER ---
    commit_messages = bitbucket_client.get_recent_commit_messages(source_branch)
    if commit_messages and "🤖 IA Auto-fix" in commit_messages[0]:
        print("[Reviewer Service] 🛑 Último commit foi da IA. Abortando para evitar loop infinito!")
        return {"status": "ignorado", "motivo": "loop_infinito_prevenido"}

    ai_agent = obter_agente_ia()

    pr_diff = bitbucket_client.get_pr_diff(pr_id)
    if not pr_diff:
        return {"erro": "Diff não encontrado"}

    # --- VERIFICAÇÃO DE CONFLITO ---
    tem_conflito = _verificar_conflito(source_branch, dest_branch)

    if tem_conflito:
        print("[Reviewer Service] ⚠️ Conflito confirmado. Iniciando modo de resolução...")
        _processar_conflito(pr_id, source_branch, dest_branch, pr_diff, commit_messages, ai_agent, bitbucket_client)
    else:
        print("[Reviewer Service] ✅ PR sem conflito. Iniciando modo de revisão de clean code...")
        _processar_clean_code(pr_id, pr_diff, commit_messages, ai_agent, bitbucket_client)

    print("[Reviewer Service] Processamento finalizado!")
    return {"status": "sucesso"}


def _verificar_conflito(source_branch: str, dest_branch: str) -> bool:
    """Verifica conflito de merge via git local — fonte de verdade definitiva."""
    return GitWorker().verificar_conflito(source_branch, dest_branch)


def _processar_conflito(pr_id, source_branch, dest_branch, pr_diff, commit_messages, ai_agent, bitbucket_client):
    arquivos_alterados = extrair_arquivos_do_diff(pr_diff)
    contexto_arquivos = []

    for path in arquivos_alterados:
        print(f"[Reviewer Service] Capturando contexto do arquivo: {path}")
        contexto_arquivos.append({
            "arquivo": path,
            "versao_origem": bitbucket_client.get_file_raw(source_branch, path),
            "versao_destino": bitbucket_client.get_file_raw(dest_branch, path),
        })

    print("[Reviewer Service] Enviando para a IA (modo: resolver_conflito)...")
    analise = ai_agent.analyze_pr(
        pr_diff=pr_diff,
        commit_messages=commit_messages,
        contexto_arquivos=contexto_arquivos,
        modo="resolver_conflito",
    )

    resolucoes = analise.get("resolucao_conflito", [])
    if not resolucoes:
        print("[Reviewer Service] IA não retornou resolução de conflito.")
        return

    worker = GitWorker()
    for res in resolucoes:
        print(f"[Reviewer Service] 🛠 Chamando GitWorker para {res['arquivo']}...")
        codigo_limpo = res["codigo_completo"].replace("```python", "").replace("```", "").strip()

        sucesso = worker.resolve_with_merge(
            source_branch=source_branch,
            dest_branch=dest_branch,
            filepath=res["arquivo"],
            fixed_content=codigo_limpo,
        )

        if sucesso:
            bitbucket_client.post_comment(
                pr_id,
                f"🤖 **Auto-fix (Real Git Merge):** Conflito em `{res['arquivo']}` resolvido com commit de merge real.",
            )


def _processar_clean_code(pr_id, pr_diff, commit_messages, ai_agent, bitbucket_client):
    print("[Reviewer Service] Enviando para a IA (modo: clean_code)...")
    analise = ai_agent.analyze_pr(
        pr_diff=pr_diff,
        commit_messages=commit_messages,
        modo="clean_code",
    )

    sugestoes = analise.get("sugestoes_clean_code", [])
    if sugestoes:
        print(f"[Reviewer Service] Postando {len(sugestoes)} sugestões de clean code...")
        for sug in sugestoes:
            bitbucket_client.post_comment(pr_id, sug["comentario"], sug["arquivo"], sug["linha"])
    else:
        print("[Reviewer Service] Nenhuma sugestão de clean code encontrada.")