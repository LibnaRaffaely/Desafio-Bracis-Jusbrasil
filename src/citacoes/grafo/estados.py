"""Estados e contexto do grafo — ver docs/contratos.md.

Só os campos que os nós já implementados (`normalizar`,
`buscar_no_catalogo`) leem ou escrevem têm um valor "real" por padrão; os
campos dos demais módulos (extração, decisão, calibração) ficam com
default neutro e são preenchidos pelos nós correspondentes — cada nó
devolve só o que mudou (docs/arquitetura.md).
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Literal

from citacoes.catalogo.esquema import Candidato, CatalogoCanonico
from citacoes.dominio.campos import CamposIdentificador

TipoBruto = Literal["jurisprudencia", "lei", "indefinido"]
OrigemSpan = Literal["regex_camada1", "heuristica_camada2", "agente_extrator_llm"]
MetodoBusca = Literal["catalogo", "lei_sumula", "sem_busca"]





@dataclass
class EstadoDocumento:
    documento_id: str = ""
    texto: str = ""
    spans: list[EstadoCitacao] = field(default_factory=list)
    citacoes: Annotated[list[EstadoCitacao], operator.add] = field(default_factory=list)
    saida: dict | None = None

@dataclass
class EstadoCitacao:
    """Um span candidato percorrendo o subgrafo da citação."""

    inicio: int
    fim: int
    trecho: str
    tipo_bruto: TipoBruto
    tem_identificador: bool
    origem: OrigemSpan
    campos: CamposIdentificador | None = None
    ocr_corrigido: bool = False
    candidatos: list[Candidato] = field(default_factory=list)
    metodo_busca: MetodoBusca | None = None
    classificacao: str | None = None
    id_canonico: int | None = None
    tipo: str | None = None
    metodo_decisao: str | None = None
    confianca: float | None = None


@dataclass
class Contexto:
    """Contexto compartilhado, somente leitura — lido via `runtime.context`,
    nunca copiado para o estado (docs/arquitetura.md)."""

    catalogo: CatalogoCanonico | None = None
    tabela_confianca: dict | None = None
    modelo_llm: object | None = None
    usar_extrator_llm: bool = False
    usar_parser_llm: bool = False
    usar_juiz: bool = False
