"""Fixtures compartilhadas — base sintética no esquema de desafio1_bracis.db
(colunas confirmadas em Analise_Exploratoria.docx §b). Testes não usam os
dados reais da competição (tests/README.md)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

_DDL = """
CREATE TABLE documentos (
    documento_id TEXT PRIMARY KEY,
    id INTEGER,
    tribunal TEXT,
    ano INTEGER,
    relator TEXT,
    natureza TEXT,
    tipo TEXT,
    texto TEXT
)
"""

_LINHAS = [
    (
        "doc_0893",
        5665364632,
        "STM",
        2023,
        "Fulano de Tal",
        "acordao",
        "jurisprudencia",
        "APL 7000449-40.2023.7.00.0000/RS\n\nRelator: Fulano de Tal. "
        "Acordam os Ministros do STM, por unanimidade...",
    ),
    (
        "doc_1234",
        1111111111,
        "STJ",
        2020,
        "Beltrano",
        "acordao",
        "jurisprudencia",
        "REsp 1.307.026/BA\n\nRelator: Beltrano. Acordam os Ministros do STJ...",
    ),
    (
        "doc_sv45",
        900045,
        "STF",
        None,
        None,
        "sumula",
        "jurisprudencia",
        "Súmula Vinculante nº 45 do STF\n\nÉ vedado...",
    ),
    (
        "doc_s331",
        900331,
        "TST",
        None,
        None,
        "sumula",
        "jurisprudencia",
        "Súmula nº 331 do TST\n\nA contratação...",
    ),
    (
        "doc_cpc927",
        800927,
        None,
        None,
        None,
        "dispositivo",
        "lei",
        "art. 927 do Código de Processo Civil\n\nAquele que...",
    ),
]


@pytest.fixture
def conexao_documentos() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(":memory:")
    con.execute(_DDL)
    con.executemany("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?)", _LINHAS)
    con.commit()
    yield con
    con.close()
