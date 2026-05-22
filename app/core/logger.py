import os
import json
from datetime import datetime


def registrar_execucao(dados: dict) -> None:
    try:
        caminho = os.getenv("LOG_PATH", "./logs/resultados_testes.json")
        os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)

        entrada = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "agente": dados.get("agente"),
            "pr_id": dados.get("pr_id"),
            "tempo_segundos": dados.get("tempo_segundos"),
            "possui_conflito": dados.get("possui_conflito"),
            "num_resolucoes": dados.get("num_resolucoes", 0),
            "num_sugestoes_clean_code": dados.get("num_sugestoes_clean_code", 0),
            "resolucao_resumo": dados.get("resolucao_resumo", []),
            "sugestoes_resumo": dados.get("sugestoes_resumo", []),
            "erro_parse": dados.get("erro_parse", False),
            "gitworker_acionado": dados.get("gitworker_acionado", False),
            "gitworker_sucesso": dados.get("gitworker_sucesso"),
        }

        registros = []
        if os.path.isfile(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                try:
                    registros = json.load(f)
                except json.JSONDecodeError:
                    registros = []

        registros.append(entrada)

        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(registros, f, ensure_ascii=False, indent=2)

        print(f"[Logger] Execução registrada em {caminho} ({len(registros)} entradas no total)")
    except Exception as e:
        print(f"[Logger] Falha ao registrar execução (não crítico): {e}")
