"""Construção offline do catálogo canônico a partir de `desafio1_bracis.db`.

Roda uma vez (fora do grafo, catalogo/README.md); o resultado é carregado
no `Contexto` do grafo por `carregar.py`. Esquema de `documentos` confirmado
em Analise_Exploratoria.docx §b: documento_id, id, tribunal, ano, relator,
natureza (acordao|sumula|dispositivo), tipo (jurisprudencia|lei), texto.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from citacoes.catalogo.esquema import CatalogoCanonico, RegistroCatalogo
from citacoes.dominio.cabecalho import extrair_cabecalho
from citacoes.dominio.campos import CamposIdentificador, extrair_campos
from citacoes.dominio.chave import corrigir_ocr_numerico, extrair_digitos

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


# ── número próprio dos acórdãos ─────────────────────────────────────────────
#
# O cabeçalho sozinho não basta (análise de 2026-09-27 na base atual):
#
# - TST: o texto abre com a ementa e o cabeçalho traz "LEI Nº 13.015/2014"
#   antes do número do processo, que só aparece na fórmula "Vistos,
#   relatados e discutidos estes autos de <classe> nº TST-<CNJ>" (195 dos
#   198 acórdãos do TST), depois do teto de 1000 caracteres do cabeçalho.
#   Sem esta regra, 80 acórdãos do TST ficavam sem número e ~110 ficavam com
#   o número de uma lei como chave.
# - TSE/STF: quando o cabeçalho menciona uma súmula, `extrair_campos` cai no
#   ramo de súmula e o acórdão perde o número de processo.
# - STJ/STF: classes com número de 4 dígitos ("SUSPENSÃO DE LIMINAR E DE
#   SENTENÇA Nº 2.883", "AÇÃO RESCISÓRIA 2.614") eram trocadas pelo número de
#   registro entre parênteses ou por uma data.
_LETRA_OU_DIGITO = r"[\dOoIlSs]"
_CNJ_CATALOGO = re.compile(
    rf"{_LETRA_OU_DIGITO}{{1,7}}\s?-\s?{_LETRA_OU_DIGITO}{{2}}\.\s?{_LETRA_OU_DIGITO}{{4}}"
    rf"\.\s?{_LETRA_OU_DIGITO}\.\s?{_LETRA_OU_DIGITO}{{2}}\.\s?{_LETRA_OU_DIGITO}{{4}}"
)
_AUTOS_TST = re.compile(
    r"(?:discutidos|examinados)\s+(?:estes|os\s+presentes|os)\s+autos\s+d[eo]s?\s"
    r"[^,]{0,250}?\bn[º°o]\.?\s*",
    re.IGNORECASE,
)
_PROCESSO_TST = re.compile(r"processo\s+n[º°o]\.?\s*(?=TST)", re.IGNORECASE)
_CADEIA = re.compile(r"\d(?:[\d.\-]*\d)?")
_LEI_ANTES = re.compile(r"\blei\s+(?:complementar\s+)?(?:n[º°o]\.?\s*)?$", re.IGNORECASE)
# "Nº 2.883", "N° 0606252-...", "N 0603354-..." (OCR sem o símbolo), "n. 2785".
_ROTULO_NUMERO = re.compile(r"(?<!\w)n(?:[º°o]|\.)?\.?[ \t]*(?=\d)", re.IGNORECASE)
# CNJ entre parênteses logo depois do número curto: "Nº 1.662 ( 47142-16...)".
_CNJ_ENTRE_PARENTESES = re.compile(r"\s*\(\s*")
_ANO = re.compile(r"(?:19|20)\d{2}")
_MINIMO_DIGITOS_PROPRIO = 4
_JANELA_SEM_ROTULO = 600


def _digitos_cnj(trecho: str) -> str | None:
    m = _CNJ_CATALOGO.search(trecho)
    if not m:
        return None
    digitos, _ = extrair_digitos(m.group(0))
    return digitos


def _numero_tst(texto: str) -> str | None:
    for rotulo in (_AUTOS_TST, _PROCESSO_TST):
        for m in rotulo.finditer(texto):
            numero = _digitos_cnj(texto[m.end() : m.end() + 80])
            if numero:
                return numero
    return _digitos_cnj(texto)


def _cadeia_valida(corrigido: str, m: re.Match[str]) -> str | None:
    """Dígitos de uma cadeia que pode ser número de processo: não é data nem
    número de registro (vizinha de "/" seguida de dígito), não é número de
    lei, não está colada a letras (OAB "DF011498") e não é um ano solto."""
    antes = corrigido[m.start() - 1 : m.start()]
    depois = corrigido[m.end() : m.end() + 2]
    # "/RS" depois do número é UF; "/2019" ou "2016/0213994" é data ou registro.
    if antes == "/" or (depois[:1] == "/" and depois[1:2].isdigit()):
        return None
    if antes.isalpha() or depois[:1].isalpha():
        return None
    if _LEI_ANTES.search(corrigido[max(0, m.start() - 30) : m.start()]):
        return None
    if _ANO.fullmatch(m.group(0)):
        return None
    digitos = "".join(c for c in m.group(0) if c.isdigit())
    return digitos if len(digitos) >= _MINIMO_DIGITOS_PROPRIO else None


def _numeros_do_rotulo(corrigido: str, limite: int) -> tuple[str, ...]:
    """Número logo depois do primeiro rótulo "Nº" que não seja de lei e que
    venha antes de `limite` (a posição da primeira cadeia válida). Se o
    rótulo abre um CNJ, o CNJ inteiro; se um CNJ vem entre parênteses logo
    depois do número, ele entra como segundo número do mesmo acórdão."""
    for rotulo in _ROTULO_NUMERO.finditer(corrigido, 0, limite + 1):
        if _LEI_ANTES.search(corrigido[max(0, rotulo.start() - 30) : rotulo.end()]):
            continue
        resto = corrigido[rotulo.end() : rotulo.end() + 80]
        cnj = _CNJ_CATALOGO.match(resto)
        if cnj:
            return (extrair_digitos(cnj.group(0))[0],)
        m = _CADEIA.match(resto)
        if not m:
            continue
        numero = _cadeia_valida(resto, m)
        if not numero:
            continue
        parenteses = _CNJ_ENTRE_PARENTESES.match(resto, m.end())
        if parenteses:
            alternativo = _CNJ_CATALOGO.match(resto, parenteses.end())
            if alternativo:
                return (numero, extrair_digitos(alternativo.group(0))[0])
        return (numero,)
    return ()


def _primeira_cadeia_propria(corrigido: str) -> tuple[int, str] | None:
    """(posição, dígitos) da primeira cadeia válida; um CNJ que começa ali
    conta inteiro, mesmo com espaço solto depois de um separador."""
    for m in _CADEIA.finditer(corrigido):
        numero = _cadeia_valida(corrigido, m)
        if numero:
            cnj = _CNJ_CATALOGO.match(corrigido, m.start())
            return m.start(), extrair_digitos(cnj.group(0))[0] if cnj else numero
    return None


def numeros_proprios_acordao(texto: str, tribunal: str | None) -> tuple[str, ...]:
    """Números de processo do próprio acórdão, o principal primeiro, na
    mesma forma de dígitos que `extrair_campos` produz para um span.

    Ordem: no TST, a fórmula dos autos; nos demais, o número do rótulo "Nº"
    do cabeçalho, se ele vier antes de qualquer outro número, e senão a
    primeira cadeia válida. Quando o
    cabeçalho sai vazio (STF "EmentaeAcórdão" corta no rótulo "Ementa"), o
    mesmo vale para o início do texto. Um CNJ solto no cabeçalho não conta:
    na reclamação do STF, ele é o número do processo de origem."""
    if tribunal == "TST":
        numero = _numero_tst(texto)
        if numero:
            return (numero,)
    for trecho in (extrair_cabecalho(texto), texto[:_JANELA_SEM_ROTULO]):
        corrigido, _ = corrigir_ocr_numerico(trecho)
        primeira = _primeira_cadeia_propria(corrigido)
        limite = primeira[0] if primeira else len(corrigido)
        numeros = _numeros_do_rotulo(corrigido, limite)
        if numeros:
            return numeros
        if primeira:
            return (primeira[1],)
    return ()


def _campos_de_acordao(
    campos: CamposIdentificador, numeros: tuple[str, ...]
) -> CamposIdentificador:
    """Acórdão nunca é súmula: a menção a uma súmula no cabeçalho não pode
    apagar o número do processo."""
    classe = campos.classe
    if classe == "Súmula":
        classe = campos.classes_compostas[-1] if campos.classes_compostas else None
    return replace(
        campos,
        numero_normalizado=numeros[0] if numeros else None,
        classe=classe,
        sumula=None,
        vinculante=False,
    )


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
    numeros: tuple[str, ...] = ()
    if linha["natureza"] == "acordao":
        numeros = numeros_proprios_acordao(linha["texto"], linha["tribunal"])
        campos = _campos_de_acordao(campos, numeros)
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
        numeros_alternativos=numeros[1:],
    )


def construir_catalogo(conexao: sqlite3.Connection) -> CatalogoCanonico:
    """Lê `documentos` inteira e monta o catálogo em memória.

    Súmulas e dispositivos de lei (18 registros: 13 + 5) vão para
    `leis_sumulas`, casados por matching de texto — mesmo a súmula tendo
    `tipo="jurisprudencia"` no banco, o número curto colide demais com o
    índice de dígitos usado pelos acórdãos (Plano_de_acao.docx §3.3).
    """
    registros = [construir_registro(linha) for linha in _linhas(conexao)]
    return indexar(registros)


def indexar(registros: list[RegistroCatalogo]) -> CatalogoCanonico:
    por_chave: dict[str, list[RegistroCatalogo]] = defaultdict(list)
    leis_sumulas: list[RegistroCatalogo] = []
    for registro in registros:
        if registro.natureza in ("sumula", "dispositivo"):
            leis_sumulas.append(registro)
            continue
        for chave in registro.chaves():
            por_chave[chave].append(registro)
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
        "numeros_alternativos": list(registro.numeros_alternativos),
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
        numeros_alternativos=tuple(dados.get("numeros_alternativos", ())),
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
    return indexar(registros)


def relatorio_colisoes_texto(catalogo: CatalogoCanonico) -> str:
    """Relatório de colisões legível (chaves que apontam para 2+ registros)."""
    colisoes = catalogo.relatorio_colisoes()
    if not colisoes:
        return "nenhuma colisão"
    linhas = [f"{chave}: ids {ids}" for chave, ids in sorted(colisoes.items())]
    return "\n".join(linhas)
