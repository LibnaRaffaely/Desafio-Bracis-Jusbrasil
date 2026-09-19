"""Nó `normalizar` (Módulo 2)."""

from __future__ import annotations

from citacoes.dominio.campos import CamposIdentificador
from citacoes.grafo.estados import EstadoCitacao
from citacoes.nos.normalizar import normalizar


def _span(**kwargs) -> EstadoCitacao:
    base = dict(
        inicio=0,
        fim=10,
        trecho="APL nº 7000449-40.2023.7.00.0000/RS",
        tipo_bruto="jurisprudencia",
        tem_identificador=True,
        origem="regex_camada1",
    )
    base.update(kwargs)
    return EstadoCitacao(**base)


def test_sem_identificador_nao_tenta_normalizar():
    estado = _span(tem_identificador=False, trecho="jurisprudência pacífica do tribunal")
    atualizacao = normalizar(estado)
    assert atualizacao["campos"] == CamposIdentificador()
    assert atualizacao["campos"].numero_normalizado is None
    assert atualizacao["ocr_corrigido"] is False


def test_normaliza_jurisprudencia_com_identificador():
    estado = _span()
    atualizacao = normalizar(estado)
    assert atualizacao["campos"].numero_normalizado == "70004494020237000000"
    assert atualizacao["campos"].classe == "APL"
    assert atualizacao["campos"].uf == "RS"
    assert atualizacao["ocr_corrigido"] is False


def test_normaliza_e_sinaliza_ocr_corrigido():
    estado = _span(trecho="APL nº 7OOO449-40.2023.7.00.0000/RS")
    atualizacao = normalizar(estado)
    assert atualizacao["campos"].numero_normalizado == "70004494020237000000"
    assert atualizacao["ocr_corrigido"] is True


def test_devolve_so_os_campos_que_muda():
    estado = _span()
    atualizacao = normalizar(estado)
    assert set(atualizacao.keys()) == {"campos", "ocr_corrigido"}
