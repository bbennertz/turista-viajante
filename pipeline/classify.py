"""Classificador: extrai um vetor de features de cada local a partir do Google Places.

As 5 reviews do Google são poucas e quase todas elogios (~80% de 5 estrelas), então o
prompt manda usar também os metadados (nº de avaliações, nota, tipos, resumo editorial)
e declarar baixa confiança quando o texto não sustenta a conclusão.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from pipeline.llm import CLASSIFIER_MODEL, ask_json, get_llm

Category = Literal[
    "restaurante", "cafe_padaria", "bar", "mercado_feira", "praia", "trilha_parque",
    "mirante", "museu_galeria", "igreja_historico", "marco_arquitetonico",
    "passeio_atividade", "compras", "outro",
]

# duração típica (min) quando o modelo não informa algo plausível
DEFAULT_DURATION = {
    "restaurante": 75, "cafe_padaria": 40, "bar": 60, "mercado_feira": 60, "praia": 120,
    "trilha_parque": 90, "mirante": 30, "museu_galeria": 75, "igreja_historico": 30,
    "marco_arquitetonico": 30, "passeio_atividade": 120, "compras": 45, "outro": 45,
}


class Features(BaseModel):
    category: Category
    is_dining: bool = Field(
        description="true só se for lugar para uma REFEIÇÃO completa (almoço/jantar): "
        "restaurante, boteco com comida, barraca de frutos do mar. Café, padaria, sorveteria, "
        "bar sem comida e mercado sem refeições = false."
    )
    is_paid: bool = Field(description="true se há ingresso/entrada paga (não conta consumir comida)")
    est_price_brl: float | None = Field(
        default=None, description="Ingresso por pessoa em R$ se is_paid e houver evidência; senão null"
    )
    duration_min: int = Field(description="Tempo típico de visita em minutos")
    setting: Literal["indoor", "outdoor", "mixed"]
    authenticity: float = Field(ge=0, le=1, description="Frequentado por moradores, tradicional, feito para quem é de lá")
    touristy: float = Field(ge=0, le=1, description="Voltado ao turista: multidão, preço inflado, souvenir, 'armadilha'")
    gastronomy: float = Field(ge=0, le=1, description="A comida/bebida É a experiência")
    culture: float = Field(ge=0, le=1, description="Valor histórico, artístico ou cultural")
    nature: float = Field(ge=0, le=1, description="Experiência de natureza/ar livre (praia, trilha, parque, vista)")
    landmark: float = Field(ge=0, le=1, description="Cartão-postal que quem visita a cidade pela primeira vez espera ver")
    evidence: list[str] = Field(
        description="1 a 3 trechos CURTOS (<=120 caracteres) das reviews/resumo que justificam as notas", max_length=3
    )
    confidence: Literal["baixa", "media", "alta"] = Field(
        description="baixa se as reviews não sustentam autenticidade/turistão"
    )

    @field_validator("evidence")
    @classmethod
    def _trim(cls, v: list[str]) -> list[str]:
        return [s[:160] for s in v]


SYSTEM = (
    "Você analisa lugares de uma cidade para um roteirizador turístico. A partir dos dados "
    "do Google (tipos, nota, nº de avaliações, resumo editorial e até 5 reviews), preencha o vetor "
    "de features. Regras: (1) baseie-se em evidências; as reviews são poucas e quase sempre elogios, "
    "então use também o nº de avaliações (muitas = mais turístico; poucas, em português e sem menção "
    "a turistas = mais local) e os tipos. (2) Se o texto não sustenta uma conclusão, use valores "
    "moderados e confidence='baixa'. (3) Notas de 0 a 1: não coloque tudo em 0.9. Um lugar pode ter "
    "authenticity e touristy altos ao mesmo tempo. (4) Não invente preço: est_price_brl=null sem evidência.\n\n"
    "ÂNCORAS (use a escala inteira; a maioria dos lugares comuns fica entre 0.1 e 0.4 na maioria das notas):\n"
    "- landmark: 0.9 = ícone inconfundível que todo guia cita (ex.: a ponte-símbolo da cidade); "
    "0.5 = conhecido na região; 0.2 = lugar comum de bairro. Museus, cafés, lojas e galerias pequenos "
    "(menos de ~500 avaliações) quase nunca passam de 0.3. Uma praia comum não é marco por ser praia.\n"
    "- touristy: 0.9 = feito para turista (souvenir, multidão, preço inflado); 0.5 = misto; "
    "0.1 = clientela de moradores, preço de bairro. Poucas avaliações e preço acessível indicam local.\n"
    "- authenticity: 0.9 = tradicional, único do lugar, frequentado por moradores; 0.2 = franquia ou genérico.\n"
    "- culture: 0.9 = patrimônio/museu/arquitetura relevante; 0.1 = sem valor cultural próprio.\n"
    "- nature: 0.9 = a experiência é a natureza (praia, trilha, vista); 0.0 = ambiente fechado urbano.\n"
    "- gastronomy: 0.9 = a comida/bebida é o motivo da visita; 0.0 = não se come lá."
)


# Contrato compacto: o JSON Schema completo custava ~650 tokens por chamada e o limite
# da Groq grátis é 8.000 tokens/min. Um teste garante que cobre todos os campos de Features.
CONTRACT = (
    "Responda APENAS com um objeto JSON com estas chaves:\n"
    "category: uma de [" + ", ".join(DEFAULT_DURATION) + "]\n"
    "is_dining: bool (true só para REFEIÇÃO completa: restaurante, boteco com comida, barraca de "
    "frutos do mar; café, padaria, sorveteria, bar sem comida = false)\n"
    "is_paid: bool (ingresso/entrada paga; consumir comida não conta)\n"
    "est_price_brl: número ou null (ingresso por pessoa, só com evidência)\n"
    "duration_min: inteiro (minutos típicos de visita)\n"
    'setting: "indoor" | "outdoor" | "mixed"\n'
    "authenticity, touristy, gastronomy, culture, nature, landmark: números de 0 a 1\n"
    "evidence: lista de 1 a 3 trechos curtos (até 120 caracteres) das reviews/resumo\n"
    'confidence: "baixa" | "media" | "alta" (baixa se o texto não sustenta autenticidade/turistão)'
)


def build_prompt(search: dict, details: dict) -> str:
    reviews = [
        f"- ({r.get('rating')}★) {(r.get('text') or {}).get('text', '')[:300]}"
        for r in details.get("reviews", [])
    ]
    price = search.get("priceLevel") or details.get("priceLevel") or "desconhecido"
    return "\n".join(
        [
            f"Nome: {(details.get('displayName') or search.get('displayName') or {}).get('text')}",
            f"Tipo principal: {search.get('primaryType')} | tipos: {', '.join(search.get('types', []))}",
            f"Nota: {search.get('rating')} | nº de avaliações: {search.get('userRatingCount')} | faixa de preço: {price}",
            f"Resumo editorial: {(details.get('editorialSummary') or {}).get('text', '(nenhum)')}",
            "Reviews:",
            *reviews,
        ]
    )


def classify_place(llm, search: dict, details: dict) -> Features:
    f = ask_json(llm, Features, SYSTEM, build_prompt(search, details), contract=CONTRACT)
    if not 10 <= f.duration_min <= 480:  # implausível: cai no padrão da categoria
        f.duration_min = DEFAULT_DURATION[f.category]
    if not f.is_paid:
        f.est_price_brl = None
    return f


def classify_all(
    city_dir: Path, model: str = CLASSIFIER_MODEL, limit: int | None = None, llm=None
) -> dict:
    """Resumível: grava classified/<id>.json por local e pula os que já existem."""
    llm = llm or get_llm(model)
    out = city_dir / "classified"
    out.mkdir(exist_ok=True)
    searches = {p["id"]: p for p in json.loads((city_dir / "candidates.json").read_text(encoding="utf-8"))}
    counts = {"done": 0, "skipped": 0, "failed": 0}
    for pid, search in list(searches.items())[: limit or None]:
        target = out / f"{pid}.json"
        if target.exists():
            counts["skipped"] += 1
            continue
        details = json.loads((city_dir / "details" / f"{pid}.json").read_text(encoding="utf-8"))
        try:
            feats = classify_place(llm, search, details)
        except Exception as e:  # um local ruim não derruba o lote
            counts["failed"] += 1
            print(f"falhou {pid}: {str(e)[:150]}")
            continue
        target.write_text(feats.model_dump_json(indent=1), encoding="utf-8")
        counts["done"] += 1
    return counts
