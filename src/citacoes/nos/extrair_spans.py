from __future__ import annotations
import re
from typing import TYPE_CHECKING
from citacoes.dominio.cabecalho import extrair_cabecalho
from citacoes.dominio.lexico import CLASSES_PROCESSUAIS, TRIBUNAIS
from citacoes.grafo.estados import EstadoCitacao, EstadoDocumento

if TYPE_CHECKING:
    from langgraph.runtime import Runtime
    from citacoes.grafo.estados import Contexto


##  --------------------Deduplicação por IoU--------------------------

def _iou(a: EstadoCitacao, b: EstadoCitacao) -> float:
    overlap = max(0, min(a.fim, b.fim) - max(a.inicio, b.inicio))
    union = max(a.fim, b.fim) - min(a.inicio, b.inicio)
    return overlap / union if union > 0 else 0.0


_PRIORIDADE = {"regex_camada1": 0, "heuristica_camada2": 1, "agente_extrator_llm": 2}


def _deduplicar(spans: list[EstadoCitacao]) -> list[EstadoCitacao]:
    """mantem so um span por região IoU >= 0.5 --> prioriza regex."""
    ordenados = sorted(spans, key=lambda s: _PRIORIDADE.get(s.origem, 99))
    mantidos: list[EstadoCitacao] = []
    for span in ordenados:
        if not any(_iou(span, k) >= 0.5 for k in mantidos):
            mantidos.append(span)
    return mantidos