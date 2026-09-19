"""Chave-esqueleto: canonicalização do identificador extraído (Módulo 2).

Regra de ouro (garantida pelo edital e cobrada em teste de propriedade,
ver `dominio/README.md`): **nunca troca um dígito por outro dígito**. Só
corrige letra->dígito visualmente confundível (0<->O, 1<->l, 5<->S),
reagrupa e normaliza separadores. A mesma função é usada para a citação
(aqui) e para o próprio catálogo (`catalogo/construir.py`), para que as
duas pontas cheguem à mesma chave — ver dominio/README.md.
"""

from __future__ import annotations

import re

from citacoes.dominio.lexico import UFS
from citacoes.dominio.texto import assinatura_tolerante_ocr, normalizar_comparavel

# Um "campo" (trecho de dígitos do formato CNJ, ex.: "7000449", "40", "2023",
# "7") pode, sozinho, virar 100% letra por ruído de OCR (o código de justiça
# "7" em "...2023.7.00...", por exemplo) — sem nenhum dígito real como
# âncora ali. Por isso a unidade de correção não é o run alfanumérico
# isolado, e sim a cadeia de campos ligados por "." ou "-" sem espaço (a
# pontuação interna de um número), com densidade de dígito medida na cadeia
# inteira. "/" fica de fora de propósito: é o separador de UF (extrair_uf),
# nunca pontuação interna do número — incluir "/" aqui corrigiria "S" de
# "/SP" para "5P".
_CADEIA_NUMERICA = re.compile(r"[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*")

# Letra -> dígito, só aplicada dentro de uma cadeia que já contém ao menos um
# dígito de verdade em algum campo (assim "REsp" nunca vira número, mas
# "7OOO449" ou "2023.O.00" — onde o "O" isolado é vizinho de dígitos reais
# via ponto —, viram número).
_LETRA_PARA_DIGITO = {"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "s": "5"}

# O agrupamento de milhar brasileiro (reagrupar()) pode deixar o primeiro
# campo com 1 dígito só (ex.: "1 307 026" — "1" sozinho). Se o ruído de OCR
# atinge exatamente esse campo, ele vira uma letra sem nenhum dígito vizinho
# via ponto/hífen para ancorar a correção acima — só um espaço o separa do
# resto. Por isso a 2ª passada abaixo trata só o caso estrito de um token
# feito de UMA letra confundível, isolado por espaço, com vizinho numérico:
# não generaliza para tokens de 2+ letras porque aí colide com palavras reais
# do português ("os", "so").
_TOKEN_CONFUNDIVEL_ISOLADO = re.compile(r"^[OoIlSs]$")


def corrigir_ocr_numerico(trecho: str) -> tuple[str, bool]:
    """Corrige confusões de OCR letra->dígito só dentro de cadeias numéricas.

    Retorna (trecho_corrigido, houve_correcao). `trecho_corrigido` é um
    valor auxiliar interno — nunca substitui o `trecho` do span, que
    permanece cópia literal do texto de origem (Contrato de Dados §3).
    """
    alterado = False

    def _corrige_cadeia(match: re.Match[str]) -> str:
        nonlocal alterado
        cadeia = match.group(0)
        if not any(c.isdigit() for c in cadeia):
            return cadeia
        novo = "".join(_LETRA_PARA_DIGITO.get(c, c) for c in cadeia)
        if novo != cadeia:
            alterado = True
        return novo

    corrigido = _CADEIA_NUMERICA.sub(_corrige_cadeia, trecho)

    partes = re.split(r"(\s+)", corrigido)  # alterna token, espaço, token...
    for i in range(0, len(partes), 2):
        token = partes[i]
        if not _TOKEN_CONFUNDIVEL_ISOLADO.match(token):
            continue
        vizinho_antes = partes[i - 2] if i >= 2 else ""
        vizinho_depois = partes[i + 2] if i + 2 < len(partes) else ""
        if any(c.isdigit() for c in vizinho_antes) or any(c.isdigit() for c in vizinho_depois):
            partes[i] = _LETRA_PARA_DIGITO[token]
            alterado = True
    corrigido = "".join(partes)

    return corrigido, alterado


def extrair_digitos(trecho: str) -> tuple[str, bool]:
    """Pipeline completo do identificador numérico: corrige OCR e extrai só dígitos.

    Espaços soltos e quebras de linha dentro do número (Nível 2) somem
    sozinhos aqui, porque só dígitos são mantidos — não é preciso tratá-los
    à parte.
    """
    corrigido, ocr_corrigido = corrigir_ocr_numerico(trecho)
    digitos = "".join(c for c in corrigido if c.isdigit())
    return digitos, ocr_corrigido


def reagrupar(digitos: str) -> str:
    """Forma canônica legível do identificador, para exibição/depuração e
    para eventual consulta por frase (FTS5).

    - 20 dígitos: formato CNJ padrão NNNNNNN-DD.AAAA.J.TR.OOOO.
    - Caso contrário: agrupamento numérico brasileiro, 3 em 3 da direita
      para a esquerda (regra citada no edital, usada em números de processo
      mais antigos/curtos, ex.: "Reclamação nº 66.516").

    A chave usada para casar contra o catálogo é sempre `extrair_digitos`
    (dígitos puros) — esta função é só a forma apresentável, imune a
    diferenças de agrupamento não fazerem `==` bater.
    """
    if len(digitos) == 20:
        return f"{digitos[0:7]}-{digitos[7:9]}.{digitos[9:13]}.{digitos[13:14]}.{digitos[14:16]}.{digitos[16:20]}"
    partes: list[str] = []
    resto = digitos
    while len(resto) > 3:
        partes.insert(0, resto[-3:])
        resto = resto[:-3]
    if resto:
        partes.insert(0, resto)
    return ".".join(partes)


_UF_NO_FINAL = re.compile(r"[\s/\-\(]{1,3}(?P<uf>[A-Za-z]{2})\)?\s*$")


def extrair_uf(trecho: str) -> str | None:
    """UF ao final do trecho, qualquer separador (`/PR`, `- PR`, `(PR)`, `PR`).

    Devolve a forma canônica (só a sigla) — não reescreve `trecho`; produz
    um campo derivado novo, como todo o resto deste módulo.
    """
    m = _UF_NO_FINAL.search(trecho)
    if not m:
        return None
    uf = m.group("uf").upper()
    return uf if uf in UFS else None


def _indice_para(tabela: dict[str, tuple[str, ...]]) -> dict[str, str]:
    from citacoes.dominio.lexico import indice_variantes

    return indice_variantes(tabela)


def _casar_ngramas(trecho: str, indice: dict[str, str], max_ngram: int) -> list[str]:
    """Varre `trecho` da esquerda para a direita casando o maior n-grama
    possível contra `indice` a cada posição (não sobrepõe), na ordem em que
    aparece — usado para achar cadeias como "EDcl no AgInt no ARESP".
    """
    tokens = normalizar_comparavel(trecho).split()
    achados: list[str] = []
    i = 0
    while i < len(tokens):
        casou = False
        for n in range(min(max_ngram, len(tokens) - i), 0, -1):
            candidato = " ".join(tokens[i : i + n])
            codigo = indice.get(assinatura_tolerante_ocr(candidato))
            if codigo:
                achados.append(codigo)
                i += n
                casou = True
                break
        if not casou:
            i += 1
    return achados


def classes_processuais(trecho: str) -> tuple[str, ...]:
    """Classes processuais reconhecidas no trecho, na ordem em que aparecem.

    Ex.: "EDcl no AgInt no ARESP 1.821.663/SC" -> ("EDcl", "AgInt", "AREsp").
    A última é, na prática, o recurso-base — quem consome decide o que usar.
    """
    from citacoes.dominio.lexico import CLASSES_PROCESSUAIS

    indice = _indice_para(CLASSES_PROCESSUAIS)
    max_ngram = max(len(v.split()) for vs in CLASSES_PROCESSUAIS.values() for v in vs)
    return tuple(_casar_ngramas(trecho, indice, max_ngram))


def diploma_legal(trecho: str) -> str | None:
    """Diploma legal citado (CF, CPC, CC...), se algum do léxico casar."""
    from citacoes.dominio.lexico import DIPLOMAS

    indice = _indice_para(DIPLOMAS)
    max_ngram = max(len(v.split()) for vs in DIPLOMAS.values() for v in vs)
    achados = _casar_ngramas(trecho, indice, max_ngram)
    return achados[0] if achados else None


def tribunal_citado(trecho: str) -> str | None:
    """Tribunal citado no próprio trecho (STF, STJ...), se algum casar."""
    from citacoes.dominio.lexico import TRIBUNAIS

    indice = _indice_para(TRIBUNAIS)
    max_ngram = max(len(v.split()) for vs in TRIBUNAIS.values() for v in vs)
    achados = _casar_ngramas(trecho, indice, max_ngram)
    return achados[0] if achados else None
