"""Léxico jurídico compartilhado: classes processuais, diplomas, tribunais e UFs.

Cada entrada é (código canônico -> variantes como aparecem no texto real,
incluindo abreviações com/sem ponto e o nome por extenso). O matching contra
o trecho é sempre feito via `dominio.texto`, tolerante a acento/caixa/
pontuação e, no caso das classes, às confusões de OCR do edital.

Fonte dos formatos mais frequentes: Analise_Exploratoria.docx §c (contagem
nos 195 trechos do goldenset).
"""

from __future__ import annotations

CLASSES_PROCESSUAIS: dict[str, tuple[str, ...]] = {
    "REsp": ("REsp", "R.Esp.", "R. Esp.", "Recurso Especial"),
    "AgRg": ("AgRg", "Ag.Rg.", "Ag Rg", "Agravo Regimental"),
    "AgInt": ("AgInt", "Ag.Int.", "Ag Int", "Agravo Interno"),
    "AREsp": (
        "AREsp",
        "Ag.REsp",
        "Ag. em REsp",
        "Agravo em Recurso Especial",
    ),
    "Rcl": ("Rcl", "Recl.", "Reclamação"),
    "EDcl": ("EDcl", "ED", "Emb.Decl.", "Embargos de Declaração"),
    "RR": ("RR", "Recurso de Revista"),
    "ARR": ("ARR", "Agravo em Recurso de Revista"),
    "RHC": ("RHC", "Recurso em Habeas Corpus"),
    "APL": ("APL", "Ap.", "Apelação", "Apelação Cível"),
    "RSE": ("RSE", "Recurso em Sentido Estrito"),
    "RE": ("RE", "Recurso Extraordinário"),
    "HC": ("HC", "Habeas Corpus"),
    "MS": ("MS", "Mandado de Segurança"),
}

# Ordem de prioridade quando 2+ classes casam no mesmo trecho (ex.: "EDcl no
# AgInt no ARESP..."): a última reconhecida antes do número é normalmente o
# recurso-base, mas mantemos aqui só a lista de nomes reconhecidos — a
# decisão de qual é "a" classe principal fica em `chave.classes_processuais`.
DIPLOMAS: dict[str, tuple[str, ...]] = {
    "CF": ("CF", "CRFB", "Constituição Federal", "Constituição da República"),
    "CPC": ("CPC", "Código de Processo Civil"),
    "CC": ("CC", "Código Civil"),
    "CP": ("CP", "Código Penal"),
    "CPP": ("CPP", "Código de Processo Penal"),
    "CLT": ("CLT", "Consolidação das Leis do Trabalho"),
    "CDC": ("CDC", "Código de Defesa do Consumidor"),
    "CTN": ("CTN", "Código Tributário Nacional"),
    "ECA": ("ECA", "Estatuto da Criança e do Adolescente"),
    # "Código Penal Militar" tem 3 tokens contra os 2 de "Código Penal" —
    # o casador de n-gramas tenta o maior n-grama primeiro (chave.py,
    # _casar_ngramas), então a frase completa vence "CP" na mesma posição;
    # sem esta entrada, "art. 290 do Código Penal Militar" seria lido como
    # CP (Analise/RELATORIO_MODULO4.md §6.7).
    "CPM": ("CPM", "Código Penal Militar"),
    # Sem a sigla curta "CE" (colide demais com a UF Ceará) — só a forma por
    # extenso aparece nas citações do goldenset.
    "CE": ("Código Eleitoral",),
    "LC64": (
        "LC 64/1990",
        "LC 64/90",
        "Lei Complementar 64/1990",
        "Lei Complementar nº 64/1990",
        "Lei Complementar n° 64/1990",
        "Lei das Inelegibilidades",
        "Lei de Inelegibilidades",
    ),
}

# Tribunais confirmados na coluna `tribunal` de desafio1_bracis.db
# (Analise_Exploratoria.docx §b) + variantes comuns de citação em texto.
TRIBUNAIS: dict[str, tuple[str, ...]] = {
    "STF": ("STF", "S.T.F.", "Supremo Tribunal Federal"),
    "STJ": ("STJ", "S.T.J.", "Superior Tribunal de Justiça"),
    "STM": ("STM", "S.T.M.", "Superior Tribunal Militar"),
    "TSE": ("TSE", "T.S.E.", "Tribunal Superior Eleitoral"),
    "TST": ("TST", "T.S.T.", "Tribunal Superior do Trabalho"),
}

UFS: frozenset[str] = frozenset(
    {
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    }
)


def indice_variantes(tabela: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Inverte a tabela: assinatura tolerante a OCR de cada variante -> código canônico.

    Usado para lookup O(1) em vez de varrer a tabela inteira a cada trecho.
    """
    from citacoes.dominio.texto import assinatura_tolerante_ocr

    indice: dict[str, str] = {}
    for canonico, variantes in tabela.items():
        for variante in variantes:
            indice[assinatura_tolerante_ocr(variante)] = canonico
    return indice
