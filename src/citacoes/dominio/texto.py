"""Normalização de texto para comparação (não para exibição).

Usada para casar abreviações, diplomas e tribunais do léxico contra o
trecho citado, ignorando acentuação, caixa e pontuação — nunca para
alterar `trecho` (que é cópia literal, ver Contrato de Dados §3).
"""

from __future__ import annotations

import re

from unidecode import unidecode

_NAO_ALFANUM = re.compile(r"[^A-Z0-9]+")


def normalizar_comparavel(texto: str) -> str:
    """Maiúsculas, sem acento, pontuação vira espaço único, sem bordas."""
    sem_acento = unidecode(texto).upper()
    return _NAO_ALFANUM.sub(" ", sem_acento).strip()


_EQUIV_OCR = str.maketrans({"0": "O", "1": "L", "5": "S"})


def assinatura_tolerante_ocr(texto: str) -> str:
    """Assinatura para comparação tolerante às confusões de OCR do edital.

    Colapsa os pares 0/O, 1/l, 5/S e a confusão de forma m/rn num símbolo
    comum, só para efeito de comparação — nunca reescreve o texto original,
    porque "rn"->"m" corromperia palavras reais (ex.: "Interno").
    """
    normalizado = normalizar_comparavel(texto)
    sem_m_rn = normalizado.replace("RN", "M")
    return sem_m_rn.translate(_EQUIV_OCR)
