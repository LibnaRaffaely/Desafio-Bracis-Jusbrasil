"""Módulo 2 — chave-esqueleto: reagrupamento, OCR e separador de UF.

Casos numéricos vêm de Analise_Exploratoria.docx §b/§c (consultas FTS5
testadas contra o banco real e ruídos confirmados no Nível 2).
"""

from __future__ import annotations

import random
import string

from hypothesis import given
from hypothesis import strategies as st

from citacoes.dominio.chave import (
    classes_processuais,
    corrigir_ocr_numerico,
    diploma_legal,
    extrair_digitos,
    extrair_uf,
    reagrupar,
    tribunal_citado,
)
from citacoes.dominio.ruido import injetar_ruido


def test_ocr_corrige_letra_por_digito_so_em_run_numerico():
    digitos, ocr = extrair_digitos("7OOO449-40.2023.7.00.0000")
    assert digitos == "70004494020237000000"
    assert ocr is True


def test_ocr_nao_mexe_em_run_sem_nenhum_digito():
    # "REsp" não tem dígito nenhum no run -> nunca vira número
    digitos, ocr = extrair_digitos("REsp 1.234/PR")
    assert ocr is False
    assert digitos == "1234"


def test_digito_faltando_nao_e_recuperavel():
    # mesmo número real, um dígito a menos: chave diferente, de propósito —
    # ruído de dígito faltando não é OCR, é perda de informação (edital).
    real, _ = extrair_digitos("7000449-40.2023.7.00.0000")
    faltando, _ = extrair_digitos("700449-40.2023.7.00.0000")
    assert real != faltando


def test_espaco_solto_e_quebra_de_linha_dentro_do_numero_somem():
    digitos, _ = extrair_digitos("EDcl no AgInt no ARESP  1 821 663/ SC")
    assert digitos == "1821663"
    digitos2, _ = extrair_digitos("RESP n. 1\n307\n026/BA")
    assert digitos2 == "1307026"


def test_reagrupar_cnj_20_digitos():
    digitos, _ = extrair_digitos("7000449-40.2023.7.00.0000")
    assert reagrupar(digitos) == "7000449-40.2023.7.00.0000"


def test_reagrupar_numero_curto_de_3_em_3():
    digitos, _ = extrair_digitos("1.821.663")
    assert reagrupar(digitos) == "1.821.663"
    digitos2, _ = extrair_digitos("66.516")
    assert reagrupar(digitos2) == "66.516"


def test_extrair_uf_qualquer_separador():
    assert extrair_uf("7000449-40.2023.7.00.0000/RS") == "RS"
    assert extrair_uf("Recl. Nº 66.152 - PR") == "PR"
    assert extrair_uf("Recl. Nº 66.152 (PR)") == "PR"
    assert extrair_uf("Recl. Nº 66.152 PR") == "PR"
    assert extrair_uf("Recl. Nº 66.152") is None
    assert extrair_uf("Recl. Nº 66.152/XX") is None  # XX não é UF válida


def test_classes_processuais_reconhece_compostas_na_ordem():
    assert classes_processuais("EDcl no AgInt no ARESP 1.821.663/SC") == (
        "EDcl",
        "AgInt",
        "AREsp",
    )
    assert classes_processuais("Recurso Especial 1.307.026/BA") == ("REsp",)


def test_classes_processuais_tolera_abreviacao_com_pontuacao():
    assert classes_processuais("R.Esp. 1.307.026/BA") == ("REsp",)
    assert classes_processuais("Ag.Rg. no AREsp 1.234/PR") == ("AgRg", "AREsp")


def test_diploma_legal_e_tribunal_citado():
    assert diploma_legal("art. 927 do Código de Processo Civil") == "CPC"
    assert diploma_legal("art. 5º da CF") == "CF"
    assert tribunal_citado("Súmula 331 do TST") == "TST"
    assert tribunal_citado("julgado do S.T.F.") == "STF"


def test_corrigir_ocr_numerico_reporta_alteracao_apenas_quando_muda():
    _, alterado = corrigir_ocr_numerico("REsp 1.234.567/PR")
    assert alterado is False
    _, alterado2 = corrigir_ocr_numerico("REsp 1.234.S67/PR")
    assert alterado2 is True


# --- Propriedade central do módulo (dominio/README.md) -------------------
#
# esqueleto(ruido(x)) == esqueleto(x): o ruído de Nível 2 nunca muda a
# chave-esqueleto de um identificador bem formado. E trocar um dígito real
# nunca leva à mesma chave (o inverso do "recuperável").

# Números reais têm estrutura: grupos de 1 a 4 dígitos, um único separador
# entre cada grupo, nunca pontuação solta/dobrada nem separador nas pontas.
# Gerar sopa de caracteres sem essa estrutura (2 pontos seguidos, "/" no
# meio, espaço na borda) cria casos que não existem no dataset real — a
# propriedade é sobre ruído de Nível 2 em cima de um número bem formado, não
# sobre qualquer string.
_GRUPO_DIGITOS = st.text(alphabet=string.digits, min_size=1, max_size=4)
_SEPARADOR = st.sampled_from([".", "-", " "])


@st.composite
def _numeros_validos(draw: st.DrawFn) -> str:
    grupos = draw(st.lists(_GRUPO_DIGITOS, min_size=2, max_size=6))
    separadores = draw(st.lists(_SEPARADOR, min_size=len(grupos) - 1, max_size=len(grupos) - 1))
    partes = [grupos[0]]
    for separador, grupo in zip(separadores, grupos[1:], strict=True):
        partes.append(separador)
        partes.append(grupo)
    numero = "".join(partes)
    if len(re_digits(numero)) < 5:
        return draw(_numeros_validos())
    return numero


def re_digits(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


@given(numero=_numeros_validos(), seed=st.integers(min_value=0, max_value=2**31 - 1))
def test_propriedade_esqueleto_ruido_igual_esqueleto_original(numero: str, seed: int):
    rng = random.Random(seed)
    ruidoso = injetar_ruido(numero, rng)
    digitos_original, _ = extrair_digitos(numero)
    digitos_ruidoso, _ = extrair_digitos(ruidoso)
    assert digitos_original == digitos_ruidoso


@given(numero=_numeros_validos(), posicao=st.integers(min_value=0))
def test_trocar_um_digito_nunca_leva_a_mesma_chave(numero: str, posicao: int):
    # Regressão contra a tentação de "normalizar" dígitos parecidos (ex.:
    # 6/8) como se fossem OCR — o edital garante que isso nunca acontece,
    # então extrair_digitos precisa preservar a diferença ponta a ponta.
    indices_digitos = [i for i, c in enumerate(numero) if c.isdigit()]
    if not indices_digitos:
        return
    i = indices_digitos[posicao % len(indices_digitos)]
    outro_digito = str((int(numero[i]) + 1) % 10)
    numero_trocado = numero[:i] + outro_digito + numero[i + 1 :]

    original, _ = extrair_digitos(numero)
    trocado, _ = extrair_digitos(numero_trocado)
    assert original != trocado
