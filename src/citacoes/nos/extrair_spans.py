from __future__ import annotations
import re
from typing import TYPE_CHECKING
from citacoes.dominio.cabecalho import extrair_cabecalho
from citacoes.dominio.lexico import CLASSES_PROCESSUAIS, TRIBUNAIS
from citacoes.grafo.estados import EstadoCitacao, EstadoDocumento