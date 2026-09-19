"""Construção offline do catálogo canônico a partir de `desafio1_bracis.db`.

Roda uma vez (fora do grafo, catalogo/README.md); o resultado é carregado
no `Contexto` do grafo por `carregar.py`. Esquema de `documentos` confirmado
em Analise_Exploratoria.docx §b: documento_id, id, tribunal, ano, relator,
natureza (acordao|sumula|dispositivo), tipo (jurisprudencia|lei), texto.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from citacoes.catalogo.esquema import CatalogoCanonico, RegistroCatalogo
from citacoes.dominio.cabecalho import extrair_cabecalho
from citacoes.dominio.campos import CamposIdentificador, extrair_campos

_COLUNAS = "documento_id, id, tribunal, ano, relator, natureza, tipo, texto"


def _linhas(conexao: sqlite3.Connection) -> Iterator[sqlite3.Row]:
    conexao.row_factory = sqlite3.Row
    yield from conexao.execute(f"SELECT {_COLUNAS} FROM documentos")


def construir_registro(linha: sqlite3.Row) -> RegistroCatalogo:
    """Extrai só o identificador **próprio** do registro (cabeçalho) — nunca
    um número que o documento apenas cite no corpo (catalogo/README.md)."""
    cabecalho = extrair_cabecalho(linha["texto"])
    tipo_bruto = "lei" if linha["tipo"] == "lei" else "jurisprudencia"
    campos, _ = extrair_campos(cabecalho, tipo_bruto)
    return RegistroCatalogo(
        id=linha["id"],
        documento_id=linha["documento_id"],
        natureza=linha["natureza"],
        tipo=linha["tipo"],
        tribunal=linha["tribunal"],
        ano=linha["ano"],
        relator=linha["relator"],
        campos=campos,
    )


def construir_catalogo(conexao: sqlite3.Connection) -> CatalogoCanonico:
    """Lê `documentos` inteira e monta o catálogo em memória.

    Súmulas e dispositivos de lei (18 registros: 13 + 5) vão para
    `leis_sumulas`, casados por matching de texto — mesmo a súmula tendo
    `tipo="jurisprudencia"` no banco, o número curto colide demais com o
    índice de dígitos usado pelos acórdãos (Plano_de_acao.docx §3.3).
    """
    registros = [construir_registro(linha) for linha in _linhas(conexao)]
    por_chave: dict[str, list[RegistroCatalogo]] = defaultdict(list)
    leis_sumulas: list[RegistroCatalogo] = []
    for registro in registros:
        if registro.natureza in ("sumula", "dispositivo"):
            leis_sumulas.append(registro)
        elif registro.campos.numero_normalizado:
            por_chave[registro.campos.numero_normalizado].append(registro)
    return CatalogoCanonico(
        registros=registros, por_chave=dict(por_chave), leis_sumulas=leis_sumulas
    )


def construir_catalogo_de_arquivo(caminho_db: Path | str) -> CatalogoCanonico:
    conexao = sqlite3.connect(f"file:{caminho_db}?mode=ro", uri=True)
    try:
        return construir_catalogo(conexao)
    finally:
        conexao.close()


def _campos_para_dict(campos: CamposIdentificador) -> dict[str, Any]:
    return asdict(campos)


def _campos_de_dict(dados: dict[str, Any]) -> CamposIdentificador:
    dados = dict(dados)
    dados["classes_compostas"] = tuple(dados.get("classes_compostas", ()))
    dados["variantes_texto"] = tuple(dados.get("variantes_texto", ()))
    return CamposIdentificador(**dados)


def _registro_para_dict(registro: RegistroCatalogo) -> dict[str, Any]:
    return {
        "id": registro.id,
        "documento_id": registro.documento_id,
        "natureza": registro.natureza,
        "tipo": registro.tipo,
        "tribunal": registro.tribunal,
        "ano": registro.ano,
        "relator": registro.relator,
        "campos": _campos_para_dict(registro.campos),
    }


def _registro_de_dict(dados: dict[str, Any]) -> RegistroCatalogo:
    return RegistroCatalogo(
        id=dados["id"],
        documento_id=dados["documento_id"],
        natureza=dados["natureza"],
        tipo=dados["tipo"],
        tribunal=dados["tribunal"],
        ano=dados["ano"],
        relator=dados["relator"],
        campos=_campos_de_dict(dados["campos"]),
    )


def salvar(catalogo: CatalogoCanonico, caminho: Path | str) -> None:
    """Serializa o catálogo em JSON — saída em `artifacts/`, fora do git
    (catalogo/README.md)."""
    dados = {
        "registros": [_registro_para_dict(r) for r in catalogo.registros],
    }
    Path(caminho).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar(caminho: Path | str) -> CatalogoCanonico:
    """Reconstrói o `CatalogoCanonico` a partir do artefato salvo por
    `salvar` — reconstrói os índices em vez de serializá-los, para que o
    formato do arquivo não precise mudar se a regra de indexação mudar."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    registros = [_registro_de_dict(r) for r in dados["registros"]]
    por_chave: dict[str, list[RegistroCatalogo]] = defaultdict(list)
    leis_sumulas: list[RegistroCatalogo] = []
    for registro in registros:
        if registro.natureza in ("sumula", "dispositivo"):
            leis_sumulas.append(registro)
        elif registro.campos.numero_normalizado:
            por_chave[registro.campos.numero_normalizado].append(registro)
    return CatalogoCanonico(
        registros=registros, por_chave=dict(por_chave), leis_sumulas=leis_sumulas
    )


def relatorio_colisoes_texto(catalogo: CatalogoCanonico) -> str:
    """Relatório de colisões legível (chaves que apontam para 2+ registros)."""
    colisoes = catalogo.relatorio_colisoes()
    if not colisoes:
        return "nenhuma colisão"
    linhas = [f"{chave}: ids {ids}" for chave, ids in sorted(colisoes.items())]
    return "\n".join(linhas)
