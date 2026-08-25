"""Agente Anthropic Claude.

Adaptado para consumir os prompts unificados do `prompt_builder` e ler modelo,
limites e timeout do config.ini. O ajuste fino deste backend (uso de tool use
para saída estruturada, cache de prompt) fica para a próxima rodada — a
prioridade atual é o Gemini.
"""

import json
import os
import random
import time

import requests

from app.clients.ai.base import BaseAIAgent
from app.clients.ai.prompt_builder import montar_prompt, resposta_vazia
from app.core.logger import obter_logger

log = obter_logger(__name__)

URL_API = "https://api.anthropic.com/v1/messages"
VERSAO_API = "2023-06-01"
STATUS_TEMPORARIOS = {429, 500, 502, 503, 529}


class ClaudeAgent(BaseAIAgent):
    def __init__(self):
        self.api_key = os.getenv("CLAUDE_API_KEY", "")
        self._modelo = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514") or "claude-sonnet-4-20250514"
        self.timeout = _inteiro("AI_TIMEOUT", 180)
        self.max_tokens = _inteiro("AI_MAX_TOKENS", 16000)
        self.temperatura = _decimal("AI_TEMPERATURA", 0.0)
        self.tentativas = max(1, _inteiro("AI_TENTATIVAS", 3))

    def analyze_pr(
        self,
        pr_diff: str,
        commit_messages: list,
        contexto_arquivos: list = None,
        modo: str = "clean_code",
        **kwargs,
    ) -> dict:
        log.info("Claude (%s) iniciando análise — modo: %s", self._modelo, modo)

        if not self.api_key:
            return resposta_vazia(erro=True, motivo="CLAUDE_API_KEY não configurada")

        system_prompt, user_prompt = montar_prompt(
            modo=modo,
            pr_diff=pr_diff,
            commit_messages=commit_messages,
            contexto_arquivos=contexto_arquivos,
            contexto_extra=self.carregar_contexto(),
            arquivos_alterados=kwargs.get("arquivos_alterados"),
            mapa_ancoras=kwargs.get("mapa_ancoras"),
            source_branch=kwargs.get("source_branch", "origem"),
            dest_branch=kwargs.get("dest_branch", "destino"),
        )

        corpo = {
            "model": self._modelo,
            "max_tokens": self.max_tokens,
            "temperature": self.temperatura,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
                # Prefill: força a resposta a começar direto no JSON.
                {"role": "assistant", "content": "{"},
            ],
        }

        resultado_bruto = self._enviar(corpo)
        if resultado_bruto is None:
            return resposta_vazia(erro=True, motivo=self._ultimo_motivo)

        texto, metadados = resultado_bruto
        resultado = _interpretar_json("{" + texto)
        if resultado is None:
            log.error("Claude devolveu conteúdo que não é JSON válido nem reparável")
            log.debug("Conteúdo recebido: %s", texto[:2000])
            return resposta_vazia(erro=True, motivo="resposta não é JSON válido")

        resultado.setdefault("sugestoes_clean_code", [])
        resultado.setdefault("resolucao_conflito", [])
        resultado.setdefault("resumo_geral", "")
        resultado["_erro_parse"] = False
        resultado["_tokens"] = metadados.get("tokens")
        resultado["_modelo"] = self._modelo

        if metadados.get("truncado"):
            resultado["_truncado"] = True
            log.error(
                "Resposta do Claude truncada em %d tokens de saída. "
                "Aumente [ia] max_tokens no config.ini — o resultado pode estar incompleto.",
                self.max_tokens,
            )

        log.info(
            "Claude concluiu: %d sugestão(ões), %d resolução(ões), tokens=%s",
            len(resultado.get("sugestoes_clean_code") or []),
            len(resultado.get("resolucao_conflito") or []),
            metadados.get("tokens"),
        )
        return resultado

    def _enviar(self, corpo: dict):
        cabecalhos = {
            "x-api-key": self.api_key,
            "anthropic-version": VERSAO_API,
            "content-type": "application/json",
        }
        self._ultimo_motivo = "falha desconhecida"

        for tentativa in range(1, self.tentativas + 1):
            try:
                resposta = requests.post(
                    URL_API, json=corpo, headers=cabecalhos, timeout=self.timeout
                )
            except requests.Timeout:
                self._ultimo_motivo = f"timeout de {self.timeout}s"
                log.warning("Claude: timeout na tentativa %d/%d", tentativa, self.tentativas)
                if tentativa < self.tentativas:
                    _esperar(tentativa)
                    continue
                return None
            except requests.RequestException as erro:
                self._ultimo_motivo = f"falha de rede: {erro}"
                log.warning("Claude: falha de rede na tentativa %d/%d: %s",
                            tentativa, self.tentativas, erro)
                if tentativa < self.tentativas:
                    _esperar(tentativa)
                    continue
                return None

            if resposta.status_code == 200:
                try:
                    return self._extrair(resposta.json())
                except ValueError:
                    self._ultimo_motivo = "corpo da resposta não é JSON"
                    log.error("Claude devolveu HTTP 200 com corpo inválido: %s",
                              (resposta.text or "")[:300])
                    return None

            detalhe = _detalhe_erro(resposta)

            if resposta.status_code in STATUS_TEMPORARIOS and tentativa < self.tentativas:
                log.warning("Claude devolveu HTTP %s (%s). Tentativa %d/%d.",
                            resposta.status_code, detalhe, tentativa, self.tentativas)
                _esperar(tentativa)
                continue

            self._ultimo_motivo = f"HTTP {resposta.status_code}: {detalhe}"
            log.error("Claude recusou a requisição — HTTP %s: %s", resposta.status_code, detalhe)
            if resposta.status_code == 401:
                log.error("Verifique [ia] claude_api_key no config.ini.")
            elif resposta.status_code == 404:
                log.error("Modelo '%s' não encontrado. Verifique [ia] claude_modelo.", self._modelo)
            return None

        return None

    def _extrair(self, dados: dict):
        blocos = dados.get("content") or []
        if not blocos:
            self._ultimo_motivo = "resposta sem conteúdo"
            log.error("Claude devolveu resposta sem 'content': %s",
                      json.dumps(dados, ensure_ascii=False)[:500])
            return None

        texto = "".join(bloco.get("text", "") for bloco in blocos if bloco.get("type") == "text")
        uso = dados.get("usage") or {}
        metadados = {
            "truncado": dados.get("stop_reason") == "max_tokens",
            "tokens": {
                "entrada": uso.get("input_tokens"),
                "saida": uso.get("output_tokens"),
                "total": (uso.get("input_tokens") or 0) + (uso.get("output_tokens") or 0),
            },
        }
        return texto, metadados


def _interpretar_json(texto: str) -> dict | None:
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    limpo = texto.strip()
    inicio = limpo.find("{")
    fim = limpo.rfind("}")
    if inicio != -1 and fim > inicio:
        limpo = limpo[inicio:fim + 1]

    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        pass

    try:
        from json_repair import repair_json
        resultado = json.loads(repair_json(limpo))
        log.warning("JSON do Claude precisou de reparo — resposta pode estar incompleta.")
        return resultado if isinstance(resultado, dict) else None
    except Exception as erro:
        log.error("Reparo de JSON falhou: %s", erro)
        return None


def _detalhe_erro(resposta) -> str:
    try:
        dados = resposta.json()
        erro = dados.get("error") or {}
        return erro.get("message") or str(dados)[:300]
    except ValueError:
        return (resposta.text or "")[:300]


def _esperar(tentativa: int) -> None:
    time.sleep(min(2 ** tentativa, 20) + random.uniform(0, 1))


def _inteiro(variavel: str, padrao: int) -> int:
    try:
        return int(str(os.getenv(variavel, padrao)).strip())
    except (TypeError, ValueError):
        return padrao


def _decimal(variavel: str, padrao: float) -> float:
    try:
        return float(str(os.getenv(variavel, padrao)).strip().replace(",", "."))
    except (TypeError, ValueError):
        return padrao
