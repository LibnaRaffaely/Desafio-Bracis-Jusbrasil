from __future__ import annotations
from citacoes.grafo.estados import EstadoCitacao, EstadoDocumento


def _tipo_final(citacao: EstadoCitacao) -> str:
    """uses resolved type from M4 falls back to tipo_bruto if None"""

    if citacao.tipo and citacao.tipo != "indefinido":
        return citacao.tipo
    return citacao.tipo_bruto if citacao.tipo_bruto != "indefinido" else "jurisprudencia"


def _validar(citacao: EstadoCitacao) -> None:
    assert citacao.inicio >= 0, f"inicio negativo: {citacao.inicio}"
    assert citacao.fim > citacao.inicio, f"fim <= inicio: {citacao.fim} <= {citacao.inicio}"
    assert citacao.classificacao in {"real", "inventada", "incompleta"}, \
        f"classificacao invalida: {citacao.classificacao}"
    if citacao.classificacao == "real":
        assert citacao.id_canonico is not None, \
            f"real sem id_canonico: {citacao.trecho}"
    if citacao.confianca is not None:
        assert 0.0 <= citacao.confianca <= 1.0, \
            f"confianca fora do intervalo: {citacao.confianca}"


def _formatar_citacao(citacao: EstadoCitacao) -> dict:
    resultado: dict = {
        "inicio": citacao.inicio,
        "fim": citacao.fim,
        "trecho": citacao.trecho,
        "tipo": _tipo_final(citacao),
        "classificacao": citacao.classificacao,
    }
    if citacao.classificacao == "real":
        resultado["resolucao"] = {"id_canonico": citacao.id_canonico}
    if citacao.confianca is not None:
        resultado["confianca"] = citacao.confianca
    return resultado


def reunir_e_formatar(estado: EstadoDocumento) -> dict:
    citacoes = sorted(estado.citacoes, key=lambda c: c.inicio)

    for citacao in citacoes:
        _validar(citacao)

    saida = {
        "documento_id": estado.documento_id,
        "citacoes": [_formatar_citacao(c) for c in citacoes],
    }

    return {"saida": saida}