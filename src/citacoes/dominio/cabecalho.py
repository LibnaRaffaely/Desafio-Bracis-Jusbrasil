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
_ROTULO_EMENTA = re.compile(r"\bementa\b", re.IGNORECASE)
_ROTULO_PROCESSO = re.compile(r"processo\s*n[º°o]", re.IGNORECASE)

# Nenhum dos 1016 registros reais de desafio1_bracis.db tem quebra dupla de
# linha (confirmado; a base vem como um bloco corrido por documento) — o
# rótulo "EMENTA"/"Ementa" é o marcador que de fato separa a autuação
# (cabeçalho, com o número do próprio registro) do relatório/voto (onde só
# aparecem números de outros processos, súmulas etc. citados no corpo).
# Alguns casos (~8% dos acórdãos, sobretudo TST/TSE sem rótulo "EMENTA"
# próprio) não têm nenhum dos três marcadores; para esses o cabeçalho cai no
# teto abaixo em vez do texto inteiro, para não repetir o defeito que este
# módulo existe para evitar (ver catalogo/README.md).
#
# O teto vale para QUALQUER marcador achado, não só a ausência de um —
# "EMENTA" pode aparecer só depois de uma lista longa de partes/votos (ex.:
# STM "EXTRATO DE ATA...", onde um voto já cita "em consonância com a
# Súmula nº 18" antes da própria EMENTA do acórdão). O número do próprio
# registro está sempre perto do início (visto <400 caracteres em todos os
# tribunais da base); o teto é generoso o bastante para isso e apertado o
# bastante para cortar fora o que vem depois.
_TAMANHO_MAXIMO_CABECALHO = 1000


def extrair_cabecalho(texto: str) -> str:
    """Bloco inicial até a primeira quebra dupla de linha; na ausência dela
    (base real), até o rótulo "EMENTA"/"Ementa" ou, se também faltar, até o
    fim da linha do rótulo "Processo nº". Sem nenhum marcador (ou com um
    marcador tardio demais), os primeiros `_TAMANHO_MAXIMO_CABECALHO`
    caracteres — nunca o texto inteiro."""
    m = _QUEBRA_DUPLA.search(texto)
    if m:
        limite = m.start()
    else:
        m_ementa = _ROTULO_EMENTA.search(texto)
        if m_ementa:
            limite = m_ementa.start()
        else:
            m_rotulo = _ROTULO_PROCESSO.search(texto)
            if m_rotulo:
                fim_linha = texto.find("\n", m_rotulo.end())
                limite = fim_linha if fim_linha != -1 else len(texto)
            else:
                limite = len(texto)
    return texto[: min(limite, _TAMANHO_MAXIMO_CABECALHO)]
