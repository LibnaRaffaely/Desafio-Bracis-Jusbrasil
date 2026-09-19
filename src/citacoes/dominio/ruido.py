"""Injetor de ruído do Nível 2, para testes de propriedade e dados sintéticos.

Só os 3 tipos de ruído confirmados em Analise_Exploratoria.docx §c:
confusão de OCR letra<->dígito, espaço solto dentro do número e quebra de
linha dentro do número. Nunca troca um dígito por outro dígito — só pelo
correspondente visualmente parecido (garantia do próprio edital).
"""

from __future__ import annotations

import random

_DIGITO_PARA_LETRA = {"0": "O", "1": "l", "5": "S"}


def injetar_ruido_ocr(trecho: str, rng: random.Random, taxa: float = 0.3) -> str:
    """Troca alguns dígitos (0, 1, 5) pela letra visualmente parecida."""
    return "".join(
        _DIGITO_PARA_LETRA[c] if c in _DIGITO_PARA_LETRA and rng.random() < taxa else c
        for c in trecho
    )


def _inserir_entre_digitos(trecho: str, rng: random.Random, taxa: float, separador: str) -> str:
    saida: list[str] = []
    for i, c in enumerate(trecho):
        saida.append(c)
        proximo_e_digito = i + 1 < len(trecho) and trecho[i + 1].isdigit()
        if c.isdigit() and proximo_e_digito and rng.random() < taxa:
            saida.append(separador)
    return "".join(saida)


def injetar_espaco_solto(trecho: str, rng: random.Random, taxa: float = 0.1) -> str:
    """Insere espaço solto entre dígitos, como em "1 307 026"."""
    return _inserir_entre_digitos(trecho, rng, taxa, " ")


def injetar_quebra_linha(trecho: str, rng: random.Random, taxa: float = 0.1) -> str:
    """Insere quebra de linha dentro do identificador."""
    return _inserir_entre_digitos(trecho, rng, taxa, "\n")


def injetar_ruido(trecho: str, rng: random.Random) -> str:
    """Combina os 3 tipos de ruído do Nível 2 num único trecho sintético."""
    saida = injetar_ruido_ocr(trecho, rng)
    saida = injetar_espaco_solto(saida, rng)
    saida = injetar_quebra_linha(saida, rng)
    return saida
