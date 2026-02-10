"""LLM client abstraction: OpenAI-compatible API or Ollama local.

Author: Armand Amoussou
"""

from __future__ import annotations

import json
from typing import Any

from app.observability.logger import get_logger

logger = get_logger("llm_client")

# --- Exact prompts for the Financial Scorer agent ---

FINANCIAL_SCORER_SYSTEM_PROMPT = """\
You are a financial risk assessment engine. Your sole function is to analyze \
provided evidence about a supplier and produce a structured JSON risk score.

ABSOLUTE RULES:
1. Output ONLY valid JSON matching the required schema. No prose, no markdown.
2. NEVER invent, fabricate, or hallucinate any source, fact, URL, or data point.
3. Every claim in risk_drivers MUST be supported by at least one evidence_item.
4. If you cannot find sufficient evidence, set financial_risk_level to \
INDETERMINATE, confidence <= 0.4, and list specific data_gaps.
5. evidence_items MUST contain 1 to 7 items. Each excerpt max 240 chars.
6. notes field max 400 chars.
7. financial_risk_score MUST be an integer in [0, 100].
8. confidence MUST be a float in [0.0, 1.0].
9. Use ONLY the evidence provided in the USER message. Do not access external data.
10. Do not include any text outside the JSON object.\
"""

FINANCIAL_SCORER_DEVELOPER_PROMPT = """\
SCORING POLICY:
- Base score: 50
- Adjustments (cumulative):
  - Payment default / insolvency / collective proceedings: +30 to +50
  - Liquidity stress / excessive debt / difficult refinancing: +10 to +25
  - Recent significant downgrade (rating/outlook): +10 to +25
  - Notable improvement / confirmed multi-period stability: -5 to -15
- Contradictions or weak data => financial_risk_level = INDETERMINATE

CONFIDENCE SCORING:
- confidence reflects quality, quantity, recency, and coherence of evidence
- 3+ recent, coherent official sources: confidence >= 0.7
- 1-2 sources or older data: confidence 0.4-0.7
- No usable evidence: confidence <= 0.4

CANONICAL RISK DRIVERS (use these exact strings when applicable):
- PAYMENT_DEFAULT
- INSOLVENCY
- PROCEEDING
- BANKRUPTCY
- LIQUIDATION
- DEBT_STRESS
- LIQUIDITY_RISK
- RATING_DOWNGRADE
- REGULATORY_ACTION
- GEOPOLITICAL_RISK
- ENVIRONMENTAL_RISK
- OPERATIONAL_DISRUPTION
- STABLE_POSITIVE

OUTPUT FORMAT:
{
  "supplier_id": "<from input>",
  "as_of_date": "<from input>",
  "financial_risk_score": <int 0-100>,
  "financial_risk_level": "<LOW|MEDIUM|HIGH|INDETERMINATE>",
  "confidence": <float 0.0-1.0>,
  "risk_drivers": ["<CANONICAL_DRIVER>"],
  "recommended_actions": ["<action string>"],
  "data_gaps": ["<gap description>"],
  "evidence_items": [
    {
      "source": "<OFFICIAL_WEB|INTERNAL_GOLDEN>",
      "url": "<source url>",
      "doc_id": "<document identifier>",
      "field": "<data field name>",
      "excerpt": "<max 240 chars>",
      "content_hash": "<sha256>",
      "observed_at": "<YYYY-MM-DD>"
    }
  ],
  "notes": "<max 400 chars>"
}

INDETERMINATE RULE:
If evidence_items is empty or all sources are unreliable:
- financial_risk_level = "INDETERMINATE"
- confidence <= 0.4
- data_gaps MUST be non-empty
- financial_risk_score = 50 (base, no adjustment)\
"""

FINANCIAL_SCORER_USER_TEMPLATE = """\
Analyze the following supplier for financial risk.

SUPPLIER:
- supplier_id: {supplier_id}
- name: {supplier_name}
- country: {country}
- sector/category: {category}
- as_of_date: {as_of_date}

COLLECTED EVIDENCE (official web extracts):
{evidence_text}

Produce the JSON risk assessment now.\
"""


class LLMClient:
    """Unified LLM client supporting OpenAI-compatible and Ollama backends."""

    def __init__(
        self,
        provider: str = "openai",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "llama3.1:8b",
    ) -> None:
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self._client = None
        self.total_tokens_used = 0
        self.total_calls = 0

    def _get_openai_client(self) -> Any:  # noqa: ANN401
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def call(
        self,
        system_prompt: str,
        developer_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        """Call the LLM and return parsed JSON response.

        Returns: {"content": str, "parsed_json": dict|None, "tokens_used": int}
        """
        if self.provider == "openai":
            return self._call_openai(
                system_prompt, developer_prompt, user_prompt, temperature, max_tokens
            )
        elif self.provider == "ollama":
            return self._call_ollama(
                system_prompt, developer_prompt, user_prompt, temperature, max_tokens
            )
        else:
            msg = f"Unknown LLM provider: {self.provider}"
            raise ValueError(msg)

    def _call_openai(
        self,
        system_prompt: str,
        developer_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        client = self._get_openai_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            self.total_tokens_used += tokens
            self.total_calls += 1

            parsed = self._try_parse_json(content)
            logger.info(
                "llm_call_ok",
                provider="openai",
                model=self.model,
                tokens=tokens,
            )
            return {"content": content, "parsed_json": parsed, "tokens_used": tokens}
        except Exception as e:
            logger.error("llm_call_error", provider="openai", error=str(e))
            return {"content": "", "parsed_json": None, "tokens_used": 0}

    def _call_ollama(
        self,
        system_prompt: str,
        developer_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        try:
            import ollama as ollama_lib

            messages = [
                {"role": "system", "content": system_prompt + "\n\n" + developer_prompt},
                {"role": "user", "content": user_prompt},
            ]
            response = ollama_lib.chat(
                model=self.ollama_model,
                messages=messages,
                options={"temperature": temperature, "num_predict": max_tokens},
            )
            content = response.get("message", {}).get("content", "")
            self.total_calls += 1

            parsed = self._try_parse_json(content)
            logger.info("llm_call_ok", provider="ollama", model=self.ollama_model)
            return {"content": content, "parsed_json": parsed, "tokens_used": 0}
        except Exception as e:
            logger.error("llm_call_error", provider="ollama", error=str(e))
            return {"content": "", "parsed_json": None, "tokens_used": 0}

    @staticmethod
    def _try_parse_json(content: str) -> dict[str, Any] | None:
        """Attempt to parse JSON from LLM response."""
        content = content.strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines)
        try:
            return json.loads(content)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(content[start:end])  # type: ignore[no-any-return]
                except json.JSONDecodeError:
                    pass
            return None

    def estimate_cost(self) -> float:
        """Rough cost estimate based on tokens used (OpenAI pricing approximation)."""
        # Approximate: $0.15 per 1M input tokens, $0.60 per 1M output tokens
        # Simplified: ~$0.001 per 1K tokens average
        return self.total_tokens_used * 0.000001
