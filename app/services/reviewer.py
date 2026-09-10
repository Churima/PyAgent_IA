"""Orquestrador da revisão de Pull Requests.

Fluxo: diff do Bitbucket -> contexto dos arquivos -> agente de IA ->
validação da resposta -> comentários no PR (ou merge real, quando há conflito).

A etapa de validação é o que separa o que a IA disse do que vai para o PR do
cliente: caminho de arquivo inexistente é descartado, número de linha é encaixado
numa âncora real do diff e sugestão de baixa confiança não é publicada.
"""

import fnmatch
import os
import time

from app.clients.ai.claude_agent import ClaudeAgent
from app.clients.ai.gemini_agent import GeminiAgent
from app.clients.ai.mock import MockAIAgent
from app.clients.ai.prompt_builder import EMOJI_SEVERIDADE, ORDEM_SEVERIDADE
from app.clients.bitbucket import BitbucketClient
from app.core.logger import obter_logger, registrar_execucao
from app.services.diff_utils import (
    ajustar_linha,
    estimar_tokens,
    extrair_arquivos_do_diff,
    extrair_janelas,
    filtrar_diff_por_arquivos,
    filtrar_diff_por_extensao,
    mapear_linhas_validas,
    remover_cercas_markdown,
    truncar_conteudo,
)
from app.services.git_worker import GitWorker

log = obter_logger(__name__)

_ALIAS_SEVERIDADE = {
    "MÉDIO": "MEDIO", "MEDIA": "MEDIO", "MÉDIA": "MEDIO", "MEDIUM": "MEDIO",
    "HIGH": "ALTO", "CRITICO": "BLOQUEADOR", "CRÍTICO": "BLOQUEADOR",
    "BLOCKER": "BLOQUEADOR", "LOW": "BAIXO", "INFO": "BAIXO",
}


# --------------------------------------------------------------------------- #
# Seleção do agente                                                            #
# --------------------------------------------------------------------------- #

def obter_agente_ia():
    """Factory que escolhe a IA conforme [ia] ativa do config.ini."""
    escolhida = os.getenv("ACTIVE_AI", "mock").lower()

    if escolhida == "gemini":
        if os.getenv("GEMINI_API_KEY"):
            log.info("IA selecionada: Google Gemini")
            return GeminiAgent()
        log.warning("Chave do Gemini não encontrada. Usando o Mock.")
        return MockAIAgent()

    if escolhida == "claude":
        if os.getenv("CLAUDE_API_KEY"):
            log.info("IA selecionada: Claude (Anthropic)")
            return ClaudeAgent()
        log.warning("Chave do Claude não encontrada. Usando o Mock.")
        return MockAIAgent()

    return MockAIAgent()


def _nome_agente(ai_agent) -> str:
    return type(ai_agent).__name__.replace("Agent", "").replace("AI", "").lower()


# --------------------------------------------------------------------------- #
# Filtro de branch de origem                                                   #
# --------------------------------------------------------------------------- #

def branch_ignorada(source_branch: str) -> str:
    """Padrão de `[revisao] branches_origem_ignoradas` que casa com a branch, ou "".

    PR de `version` para `master` é promoção de release, não trabalho novo: o
    código já foi revisado quando entrou na branch de origem. Revisar de novo
    enche de comentário um PR que ninguém vai tratar como revisão — e, num
    monorepo, custa a cota de token de centenas de arquivos.

    Aceita curinga (`release/*`) e ignora diferença de maiúsculas. A lista vazia
    (o padrão) não ignora nada, então instalação existente não muda de
    comportamento.
    """
    nome = (source_branch or "").strip()
    if not nome:
        return ""

    for padrao in _lista("REVISAO_BRANCHES_IGNORADAS"):
        # fnmatchcase com os dois lados em minúscula, porque fnmatch simples
        # muda de comportamento entre Windows e Linux.
        if fnmatch.fnmatchcase(nome.lower(), padrao.lower()):
            return padrao

    return ""


# --------------------------------------------------------------------------- #
# Entrada principal                                                            #
# --------------------------------------------------------------------------- #

def process_pull_request(pr_id: int, pr_title: str, source_branch: str, dest_branch: str):
    log.info("Iniciando revisão do PR #%s: '%s'", pr_id, pr_title)

    # O webhook já barra antes de abrir a thread; aqui é a mesma regra para quem
    # chamar esta função direto.
    padrao = branch_ignorada(source_branch)
    if padrao:
        log.info("PR #%s ignorado: branch de origem '%s' casa com '%s' em "
                 "[revisao] branches_origem_ignoradas.", pr_id, source_branch, padrao)
        return {"status": "ignorado", "motivo": "branch_origem_ignorada"}

    bitbucket = BitbucketClient()

    # --- CIRCUIT BREAKER: não reagir ao próprio commit ---
    commit_messages = bitbucket.get_recent_commit_messages(source_branch)
    if commit_messages and "🤖 IA Auto-fix" in commit_messages[0]:
        log.info("Último commit foi da própria IA. Abortando para evitar loop infinito.")
        return {"status": "ignorado", "motivo": "loop_infinito_prevenido"}

    ai_agent = obter_agente_ia()
    nome_agente = _nome_agente(ai_agent)

    pr_diff = bitbucket.get_pr_diff(pr_id)
    if not pr_diff:
        log.error("Diff do PR #%s não encontrado ou vazio.", pr_id)
        return {"status": "erro", "motivo": "diff_nao_encontrado"}

    # O diff ia inteiro para a IA, sem limite nenhum. Num repositório Delphi o
    # `.dfm` é gerado pela IDE e o diff dele é enorme — e a IA nem pode comentar
    # nele, porque a extensão é bloqueada. Tirar essas seções aqui economiza
    # antes de qualquer outra coisa.
    tamanho_original = len(pr_diff)
    pr_diff, removidos_do_diff = filtrar_diff_por_extensao(pr_diff, _extensoes_bloqueadas())
    if removidos_do_diff:
        log.info(
            "Removidas do diff %d seção(ões) de extensão bloqueada (%s): %d de %d caracteres.",
            len(removidos_do_diff), ", ".join(sorted(set(removidos_do_diff))[:5]),
            tamanho_original - len(pr_diff), tamanho_original,
        )

    arquivos_alterados = extrair_arquivos_do_diff(pr_diff)
    mapa_ancoras = mapear_linhas_validas(pr_diff)
    log.info("Arquivos alterados no PR: %s", ", ".join(arquivos_alterados) or "(nenhum)")

    if not arquivos_alterados:
        log.info("Nada revisável no PR #%s depois do filtro de extensões.", pr_id)
        return {"status": "ignorado", "motivo": "sem_arquivos_revisaveis"}

    tem_conflito, arquivos_conflito = GitWorker().verificar_conflito(source_branch, dest_branch)

    comum = {
        "pr_id": pr_id,
        "pr_diff": pr_diff,
        "source_branch": source_branch,
        "dest_branch": dest_branch,
        "commit_messages": commit_messages,
        "arquivos_alterados": arquivos_alterados,
        "mapa_ancoras": mapa_ancoras,
        "ai_agent": ai_agent,
        "bitbucket": bitbucket,
    }

    if tem_conflito:
        log.info("Conflito confirmado. Entrando no modo de resolução.")
        dados_log = _processar_conflito(arquivos_conflito=arquivos_conflito, **comum)
    else:
        log.info("PR sem conflito. Entrando no modo de revisão de clean code.")
        dados_log = _processar_clean_code(**comum)

    registrar_execucao({
        "agente": nome_agente,
        "modelo": getattr(ai_agent, "modelo", nome_agente),
        "pr_id": pr_id,
        "possui_conflito": tem_conflito,
        **dados_log,
    })

    log.info("Processamento do PR #%s finalizado.", pr_id)
    return {"status": "sucesso", "conflito": tem_conflito}


# --------------------------------------------------------------------------- #
# Contexto dos arquivos                                                        #
# --------------------------------------------------------------------------- #

def _montar_contexto(bitbucket, arquivos, source_branch, dest_branch,
                     modo: str = "clean_code", mapa_ancoras: dict | None = None) -> list:
    """Baixa o conteúdo dos arquivos do PR, no volume que o modo exige.

    `resolver_conflito` precisa das duas versões inteiras: a IA devolve o
    arquivo completo e o que faltar vira perda de código no commit.

    `clean_code` não precisa. Antes esse modo baixava e enviava as duas versões
    completas de todo arquivo alterado — num PR de 10 `.pas` isso passava de 300
    mil tokens de entrada e estourava a cota antes de o modelo ler qualquer
    coisa. Agora só a versão de origem é baixada, e do texto dela vão para o
    prompt apenas janelas em volta do que mudou, com a numeração real do arquivo
    preservada. O conteúdo integral continua em memória porque o mapa de
    símbolos e a busca de usos (`app/services/simbolos.py`) trabalham sobre ele
    — mas nunca chega a entrar no prompt.
    """
    bloqueadas = _extensoes_bloqueadas()
    limite = _inteiro("REVISAO_MAX_CARACTERES_ARQUIVO", 80000)
    margem = _inteiro("CONTEXTO_MARGEM_LINHAS", 40)
    ancoras = mapa_ancoras or {}
    contexto = []

    for caminho in arquivos:
        if _extensao(caminho) in bloqueadas:
            log.info("Contexto ignorado para '%s' (extensão bloqueada).", caminho)
            continue

        log.info("Capturando contexto do arquivo: %s", caminho)
        origem, truncou_origem = truncar_conteudo(
            bitbucket.get_file_raw(source_branch, caminho), limite
        )

        if modo == "resolver_conflito":
            destino, truncou_destino = truncar_conteudo(
                bitbucket.get_file_raw(dest_branch, caminho), limite
            )
            if truncou_origem or truncou_destino:
                log.warning("Arquivo '%s' truncado por exceder %d caracteres.", caminho, limite)
            contexto.append({
                "arquivo": caminho,
                "versao_origem": origem,
                "versao_destino": destino,
                "nome_origem": source_branch,
                "nome_destino": dest_branch,
            })
            continue

        if truncou_origem:
            log.warning("Arquivo '%s' truncado por exceder %d caracteres.", caminho, limite)

        dados = ancoras.get(caminho) or {}
        alteradas = dados.get("adicionadas") or dados.get("visiveis") or []
        trechos, incluidas = extrair_janelas(origem, alteradas, margem, destacar=alteradas)
        total = len(origem.splitlines()) if origem else 0

        if total and incluidas:
            log.info("Contexto de '%s': %d de %d linhas (%.0f%%).",
                     caminho, incluidas, total, 100 * incluidas / total)

        contexto.append({
            "arquivo": caminho,
            # Fica só em memória, para o mapa de símbolos e a busca de usos.
            "versao_origem": origem,
            "trechos": trechos,
            "linhas_incluidas": incluidas,
            "total_linhas": total,
            "nome_origem": source_branch,
        })

    return contexto


# --------------------------------------------------------------------------- #
# Modo: clean code                                                             #
# --------------------------------------------------------------------------- #

def _processar_clean_code(pr_id, pr_diff, source_branch, dest_branch, commit_messages,
                          arquivos_alterados, mapa_ancoras, ai_agent, bitbucket) -> dict:
    contexto_arquivos = _montar_contexto(
        bitbucket, arquivos_alterados, source_branch, dest_branch,
        modo="clean_code", mapa_ancoras=mapa_ancoras,
    )

    lotes = _dividir_em_lotes(contexto_arquivos, pr_diff)
    inicio = time.time()
    analises = []

    for indice, lote in enumerate(lotes, start=1):
        caminhos = [item["arquivo"] for item in lote]
        diff_lote = filtrar_diff_por_arquivos(pr_diff, caminhos) if len(lotes) > 1 else pr_diff

        if len(lotes) > 1:
            log.info("Enviando para a IA (modo: clean_code) — lote %d/%d: %s",
                     indice, len(lotes), ", ".join(caminhos))
            if indice > 1:
                # Espaçamento entre chamadas por causa do limite de requisições
                # por minuto do plano gratuito.
                time.sleep(_inteiro("AI_PAUSA_ENTRE_LOTES", 2))
        else:
            log.info("Enviando para a IA (modo: clean_code)...")

        analises.append(ai_agent.analyze_pr(
            pr_diff=diff_lote,
            commit_messages=commit_messages,
            contexto_arquivos=lote,
            modo="clean_code",
            arquivos_alterados=caminhos,
            mapa_ancoras=mapa_ancoras,
            source_branch=source_branch,
            dest_branch=dest_branch,
            # Mapa de símbolos e usos são montados sobre o PR inteiro, mesmo
            # quando o lote traz só parte dos arquivos: é isso que preserva a
            # detecção de chamador desatualizado através da fronteira do lote.
            contexto_global=contexto_arquivos,
        ))

    analise = _mesclar_analises(analises)
    tempo_segundos = round(time.time() - inicio, 2)

    brutas = analise.get("sugestoes_clean_code") or []
    validas, descartadas = _validar_sugestoes(brutas, arquivos_alterados, mapa_ancoras)

    log.info("IA devolveu %d sugestão(ões); %d válida(s), %d descartada(s) em %.2fs",
             len(brutas), len(validas), descartadas, tempo_segundos)

    if validas and _booleano("REVISAO_POSTAR_RESUMO", True):
        bitbucket.post_comment(pr_id, _montar_resumo(validas, analise, ai_agent, tempo_segundos))

    postadas = 0
    for sugestao in validas:
        conteudo = _formatar_comentario(sugestao)
        if sugestao["linha"] is None:
            enviado = bitbucket.post_comment(pr_id, f"**{sugestao['arquivo']}**\n\n{conteudo}")
        else:
            enviado = bitbucket.post_comment(
                pr_id, conteudo, sugestao["arquivo"], sugestao["linha"]
            )
        postadas += 1 if enviado else 0

    if not validas:
        log.info("Nenhuma sugestão de clean code publicável para o PR #%s.", pr_id)

    return {
        "tempo_segundos": tempo_segundos,
        "lotes": len(lotes),
        "lotes_com_falha": analise.get("_lotes_com_falha", 0),
        "num_resolucoes": 0,
        "num_sugestoes_clean_code": postadas,
        "num_descartadas": descartadas,
        "resolucao_resumo": [],
        "sugestoes_resumo": [
            {
                "arquivo": item["arquivo"],
                "linha": item["linha"],
                "severidade": item["severidade"],
                "categoria": item.get("categoria", ""),
            }
            for item in validas
        ],
        "erro_parse": analise.get("_erro_parse", False),
        "gitworker_acionado": False,
        "gitworker_sucesso": None,
        "tokens": analise.get("_tokens"),
    }


# Espaço reservado, dentro do orçamento, para o que não depende da quantidade de
# arquivos do lote: system prompt, regras, exemplos, mapa de símbolos e usos.
_RESERVA_PROMPT_FIXO = 15000


def _dividir_em_lotes(contexto_arquivos: list, pr_diff: str) -> list[list]:
    """Divide os arquivos em requisições que caibam no orçamento de entrada.

    Um PR grande ia numa chamada só; quando estourava o limite do modelo, o PR
    inteiro voltava sem nenhuma revisão. Em lotes, cada requisição cabe na cota
    e um arquivo problemático não derruba os outros.
    """
    if not contexto_arquivos:
        return []

    orcamento = _inteiro("AI_MAX_TOKENS_ENTRADA", 60000)
    if orcamento <= 0:
        return [contexto_arquivos]

    disponivel = max(4000, orcamento - _RESERVA_PROMPT_FIXO)

    custos = []
    for item in contexto_arquivos:
        diff_arquivo = filtrar_diff_por_arquivos(pr_diff, [item["arquivo"]])
        custos.append(estimar_tokens(item.get("trechos") or "") + estimar_tokens(diff_arquivo))

    if sum(custos) <= disponivel:
        return [contexto_arquivos]

    lotes: list[list] = []
    atual: list = []
    acumulado = 0

    for item, custo in zip(contexto_arquivos, custos):
        # Arquivo que sozinho estoura o orçamento vai sozinho: cortá-lo mais já
        # foi feito em `truncar_conteudo`, e recusar seria pior que tentar.
        if atual and acumulado + custo > disponivel:
            lotes.append(atual)
            atual, acumulado = [], 0
        atual.append(item)
        acumulado += custo

    if atual:
        lotes.append(atual)

    log.info(
        "PR dividido em %d lote(s): ~%d tokens de conteúdo para um orçamento de %d por requisição.",
        len(lotes), sum(custos), orcamento,
    )
    return lotes


def _mesclar_analises(analises: list) -> dict:
    """Junta o resultado dos lotes numa única análise.

    Um lote que falha não invalida os demais: as sugestões dos que deram certo
    continuam sendo publicadas, e o erro fica registrado em `_erro_parse`.
    """
    if len(analises) == 1:
        return analises[0]

    tokens: dict[str, int] = {}
    for analise in analises:
        for chave, valor in (analise.get("_tokens") or {}).items():
            if isinstance(valor, (int, float)):
                tokens[chave] = tokens.get(chave, 0) + int(valor)

    resumos = [str(a.get("resumo_geral") or "").strip() for a in analises]
    falhas = [a for a in analises if a.get("_erro_parse")]

    if falhas:
        log.warning("%d de %d lote(s) falharam. As sugestões dos demais seguem para o PR.",
                    len(falhas), len(analises))

    return {
        "sugestoes_clean_code": [
            sugestao
            for analise in analises
            for sugestao in (analise.get("sugestoes_clean_code") or [])
        ],
        "resolucao_conflito": [],
        "resumo_geral": " ".join(resumo for resumo in resumos if resumo),
        "_erro_parse": bool(falhas) and len(falhas) == len(analises),
        "_motivo_erro": falhas[0].get("_motivo_erro", "") if falhas else "",
        "_truncado": any(a.get("_truncado") for a in analises),
        "_tokens": tokens or None,
        "_lotes": len(analises),
        "_lotes_com_falha": len(falhas),
    }


def _validar_sugestoes(brutas, arquivos_alterados, mapa_ancoras) -> tuple[list, int]:
    """Descarta o que não pode ir para o PR e encaixa cada item numa âncora real."""
    indice_arquivos = {caminho.replace("\\", "/").lower(): caminho for caminho in arquivos_alterados}
    minima = ORDEM_SEVERIDADE.get(
        (os.getenv("REVISAO_SEVERIDADE_MINIMA", "BAIXO") or "BAIXO").upper(), 3
    )
    maximo = _inteiro("REVISAO_MAX_SUGESTOES", 15)

    validas: list[dict] = []
    descartadas = 0
    vistos: set[tuple] = set()

    for item in brutas:
        if not isinstance(item, dict):
            descartadas += 1
            continue

        caminho_bruto = str(item.get("arquivo") or "").replace("\\", "/").strip()
        caminho = indice_arquivos.get(caminho_bruto.lower())
        if not caminho:
            log.warning("Sugestão descartada: arquivo '%s' não faz parte deste PR.", caminho_bruto)
            descartadas += 1
            continue

        comentario = str(item.get("comentario") or "").strip()
        if not comentario:
            descartadas += 1
            continue

        if str(item.get("confianca", "alta")).lower() == "baixa":
            log.info("Sugestão descartada por baixa confiança em '%s'.", caminho)
            descartadas += 1
            continue

        severidade = _normalizar_severidade(item.get("severidade"))
        if ORDEM_SEVERIDADE[severidade] > minima:
            descartadas += 1
            continue

        linha = ajustar_linha(mapa_ancoras, caminho, item.get("linha"))
        if linha is None:
            log.info("Sem âncora inline para '%s' — vira comentário geral.", caminho)

        chave = (caminho, linha, comentario[:120])
        if chave in vistos:
            descartadas += 1
            continue
        vistos.add(chave)

        validas.append({
            "arquivo": caminho,
            "linha": linha,
            "severidade": severidade,
            "categoria": str(item.get("categoria") or "").strip(),
            "titulo": str(item.get("titulo") or "").strip(),
            "comentario": comentario,
        })

    validas.sort(key=lambda item: (ORDEM_SEVERIDADE[item["severidade"]], item["arquivo"], item["linha"] or 0))

    if len(validas) > maximo:
        log.info("Limitando de %d para %d sugestões (config [revisao] max_sugestoes).",
                 len(validas), maximo)
        descartadas += len(validas) - maximo
        validas = validas[:maximo]

    return validas, descartadas


def _normalizar_severidade(valor) -> str:
    texto = str(valor or "MEDIO").strip().upper()
    texto = _ALIAS_SEVERIDADE.get(texto, texto)
    return texto if texto in ORDEM_SEVERIDADE else "MEDIO"


def _formatar_comentario(sugestao: dict) -> str:
    """Garante o cabeçalho de severidade mesmo se a IA não seguir o formato."""
    comentario = sugestao["comentario"]
    if comentario.lstrip().startswith("**"):
        return comentario

    emoji = EMOJI_SEVERIDADE[sugestao["severidade"]]
    categoria = (sugestao.get("categoria") or "revisão").replace("_", " ").capitalize()
    return f"**{emoji} {sugestao['severidade']} · {categoria}**\n\n{comentario}"


def _montar_resumo(validas: list, analise: dict, ai_agent, tempo_segundos: float) -> str:
    contagem: dict[str, int] = {}
    for item in validas:
        contagem[item["severidade"]] = contagem.get(item["severidade"], 0) + 1

    ordenadas = sorted(contagem.items(), key=lambda par: ORDEM_SEVERIDADE[par[0]])
    placar = " · ".join(
        f"{EMOJI_SEVERIDADE[severidade]} {quantidade} {severidade}"
        for severidade, quantidade in ordenadas
    )

    linhas = [
        "## 🤖 Revisão automática — PyAgent IA",
        "",
        f"**{len(validas)} ponto(s) encontrado(s)** · {placar}",
        "",
    ]

    resumo_geral = str(analise.get("resumo_geral") or "").strip()
    if resumo_geral:
        linhas += [resumo_geral, ""]

    linhas += ["| Arquivo | Linha | Severidade | Ponto |", "|---|---|---|---|"]
    for item in validas:
        titulo = item["titulo"] or (item.get("categoria") or "").replace("_", " ") or "ver comentário"
        linha = item["linha"] if item["linha"] is not None else "—"
        linhas.append(
            f"| `{item['arquivo']}` | {linha} | "
            f"{EMOJI_SEVERIDADE[item['severidade']]} {item['severidade']} | {titulo} |"
        )

    fontes = ", ".join(ai_agent.carregar_contexto().get("fontes") or []) or "nenhuma"
    linhas += [
        "",
        f"_Agente: {getattr(ai_agent, 'modelo', 'desconhecido')} · {tempo_segundos}s · Contexto: {fontes}_",
    ]

    if analise.get("_truncado"):
        linhas.append(
            "\n> ⚠️ A resposta da IA foi truncada por limite de tokens. "
            "Pode haver pontos não reportados — aumente `[ia] max_tokens` no `config.ini`."
        )

    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# Modo: resolução de conflito                                                  #
# --------------------------------------------------------------------------- #

def _processar_conflito(pr_id, pr_diff, source_branch, dest_branch, commit_messages,
                        arquivos_alterados, mapa_ancoras, ai_agent, bitbucket,
                        arquivos_conflito=None) -> dict:
    # Só os arquivos que o Git marcou como não mesclados. O modo de conflito
    # precisa mesmo do arquivo inteiro, então mandar também os que o Git mesclou
    # sozinho multiplicava o prompt à toa — e ainda dava à IA a chance de
    # devolver arquivo que o `GitWorker` descartaria depois, em `ignorados`.
    alvo = _arquivos_para_resolver(arquivos_conflito, arquivos_alterados)

    contexto_arquivos = _montar_contexto(
        bitbucket, alvo, source_branch, dest_branch, modo="resolver_conflito",
    )
    diff_conflito = filtrar_diff_por_arquivos(pr_diff, alvo)

    log.info("Enviando para a IA (modo: resolver_conflito) — %d arquivo(s): %s",
             len(alvo), ", ".join(alvo))
    inicio = time.time()
    analise = ai_agent.analyze_pr(
        pr_diff=diff_conflito or pr_diff,
        commit_messages=commit_messages,
        contexto_arquivos=contexto_arquivos,
        modo="resolver_conflito",
        arquivos_alterados=alvo,
        mapa_ancoras=mapa_ancoras,
        source_branch=source_branch,
        dest_branch=dest_branch,
    )
    tempo_segundos = round(time.time() - inicio, 2)

    resolucoes, pendentes = _validar_resolucoes(
        analise.get("resolucao_conflito") or [], alvo
    )

    resultado_git = {
        "sucesso": False,
        "motivo": "nao_acionado",
        "aplicados": [],
        "nao_resolvidos": [],
        "ignorados": [],
    }
    acionado = False

    if not resolucoes:
        log.warning("Nenhuma resolução aplicável devolvida pela IA.")
        bitbucket.post_comment(pr_id, _comentario_conflito_nao_resolvido(pendentes, analise))
    else:
        log.info("Chamando GitWorker para %s", ", ".join(r["arquivo"] for r in resolucoes))
        acionado = True
        resultado_git = GitWorker().resolve_with_merge(
            source_branch=source_branch,
            dest_branch=dest_branch,
            resolucoes=[
                {"arquivo": r["arquivo"], "codigo_completo": r["codigo_completo"]}
                for r in resolucoes
            ],
        )
        bitbucket.post_comment(
            pr_id, _comentario_conflito(resolucoes, pendentes, resultado_git, analise)
        )

    # O log registra o que foi de fato gravado, não o que a IA propôs.
    aplicados = resultado_git["aplicados"] if acionado else []

    return {
        "tempo_segundos": tempo_segundos,
        "num_resolucoes": len(aplicados),
        "num_sugestoes_clean_code": 0,
        "num_descartadas": len(pendentes) + len(resultado_git["ignorados"]),
        "resolucao_resumo": aplicados,
        "arquivos_ignorados": resultado_git["ignorados"],
        "sugestoes_resumo": [],
        "erro_parse": analise.get("_erro_parse", False),
        "gitworker_acionado": acionado,
        "gitworker_sucesso": resultado_git["sucesso"] if acionado else None,
        "tokens": analise.get("_tokens"),
    }


def _arquivos_para_resolver(arquivos_conflito, arquivos_alterados) -> list[str]:
    """Lista final de arquivos do modo de conflito, na grafia que o diff usa.

    O Git reporta o caminho como está no repositório; o diff pode trazer outra
    caixa. Como `_validar_resolucoes` e o `GitWorker` casam caminho por
    comparação normalizada, vale usar a grafia do diff quando ela existe.
    """
    if not arquivos_conflito:
        log.warning(
            "O Git não devolveu a lista de arquivos em conflito. "
            "Enviando todos os %d arquivo(s) do PR — o prompt fica maior que o necessário.",
            len(arquivos_alterados),
        )
        return list(arquivos_alterados)

    indice = {caminho.replace("\\", "/").lower(): caminho for caminho in arquivos_alterados}
    alvo: list[str] = []

    for caminho in arquivos_conflito:
        normalizado = caminho.replace("\\", "/").lower()
        escolhido = indice.get(normalizado, caminho)
        if escolhido not in alvo:
            alvo.append(escolhido)

    fora_do_diff = [c for c in alvo if c.replace("\\", "/").lower() not in indice]
    if fora_do_diff:
        log.info("Arquivos em conflito que não aparecem no diff do PR: %s", ", ".join(fora_do_diff))

    return alvo


def _validar_resolucoes(brutas, arquivos_alterados) -> tuple[list, list]:
    """Separa o que pode ser commitado do que precisa de revisão humana."""
    indice = {caminho.replace("\\", "/").lower(): caminho for caminho in arquivos_alterados}
    bloqueadas = _extensoes_bloqueadas()

    aplicaveis: list[dict] = []
    pendentes: list[dict] = []

    for item in brutas:
        if not isinstance(item, dict):
            continue

        caminho_bruto = str(item.get("arquivo") or "").replace("\\", "/").strip()
        caminho = indice.get(caminho_bruto.lower(), caminho_bruto)
        explicacao = str(item.get("explicacao") or "").strip()

        if not caminho:
            continue

        if _extensao(caminho) in bloqueadas:
            pendentes.append({
                "arquivo": caminho,
                "motivo": "arquivo gerado pela IDE ou binário — resolução automática desabilitada "
                          "em `[revisao] extensoes_bloqueadas`",
            })
            continue

        if item.get("requer_revisao_humana"):
            pendentes.append({
                "arquivo": caminho,
                "motivo": explicacao or "a IA não teve confiança suficiente para resolver",
            })
            continue

        codigo = remover_cercas_markdown(str(item.get("codigo_completo") or ""))
        if not codigo.strip():
            pendentes.append({"arquivo": caminho, "motivo": "a IA devolveu conteúdo vazio"})
            continue

        if any(marcador in codigo for marcador in ("<<<<<<<", ">>>>>>>", "=======\n")):
            log.error("Resolução de '%s' ainda contém marcador de conflito. Descartada.", caminho)
            pendentes.append({
                "arquivo": caminho,
                "motivo": "a resolução ainda continha marcadores de conflito do Git",
            })
            continue

        aplicaveis.append({
            "arquivo": caminho,
            "codigo_completo": codigo,
            "explicacao": explicacao or "sem explicação fornecida pela IA",
        })

    return aplicaveis, pendentes


def _comentario_conflito(resolucoes, pendentes, resultado_git, analise) -> str:
    aplicados = {caminho.replace("\\", "/").lower() for caminho in resultado_git["aplicados"]}

    if resultado_git["sucesso"]:
        linhas = ["## 🤖 Conflito resolvido automaticamente", ""]
        for item in resolucoes:
            if item["arquivo"].replace("\\", "/").lower() not in aplicados:
                continue
            linhas += [f"**`{item['arquivo']}`** — {item['explicacao']}", ""]
    else:
        linhas = [
            "## ⚠️ Conflito NÃO resolvido automaticamente",
            "",
            f"Motivo: `{resultado_git['motivo']}`. Nenhuma alteração foi enviada ao repositório.",
            "",
        ]
        if resultado_git["nao_resolvidos"]:
            linhas += [
                "Arquivos que o Git marcou como conflitantes e não foram resolvidos:",
                "",
            ]
            linhas += [f"- `{caminho}`" for caminho in resultado_git["nao_resolvidos"]]
            linhas.append("")

    if resultado_git["ignorados"]:
        linhas += [
            "### ⚠️ Verifique manualmente — possível inconsistência semântica",
            "",
            "A IA quis alterar os arquivos abaixo, mas o Git **não** os marcou como conflitantes.",
            "Nada foi gravado neles: resolver conflito semântico automaticamente não é papel deste",
            "agente. Vale a pena olhar se as mudanças combinadas realmente se encaixam.",
            "",
        ]
        linhas += [f"- `{caminho}`" for caminho in resultado_git["ignorados"]]
        linhas.append("")

    if pendentes:
        linhas += ["### Requerem merge manual", ""]
        linhas += [f"- **`{item['arquivo']}`** — {item['motivo']}" for item in pendentes]
        linhas.append("")

    if resultado_git["sucesso"]:
        linhas.append("_Commit de merge real criado. A tag CONFLICTED deve desaparecer._")

    if analise.get("_truncado"):
        linhas.append(
            "\n> ⚠️ A resposta da IA foi truncada por limite de tokens. "
            "Aumente `[ia] max_tokens` no `config.ini` antes de tentar de novo."
        )

    return "\n".join(linhas)


def _comentario_conflito_nao_resolvido(pendentes, analise) -> str:
    linhas = [
        "## ⚠️ Conflito detectado, mas não resolvido automaticamente",
        "",
        "A IA não devolveu nenhuma resolução aplicável. Este PR precisa de merge manual.",
        "",
    ]
    if pendentes:
        linhas += [f"- **`{item['arquivo']}`** — {item['motivo']}" for item in pendentes]
        linhas.append("")
    if analise.get("_erro_parse"):
        motivo = analise.get("_motivo_erro") or "falha na comunicação com a IA"
        linhas.append(f"_Detalhe técnico: {motivo}._")
    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# Auxiliares de configuração                                                   #
# --------------------------------------------------------------------------- #

def _extensao(caminho: str) -> str:
    return os.path.splitext(caminho)[1].lower()


def _extensoes_bloqueadas() -> set[str]:
    bruto = os.getenv("REVISAO_EXTENSOES_BLOQUEADAS", "") or ""
    return {
        item.strip().lower() if item.strip().startswith(".") else f".{item.strip().lower()}"
        for item in bruto.split(",")
        if item.strip()
    }


def _lista(variavel: str) -> list[str]:
    """Valor separado por vírgula do config.ini, já limpo de espaços e vazios."""
    return [item.strip() for item in (os.getenv(variavel, "") or "").split(",") if item.strip()]


def _inteiro(variavel: str, padrao: int) -> int:
    try:
        return int(str(os.getenv(variavel, padrao)).strip())
    except (TypeError, ValueError):
        return padrao


def _booleano(variavel: str, padrao: bool) -> bool:
    valor = str(os.getenv(variavel, "")).strip().lower()
    if valor in ("1", "true", "sim", "yes", "on"):
        return True
    if valor in ("0", "false", "nao", "não", "no", "off"):
        return False
    return padrao
