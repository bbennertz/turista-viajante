"""Acesso ao LLM (open-weight via Groq) com saída JSON validada por Pydantic."""

from __future__ import annotations

import json
import os
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, ValidationError

from pipeline.env import load_env, require

T = TypeVar("T", bound=BaseModel)

AGENT_MODEL = "openai/gpt-oss-120b"
CLASSIFIER_MODEL = "openai/gpt-oss-20b"
JUDGE_MODEL = "openai/gpt-oss-120b"  # diferente e maior que o classificador


def get_llm(model: str | None = None, temperature: float = 0.0) -> ChatGroq:
    load_env()
    return ChatGroq(
        model=model or os.environ.get("LLM_MODEL", AGENT_MODEL),
        api_key=require("GROQ_API_KEY"),
        temperature=temperature,
        reasoning_effort="low",
        model_kwargs={"response_format": {"type": "json_object"}},
        max_retries=3,
    )


def ask_json(
    llm, schema: type[T], system: str, user: str, retries: int = 1, contract: str | None = None
) -> T:
    """Pede JSON conforme `schema`; em caso de JSON/validação inválidos, reenvia o erro ao modelo.

    `contract` substitui o JSON Schema completo por uma descrição compacta (poupa tokens)."""
    contract = contract or (
        "Responda APENAS com um objeto JSON que siga este JSON Schema:\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )
    messages = [SystemMessage(system + "\n\n" + contract), HumanMessage(user)]
    last_error = ""
    for _ in range(retries + 1):
        reply = llm.invoke(messages).content
        try:
            return schema.model_validate_json(reply)
        except (ValidationError, ValueError) as e:
            last_error = str(e)[:500]
            messages += [
                HumanMessage(f"Sua resposta foi inválida: {last_error}\nCorrija e responda só com o JSON.")
            ]
    raise ValueError(f"LLM não produziu JSON válido: {last_error}")
