"""Nó `normalizar` — Módulo 2 (Normalização), docs/arquitetura.md.

Função pura: recebe o estado, devolve só os campos que muda. Não depende do
contexto do grafo (não consulta a base) — só reconstrói a forma canônica do
identificador, essencial para o Nível 2 (Plano_de_acao.docx §3.2).
"""

from __future__ import annotations

from citacoes.dominio.campos import CamposIdentificador, extrair_campos
from citacoes.grafo.estados import EstadoCitacao


def normalizar(estado: EstadoCitacao) -> dict:
    """`tem_identificador=False` -> não força uma tentativa de busca
    (docs/contratos.md, invariante da fronteira 2->3)."""
    if not estado.tem_identificador:
        return {"campos": CamposIdentificador(), "ocr_corrigido": False}
    campos, ocr_corrigido = extrair_campos(estado.trecho, estado.tipo_bruto)
    return {"campos": campos, "ocr_corrigido": ocr_corrigido}
