"""Nó `calibrar` — Módulo 5 (Confiança), docs/arquitetura.md.

A métrica oficial dá um bônus de até 10% por calibração:
`score = s · (1 + 0,1 · (1 − Brier))`, com o Brier medido só nos pares
casados com o gabarito (`y = 1` se classe e id estão certos). Sem
confiança, o bônus é zero. Com confiança constante 1,0, o Brier vira a taxa
de erro. O valor que minimiza o Brier em cada grupo de citações é a taxa de
acerto desse grupo, e é isso que a tabela guarda.

`calibrar` é a lógica pura; `calibrar_confianca` é o nó do grafo. A tabela
vem de `params/tabela_confianca.json` via `Contexto.tabela_confianca` e é
ajustada por `scripts/ajustar_confianca.py` (formato em params/README.md).
A chave da faixa é o par `metodo_decisao|metodo_busca`, com recuo para só
`metodo_decisao` e depois para `padrao`. Os dois sinais são escritos pelos
Módulos 3 e 4, então a confiança nunca muda a classe nem o id.

Sem tabela, a confiança fica `None` (vira `-` no CSV): o nó não inventa
valores que não foram medidos.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from citacoes.grafo.estados import Contexto, EstadoCitacao

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

SEM_VALOR = "-"


def chave_faixa(metodo_decisao: str | None, metodo_busca: str | None) -> str:
    """Chave fina da tabela. É a mesma função no ajuste e na inferência, para
    as duas pontas nunca divergirem."""
    return f"{metodo_decisao or SEM_VALOR}|{metodo_busca or SEM_VALOR}"


def _limitar(valor: float) -> float:
    return min(1.0, max(0.0, float(valor)))


def confianca_da_tabela(
    tabela: Mapping, metodo_decisao: str | None, metodo_busca: str | None
) -> float | None:
    """Procura a faixa mais específica que existe na tabela."""
    faixas = tabela.get("faixas", {})
    por_decisao = tabela.get("por_metodo_decisao", {})
    fina = faixas.get(chave_faixa(metodo_decisao, metodo_busca))
    if fina is not None:
        return _limitar(fina["confianca"])
    grossa = por_decisao.get(metodo_decisao or SEM_VALOR)
    if grossa is not None:
        return _limitar(grossa["confianca"])
    padrao = tabela.get("padrao")
    return None if padrao is None else _limitar(padrao)


def calibrar(estado: EstadoCitacao, tabela: Mapping | None) -> dict:
    if not tabela:
        return {"confianca": None}
    return {"confianca": confianca_da_tabela(tabela, estado.metodo_decisao, estado.metodo_busca)}


def calibrar_confianca(estado: EstadoCitacao, runtime: Runtime[Contexto]) -> dict:
    """Nó do grafo. Lê só `tabela_confianca` do contexto."""
    return calibrar(estado, runtime.context.tabela_confianca)
