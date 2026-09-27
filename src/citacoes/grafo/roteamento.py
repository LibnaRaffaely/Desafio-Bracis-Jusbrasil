"""Funções de roteamento das arestas condicionais — docs/arquitetura.md
(mermaid "Visão geral"). Puras: leem o estado (e as flags do contexto) e
devolvem o nome do próximo nó ou a lista de `Send`. Regra de negócio não
entra aqui.

Arestas do mermaid que não viram função neste arquivo:

- `buscar_no_catalogo -> agente_juiz`: o juiz é um `Juiz` injetado dentro
  do nó `decidir` (`nos/decidir.py:decidir_classe`), que já aplica o
  critério de empate (2+ ids distintos sem conflito duro, depois dos
  desempates determinísticos). A aresta é fixa `buscar -> decidir`.
- `normalizar -> agente_parser`: não há agente parser nem critério de
  "parse falhou" no código. Com o parser desligado, span com identificador
  vai para `buscar_no_catalogo`, que devolve `sem_busca` quando os campos
  não são buscáveis — o caso que `decidir` trata como incompleta.
"""

from __future__ import annotations

from langgraph.runtime import Runtime
from langgraph.types import Send

from citacoes.grafo.estados import Contexto, EstadoCitacao, EstadoDocumento

NO_PROCESSAR_CITACAO = "processar_citacao"
NO_REUNIR = "reunir_e_formatar"


def distribuir(estado: EstadoDocumento) -> list[Send] | str:
    """Um `Send` por span. Sem spans a lista ficaria vazia e o grafo
    terminaria sem `reunir_e_formatar`; todo documento precisa de saída
    (docs/contratos.md, invariante da submissão), então vai direto para lá."""
    if not estado.spans:
        return NO_REUNIR
    return [Send(NO_PROCESSAR_CITACAO, span) for span in estado.spans]


def rota_apos_extrair(estado: EstadoDocumento, runtime: Runtime[Contexto]) -> list[Send] | str:
    if runtime.context.usar_extrator_llm:
        return "agente_extrator"
    return distribuir(estado)


def rota_apos_normalizar(estado: EstadoCitacao) -> str:
    """Sem identificador não há busca (docs/contratos.md: `tem_identificador`
    falso ⇒ sem busca e sem candidatos); `decidir` trata `metodo_busca=None`
    como `sem_identificador`."""
    if not estado.tem_identificador:
        return "decidir"
    return "buscar_no_catalogo"
