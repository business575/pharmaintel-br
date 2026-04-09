"""
ai_auditor.py — PharmaIntel BR AI Output Quality Auditor

Scores AI responses for confidence, detects hallucination risk,
blocks outputs below threshold, and adds transparency notes.
Target: 99% accuracy, 0% critical errors reaching clients.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

RiskLevel = Literal["low", "medium", "critical"]

CONFIDENCE_BLOCK_THRESHOLD = 60

# Scoring weights (must sum to 100)
WEIGHT_LENGTH   = 15
WEIGHT_CITATIONS = 30
WEIGHT_HEDGING  = 25
WEIGHT_NUMERIC  = 30

# Tools that use potentially delayed data sources
DELAYED_DATA_TOOLS = {
    "get_market_overview", "get_top_ncm", "get_monthly_trend",
    "get_ncm_detail", "get_compliance_alerts", "get_top_countries",
    "get_empresa_detail",
}
ANVISA_TOOLS = {
    "get_anvisa_registros_recentes", "get_anvisa_alertas_vencimento_real",
    "get_anvisa_dispositivos_por_risco", "get_alertas_vencimento",
    "get_produtos_vencendo",
}

HALLUCINATION_PATTERNS = [
    (r"(?i)\b(invented|fictitious|made.up)\b",             "explicit fabrication language"),
    (r"(?i)\b(always|never|all companies|every pharmacy)\b","unsupported absolute claim"),
    (r"(?i)source:\s*[\"']?none[\"']?",                    "no source declared"),
    (r"(?i)(the exact figure is|precisely exactly)\s+\d",  "false precision claim"),
    (r"(?i)\b(todas as empresas|todo o mercado|nunca foi registrado)\b",
     "unsupported absolute claim (PT)"),
    (r"(?i)(o valor exato é|precisamente|exatamente)\s+\d","false precision claim (PT)"),
    (r"(?i)\b(é sabido que|é fato que|obviamente)\b",      "unverifiable assertion (PT)"),
]


@dataclass
class AuditResult:
    confidence_score: int
    risk_level: RiskLevel
    blocked: bool
    flags: list[str] = field(default_factory=list)
    transparency_note: str = ""
    original_text: str = ""
    audited_text: str = ""

    @property
    def result_str(self) -> str:
        if self.blocked:
            return "fail"
        if self.flags:
            return "warn"
        return "pass"

    def to_details_json(self) -> str:
        return json.dumps({
            "confidence_score": self.confidence_score,
            "risk_level":       self.risk_level,
            "blocked":          self.blocked,
            "flags":            self.flags,
            "transparency_note": self.transparency_note,
        }, ensure_ascii=False)


class AIOutputAuditor:
    """Audits AI-generated responses before delivery to the client."""

    # ------------------------------------------------------------------
    # Sub-scorers
    # ------------------------------------------------------------------

    def _score_length(self, text: str) -> int:
        n = len(text.strip())
        if n < 50:   return 0
        if n < 150:  return 30
        if n < 400:  return 60
        return 100

    def _score_citations(self, text: str, tool_calls: list) -> int:
        score = 0
        anchors = 0

        # 8-digit NCM patterns (chapters 30 or 90)
        anchors += len(re.findall(r"\b[39]\d{7}\b", text))
        # USD monetary values
        anchors += len(re.findall(r"US\$\s*[\d,.]+[KMBbi]?|\$[\d,]+", text, re.IGNORECASE))
        # Percentage values
        anchors += len(re.findall(r"\d+[,.]\d+\s*%", text))
        # BRL values
        anchors += len(re.findall(r"R\$\s*[\d,.]+[KMB]?", text, re.IGNORECASE))

        if anchors == 0 and not tool_calls:  score = 0
        elif anchors <= 2 or tool_calls:     score = 40
        elif anchors <= 5:                   score = 70
        else:                                score = 100

        if tool_calls:
            score = min(100, score + 20)

        return score

    def _score_hedging(self, text: str) -> int:
        score = 50  # neutral baseline

        hedge_patterns = [
            r"(?i)(estimado|aprox\.?|aproximadamente|cerca de)",
            r"(?i)(estimated|approx\.?|approximately|around)",
            r"(?i)(dados disponíveis indicam|based on available data)",
            r"(?i)(pode variar|may vary|subject to change)",
            r"(?i)(conforme|according to|de acordo com)",
        ]
        for p in hedge_patterns:
            if re.search(p, text):
                score += 10
        score = min(100, score)

        # Penalize hallucination-adjacent phrases
        bad_patterns = [
            r"(?i)(é sabido que|é fato que|obviamente|certamente|definitivamente)",
            r"(?i)(it is known that|it is a fact|obviously|certainly|definitely)\b",
        ]
        for p in bad_patterns:
            if re.search(p, text):
                score -= 20
        return max(0, score)

    def _score_numeric(self, text: str) -> int:
        score = 70  # baseline

        # Good: specific decimal values with units
        good = len(re.findall(r"(?:US\$|R\$)\s*[\d,.]+[KMBbi]?|\d+[,.]\d+\s*%", text, re.IGNORECASE))
        score += min(30, good * 10)

        # Bad: very large round numbers without unit context
        suspicious = re.findall(r"\b\d{9,}\b", text)
        for num in suspicious:
            context = text[max(0, text.find(num)-20):text.find(num)+30]
            if not re.search(r"(?:US\$|R\$|NCM|CNPJ|registro|código)", context, re.IGNORECASE):
                score -= 15

        # Bad: negative monetary values
        if re.search(r"(?:US\$|R\$)\s*-\d", text, re.IGNORECASE):
            score -= 20

        return max(0, min(100, score))

    def _detect_hallucination_flags(self, text: str) -> list:
        flags = []
        for pattern, label in HALLUCINATION_PATTERNS:
            if re.search(pattern, text):
                flags.append(label)
        return flags

    def _check_data_freshness_note(self, tool_calls: list, lang: str = "PT") -> str:
        tools = set(tool_calls)
        notes = []

        if tools & DELAYED_DATA_TOOLS:
            if lang == "EN":
                notes.append(
                    "\n\n---\n*Transparency note: Comex Stat data has up to 45-day lag "
                    "relative to MDIC publication date.*"
                )
            else:
                notes.append(
                    "\n\n---\n*Nota de transparência: Dados Comex Stat com defasagem de até 45 dias "
                    "em relação à data de publicação do MDIC.*"
                )

        if tools & ANVISA_TOOLS:
            if lang == "EN":
                notes.append(
                    "\n*ANVISA data extracted at last ETL pipeline run. "
                    "Run ETL for latest synchronization.*"
                )
            else:
                notes.append(
                    "\n*Dados ANVISA extraídos na última execução do Pipeline ETL. "
                    "Execute o ETL para sincronização mais recente.*"
                )

        return "".join(notes)

    # ------------------------------------------------------------------
    # Main audit method
    # ------------------------------------------------------------------

    def audit(
        self,
        text: str,
        tool_calls_made: list = None,
        module: str = "ai_output",
        lang: str = "PT",
    ) -> AuditResult:
        """
        Score an AI response and return an AuditResult.
        Blocks output if confidence < CONFIDENCE_BLOCK_THRESHOLD (60).
        """
        tool_calls_made = tool_calls_made or []

        s_length  = self._score_length(text)
        s_cite    = self._score_citations(text, tool_calls_made)
        s_hedge   = self._score_hedging(text)
        s_numeric = self._score_numeric(text)

        confidence = round(
            s_length  * (WEIGHT_LENGTH   / 100) +
            s_cite    * (WEIGHT_CITATIONS / 100) +
            s_hedge   * (WEIGHT_HEDGING  / 100) +
            s_numeric * (WEIGHT_NUMERIC  / 100)
        )
        confidence = max(0, min(100, confidence))

        flags = self._detect_hallucination_flags(text)

        if confidence < 40 or any("critical" in f for f in flags):
            risk_level: RiskLevel = "critical"
        elif confidence < 60:
            risk_level = "medium"
        else:
            risk_level = "low"

        blocked = confidence < CONFIDENCE_BLOCK_THRESHOLD

        transparency_note = self._check_data_freshness_note(tool_calls_made, lang=lang)

        if blocked:
            if lang == "EN":
                audited_text = (
                    "⚠️ **Response blocked by quality control.**\n\n"
                    "The generated response did not meet the minimum confidence threshold (60/100). "
                    "Please rephrase your question with more specific details.\n\n"
                    f"*Confidence score: {confidence}/100 · Risk level: {risk_level}*"
                )
            else:
                audited_text = (
                    "⚠️ **Resposta bloqueada pelo controle de qualidade.**\n\n"
                    "A resposta gerada não atingiu o limiar mínimo de confiança (60/100). "
                    "Tente reformular a pergunta com mais detalhes específicos.\n\n"
                    f"*Score de confiança: {confidence}/100 · Nível de risco: {risk_level}*"
                )
        else:
            audited_text = text + transparency_note

        return AuditResult(
            confidence_score=confidence,
            risk_level=risk_level,
            blocked=blocked,
            flags=flags,
            transparency_note=transparency_note,
            original_text=text,
            audited_text=audited_text,
        )
