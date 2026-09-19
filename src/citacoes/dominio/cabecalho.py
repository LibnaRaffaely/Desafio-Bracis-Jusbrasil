"""Reconhecimento estrutural do cabeçalho de um documento (Arquitetura.md).

Usado por `catalogo/construir.py` para isolar, em cada registro da base, só
o identificador **próprio** daquele documento — nunca um número que o
documento apenas cite no corpo (ver catalogo/README.md). O Módulo 1
(extração, fora do escopo deste módulo) usa a mesma função para o filtro de
distratores no documento de entrada.
"""

from __future__ import annotations

import re

_QUEBRA_DUPLA = re.compile(r"\r?\n[ \t]*\r?\n")
_ROTULO_PROCESSO = re.compile(r"processo\s*n[º°o]", re.IGNORECASE)


def extrair_cabecalho(texto: str) -> str:
    """Bloco inicial até a primeira quebra dupla de linha, ou até o fim da
    linha do rótulo "Processo nº" se não houver quebra dupla (documento sem
    parágrafos separados)."""
    m = _QUEBRA_DUPLA.search(texto)
    if m:
        return texto[: m.start()]
    m_rotulo = _ROTULO_PROCESSO.search(texto)
    if m_rotulo:
        fim_linha = texto.find("\n", m_rotulo.end())
        return texto[: fim_linha if fim_linha != -1 else len(texto)]
    return texto
