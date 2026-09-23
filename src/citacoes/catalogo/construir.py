"""Construção offline do catálogo canônico a partir de `desafio1_bracis.db`.

Roda uma vez (fora do grafo, catalogo/README.md); o resultado é carregado
no `Contexto` do grafo por `carregar.py`. Esquema de `documentos` confirmado
em Analise_Exploratoria.docx §b: documento_id, id, tribunal, ano, relator,
natureza (acordao|sumula|dispositivo), tipo (jurisprudencia|lei), texto.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from citacoes.catalogo.esquema import CatalogoCanonico, RegistroCatalogo
from citacoes.dominio.cabecalho import extrair_cabecalho
from citacoes.dominio.campos import CamposIdentificador, extrair_campos

_COLUNAS = "documento_id, id, tribunal, ano, relator, natureza, tipo, texto"

# Os 13 dispositivos de lei da base real citam só o próprio artigo — o nome
# do diploma nunca aparece no corpo do texto (conferido nos 13 registros de
# desafio1_bracis.db). O que `diploma_legal` acha ali (quando acha) é
# sempre menção incidental a outro diploma no corpo do artigo, nunca o
# diploma do próprio artigo — por isso este mapeamento (um por um contra o
# texto de cada registro e contra a citação correspondente no goldenset,
# RELATORIO_MODULO4.md §6.7) sempre prevalece sobre `extrair_campos`.
_DIPLOMA_DISPOSITIVOS: dict[int, str] = {
    10577194: "CE",  # Art. 276 do Código Eleitoral
    10590194: "CPM",  # Art. 290 do Código Penal Militar
    10606184: "CDC",  # Art. 14 do Código de Defesa do Consumidor
    10626510: "CF",  # Art. 93 da Constituição Federal
    10637358: "CLT",  # Art. 896 da CLT
    10641213: "CF",  # Art. 7º da Constituição Federal
    10641516: "CF",  # Art. 5º da Constituição Federal
    10647746: "CLT",  # Art. 818 da CLT
    10652044: "CPP",  # Art. 312 do Código de Processo Penal
    10710324: "CLT",  # Art. 477 da CLT
    10718759: "CC",  # Art. 186 do Código Civil
    11304039: "LC64",  # Art. 1º da LC 64/1990 (Lei das Inelegibilidades)
    28893055: "CPC",  # Art. 373 do CPC
}


def _linhas(conexao: sqlite3.Connection) -> Iterator[sqlite3.Row]:
    conexao.row_factory = sqlite3.Row
    yield from conexao.execute(f"SELECT {_COLUNAS} FROM documentos")


def construir_registro(linha: sqlite3.Row) -> RegistroCatalogo:
    """Extrai só o identificador **próprio** do registro (cabeçalho) — nunca
    um número que o documento apenas cite no corpo (catalogo/README.md)."""
    cabecalho = extrair_cabecalho(linha["texto"])
    tipo_bruto = "lei" if linha["tipo"] == "lei" else "jurisprudencia"
    campos, _ = extrair_campos(cabecalho, tipo_bruto)
    if linha["natureza"] == "dispositivo":
        diploma_conhecido = _DIPLOMA_DISPOSITIVOS.get(linha["id"])
        # Sobrescreve mesmo quando `extrair_campos` achou algo: o nome do
        # diploma nunca é o próprio artigo, então qualquer diploma "achado"
        # no corpo de um destes 13 registros é falso positivo (ex.: id
        # 11304039 — art. 1º da LC 64/1990 — bate com "Constituição
        # Federal" só porque o texto discute fundamento constitucional da
        # inelegibilidade, não porque é dela).
        if diploma_conhecido is not None:
            campos = replace(campos, diploma=diploma_conhecido)
    return RegistroCatalogo(
        id=linha["id"],
        documento_id=linha["documento_id"],
        natureza=linha["natureza"],
        tipo=linha["tipo"],
        tribunal=linha["tribunal"],
        ano=linha["ano"],
        relator=linha["relator"],
        campos=campos,
        hash_texto=hashlib.sha1(linha["texto"].encode("utf-8")).hexdigest(),
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
        "hash_texto": registro.hash_texto,
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
        hash_texto=dados.get("hash_texto"),
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
