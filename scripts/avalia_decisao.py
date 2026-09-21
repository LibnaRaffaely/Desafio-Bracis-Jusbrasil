"""Avaliação do Módulo 4 (`nos/decidir.py`) contra o goldenset. Só biblioteca
padrão além do próprio pacote.

Uso:
    python scripts/avalia_decisao.py --dados /caminho/da/pasta_do_desafio
    python scripts/avalia_decisao.py --dados ... --modo isolado
    python scripts/avalia_decisao.py --dados ... --modo integrado
    python scripts/avalia_decisao.py --dados ... --juiz falso

Modos (docs/avaliacao.md, modo `resolucao`):

- `isolado`: entradas sintéticas derivadas do gabarito (gold `real` -> 1
  candidato limpo com o id do gabarito; `inventada` -> 0 candidatos;
  `incompleta` -> sem busca ou 2+ candidatos limpos), mais uma fatia com
  conflitos duros para exercitar o veto. Mede só o Módulo 4: tem de dar
  100%, senão o defeito é do nó de decisão. Sai com código 1 se não der.
  Um segundo bloco, reportado à parte para não mexer na linha de base de
  451 entradas, exercita os desempates determinísticos (duplicata de
  conteúdo, margem de score) e os três desfechos do juiz (id válido, id
  fora da lista, indecisão) com `JuizFalso`.
- `integrado`: spans do gabarito como extração-oráculo -> `normalizar`
  (Módulo 2) -> `resolver` (Módulo 3, catálogo real) -> `decidir`. Tudo
  reportado separado por `metodo_busca`, porque o caminho de lei/súmula e o
  de jurisprudência têm defeitos independentes a montante. O diagnóstico
  inclui contrafactuais (o que os desempates e o juiz mudariam hoje) e a
  projeção de macro-F1 se todo `cardinalidade_2mais` virasse `real` certo.

`--juiz {desligado,falso}` (padrão `desligado`): `falso` liga o juiz com
`JuizFalso` — no isolado, respostas programadas por fatia; no integrado,
um oráculo que devolve o id do gabarito quando ele está entre os
candidatos (teto do que um juiz perfeito faria). Nenhum modo carrega
pesos de modelo aqui; isso fica para quem tiver a GPU do envelope.

O catálogo real demora para construir; fica em cache em `artifacts/`
(gitignored) e é reaproveitado. Erros por citação vão para `outputs/`
(gitignored). A base é aberta em modo somente leitura.

Semântica de macro-F1 e τ copiada de `kaggle_metric.py`: `real` com id
errado é FP de `real` sem FN; classe trocada é FN da esperada e FP da
predita; τ = inventadas do gabarito preditas como `real`; classe sem
suporte fica fora da média.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from citacoes.catalogo.construir import (  # noqa: E402
    carregar,
    construir_catalogo_de_arquivo,
    salvar,
)
from citacoes.catalogo.esquema import Candidato, CatalogoCanonico  # noqa: E402
from citacoes.grafo.estados import EstadoCitacao  # noqa: E402
from citacoes.nos.buscar_no_catalogo import resolver  # noqa: E402
from citacoes.nos.decidir import (  # noqa: E402
    Duplicatas,
    DuplicatasPorAssinatura,
    Juiz,
    JuizDesligado,
    JuizFalso,
    ParametrosDecisao,
    SemDuplicatas,
    decidir,
)
from citacoes.nos.normalizar import normalizar  # noqa: E402

CLASSES = ("real", "inventada", "incompleta")
METODOS_DECISAO = (
    "sem_identificador",
    "cardinalidade_0",
    "cardinalidade_1",
    "cardinalidade_2mais",
    "veto_quimera",
    "desempate_duplicata",
    "desempate_score",
    "juiz",
)
GAMMA = 0.5
NOME_CACHE_CATALOGO = "catalogo_canonico.json"
NOME_CACHE_ASSINATURAS = "assinaturas_conteudo.json"


# ── gabarito ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Gold:
    nivel: int
    documento_id: str
    citacao_id: str
    inicio: int
    fim: int
    trecho: str
    tipo: str
    classificacao: str
    id_canonico: int | None


def _desescapar(trecho: str) -> str:
    return trecho.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t")


def ler_gabarito(pasta: Path) -> list[Gold]:
    """Lê `goldenset.csv`; quando o .txt existe, o trecho vem de
    `texto[inicio:fim]` (cópia literal, invariante de docs/contratos.md)."""
    textos: dict[str, str] = {}
    pasta_txt = pasta / "txt"
    if pasta_txt.is_dir():
        for arquivo in pasta_txt.glob("*.txt"):
            with open(arquivo, encoding="utf-8", newline="") as f:
                textos[arquivo.stem] = f.read()
    linhas: list[Gold] = []
    with open(pasta / "goldenset.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            inicio, fim = int(r["inicio"]), int(r["fim"])
            texto = textos.get(r["documento_id"])
            trecho = texto[inicio:fim] if texto is not None else _desescapar(r["trecho"])
            id_bruto = r["id_canonico"].strip()
            linhas.append(
                Gold(
                    nivel=int(r["nivel"]),
                    documento_id=r["documento_id"],
                    citacao_id=r["citacao_id"],
                    inicio=inicio,
                    fim=fim,
                    trecho=trecho,
                    tipo=r["tipo"],
                    classificacao=r["classificacao"],
                    id_canonico=int(id_bruto) if id_bruto else None,
                )
            )
    return linhas


# ── resultado por citação ───────────────────────────────────────────────────


@dataclass
class Resultado:
    gold: Gold
    rotulo: str  # nome da fatia (isolado) ou "gabarito" (integrado)
    estado: EstadoCitacao
    saida: dict
    esperado_classe: str
    esperado_id: int | None
    esperado_tipo: str
    esperado_metodo: str | None = None  # só no modo isolado

    @property
    def categoria(self) -> str:
        pred, gold = self.saida["classificacao"], self.esperado_classe
        if pred != gold:
            if gold == "inventada" and pred == "real":
                return "erro_tau"
            return "classe_trocada"
        if gold == "real" and self.saida["id_canonico"] != self.esperado_id:
            return "id_errado"
        return "acerto"


# ── métrica (semântica de kaggle_metric.py) ────────────────────────────────


@dataclass
class Acumulador:
    tp: Counter = field(default_factory=Counter)
    fp: Counter = field(default_factory=Counter)
    fn: Counter = field(default_factory=Counter)
    suporte: Counter = field(default_factory=Counter)
    tau_num: int = 0
    tau_den: int = 0
    confusao: Counter = field(default_factory=Counter)

    def acumular(self, r: Resultado) -> None:
        cg, cp = r.esperado_classe, r.saida["classificacao"]
        self.suporte[cg] += 1
        self.confusao[(cg, cp)] += 1
        if cg == "inventada":
            self.tau_den += 1
        if cg == cp:
            if cg == "real" and r.saida["id_canonico"] != r.esperado_id:
                self.fp["real"] += 1  # real com id errado: FP sem FN
            else:
                self.tp[cg] += 1
        else:
            self.fn[cg] += 1
            self.fp[cp] += 1
            if cg == "inventada" and cp == "real":
                self.tau_num += 1

    def f1_por_classe(self) -> dict[str, float]:
        f1s = {}
        for c in CLASSES:
            if self.suporte[c] == 0:
                continue
            denom = 2 * self.tp[c] + self.fp[c] + self.fn[c]
            f1s[c] = (2 * self.tp[c] / denom) if denom > 0 else 0.0
        return f1s

    def macro_f1(self) -> float:
        f1s = self.f1_por_classe()
        return sum(f1s.values()) / len(f1s) if f1s else 0.0

    def tau(self) -> float:
        return self.tau_num / self.tau_den if self.tau_den else 0.0

    def s(self) -> float:
        return self.macro_f1() * (1.0 - GAMMA * self.tau())


def _tabela_confusao(acc: Acumulador) -> str:
    cab = "gold \\ pred".ljust(14) + "".join(c.rjust(12) for c in CLASSES) + "total".rjust(8)
    linhas = [cab]
    for g in CLASSES:
        valores = [acc.confusao[(g, p)] for p in CLASSES]
        linhas.append(
            g.ljust(14) + "".join(str(v).rjust(12) for v in valores) + str(sum(valores)).rjust(8)
        )
    return "\n".join(linhas)


def _resumo_metrica(acc: Acumulador) -> str:
    f1s = acc.f1_por_classe()
    partes = [f"{c}={f1s[c]:.3f}" for c in CLASSES if c in f1s]
    return (
        f"macro-F1 = {acc.macro_f1():.3f}  ({', '.join(partes)})  |  "
        f"τ = {acc.tau():.3f} ({acc.tau_num}/{acc.tau_den})  |  "
        f"s = macroF1·(1−0,5τ) = {acc.s():.3f}"
    )


def _secao(titulo: str) -> None:
    print(f"\n== {titulo} ==")


def _relatar_metricas(resultados: list[Resultado], chave_grupo) -> None:
    """Matriz de confusão + macro-F1 + τ, geral, por nível e por grupo."""
    geral = Acumulador()
    por_nivel: dict[int, Acumulador] = defaultdict(Acumulador)
    por_grupo: dict[str, Acumulador] = defaultdict(Acumulador)
    for r in resultados:
        geral.acumular(r)
        por_nivel[r.gold.nivel].acumular(r)
        por_grupo[str(chave_grupo(r))].acumular(r)

    _secao("Matriz de confusão — geral")
    print(_tabela_confusao(geral))
    print(_resumo_metrica(geral))
    for nivel in sorted(por_nivel):
        _secao(f"Matriz de confusão — nível {nivel}")
        print(_tabela_confusao(por_nivel[nivel]))
        print(_resumo_metrica(por_nivel[nivel]))
    if len(por_nivel) == 2:
        s1, s2 = por_nivel[1].s(), por_nivel[2].s()
        print(f"\nfinal (1×N1 + 2×N2)/3 sem bônus de confiança = {(s1 + 2 * s2) / 3:.3f}")
    for grupo in sorted(por_grupo):
        _secao(f"Matriz de confusão — {grupo}")
        print(_tabela_confusao(por_grupo[grupo]))
        print(_resumo_metrica(por_grupo[grupo]))

    casos_tau = [r for r in resultados if r.categoria == "erro_tau"]
    _secao(f"Casos de τ (inventada → real): {len(casos_tau)}")
    for r in casos_tau:
        print(
            f"  N{r.gold.nivel} {r.gold.documento_id} {r.gold.citacao_id} "
            f"[{r.estado.metodo_busca}/{r.saida['metodo_decisao']}] "
            f"id_pred={r.saida['id_canonico']} {r.gold.trecho!r}"
        )


def _histograma_metodo_decisao(resultados: list[Resultado]) -> None:
    _secao("Histograma de metodo_decisao (geral e por metodo_busca)")
    grupos = sorted({str(r.estado.metodo_busca) for r in resultados})
    cab = "metodo_decisao".ljust(22) + "geral".rjust(8) + "".join(g.rjust(12) for g in grupos)
    print(cab)
    for m in METODOS_DECISAO:
        linha = m.ljust(22) + str(
            sum(1 for r in resultados if r.saida["metodo_decisao"] == m)
        ).rjust(8)
        for g in grupos:
            n = sum(
                1
                for r in resultados
                if r.saida["metodo_decisao"] == m and str(r.estado.metodo_busca) == g
            )
            linha += str(n).rjust(12)
        print(linha)


def _escrever_csv_erros(resultados: list[Resultado], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    colunas = [
        "categoria",
        "nivel",
        "documento_id",
        "citacao_id",
        "fatia",
        "trecho",
        "tipo_gold",
        "classificacao_gold",
        "id_gold",
        "classificacao_pred",
        "id_pred",
        "tipo_pred",
        "metodo_busca",
        "metodo_decisao",
        "n_candidatos",
        "n_limpos",
        "ids_candidatos",
        "scores",
        "conflitos_duros",
        "divergencias_brandas",
    ]
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colunas)
        w.writeheader()
        for r in resultados:
            cands = r.estado.candidatos
            w.writerow(
                {
                    "categoria": r.categoria,
                    "nivel": r.gold.nivel,
                    "documento_id": r.gold.documento_id,
                    "citacao_id": r.gold.citacao_id,
                    "fatia": r.rotulo,
                    "trecho": r.gold.trecho.replace("\r", "\\r").replace("\n", "\\n"),
                    "tipo_gold": r.esperado_tipo,
                    "classificacao_gold": r.esperado_classe,
                    "id_gold": r.esperado_id if r.esperado_id is not None else "",
                    "classificacao_pred": r.saida["classificacao"],
                    "id_pred": r.saida["id_canonico"] if r.saida["id_canonico"] is not None else "",
                    "tipo_pred": r.saida["tipo"],
                    "metodo_busca": r.estado.metodo_busca,
                    "metodo_decisao": r.saida["metodo_decisao"],
                    "n_candidatos": len(cands),
                    "n_limpos": sum(1 for c in cands if not c.conflitos_duros),
                    "ids_candidatos": ";".join(str(c.id) for c in cands),
                    "scores": ";".join(f"{c.score:.2f}" for c in cands),
                    "conflitos_duros": ";".join(",".join(c.conflitos_duros) or "-" for c in cands),
                    "divergencias_brandas": ";".join(
                        ",".join(c.divergencias_brandas) or "-" for c in cands
                    ),
                }
            )
    print(f"\nCSV por citação: {caminho}")


# ── modo isolado ────────────────────────────────────────────────────────────


def _candidato_sintetico(
    id_: int, tipo: str, conflitos: tuple[str, ...] = (), score: float = 1.0
) -> Candidato:
    return Candidato(
        id=id_,
        tribunal=None,
        natureza="dispositivo" if tipo == "lei" else "acordao",
        score=score,
        conflitos_duros=conflitos,
    )


def _estado_sintetico(
    g: Gold,
    candidatos: list[Candidato],
    metodo_busca: str | None,
    tem_identificador: bool = True,
) -> EstadoCitacao:
    return EstadoCitacao(
        inicio=g.inicio,
        fim=g.fim,
        trecho=g.trecho,
        tipo_bruto=g.tipo,
        tem_identificador=tem_identificador,
        origem="regex_camada1",
        candidatos=candidatos,
        metodo_busca=metodo_busca,
    )


def _fatias_isoladas(
    gold: list[Gold],
) -> list[tuple[str, Gold, EstadoCitacao, str, int | None, str]]:
    """Cada tupla: (fatia, gold, estado, classe esperada, id esperado,
    metodo_decisao esperado). Ids sintéticos para os empates ficam fora da
    faixa dos ids reais (que têm 10 dígitos)."""
    fatias = []
    contador_incompleta = 0
    for g in gold:
        busca = "lei_sumula" if g.tipo == "lei" else "catalogo"
        if g.classificacao == "real":
            if g.id_canonico is None:
                raise ValueError(f"gabarito: {g.citacao_id} é real sem id_canonico")
            limpo = _candidato_sintetico(g.id_canonico, g.tipo)
            fatias.append(
                (
                    "real_1_limpo",
                    g,
                    _estado_sintetico(g, [limpo], busca),
                    "real",
                    g.id_canonico,
                    "cardinalidade_1",
                )
            )
            # veto: o mesmo id com conflito duro em todo candidato é quimera
            quimera = _candidato_sintetico(g.id_canonico, g.tipo, ("uf",))
            fatias.append(
                (
                    "veto_todos_conflitados",
                    g,
                    _estado_sintetico(g, [quimera], busca),
                    "inventada",
                    None,
                    "veto_quimera",
                )
            )
            # 1 limpo + 2 conflitados: decide pelo limpo
            mistos = [
                _candidato_sintetico(1, g.tipo, ("uf",)),
                limpo,
                _candidato_sintetico(2, g.tipo, ("uf",)),
            ]
            fatias.append(
                (
                    "real_1_limpo_2_conflitados",
                    g,
                    _estado_sintetico(g, mistos, busca),
                    "real",
                    g.id_canonico,
                    "cardinalidade_1",
                )
            )
        elif g.classificacao == "inventada":
            fatias.append(
                (
                    "inventada_0_candidatos",
                    g,
                    _estado_sintetico(g, [], busca),
                    "inventada",
                    None,
                    "cardinalidade_0",
                )
            )
            quimera = _candidato_sintetico(3, g.tipo, ("uf",))
            fatias.append(
                (
                    "inventada_quimera",
                    g,
                    _estado_sintetico(g, [quimera], busca),
                    "inventada",
                    None,
                    "veto_quimera",
                )
            )
        else:
            # alterna entre os três jeitos de chegar a incompleta
            forma = contador_incompleta % 3
            contador_incompleta += 1
            if forma == 0:
                estado = _estado_sintetico(g, [], "sem_busca", tem_identificador=False)
                fatias.append(
                    ("incompleta_sem_busca", g, estado, "incompleta", None, "sem_identificador")
                )
            elif forma == 1:
                estado = _estado_sintetico(g, [], None, tem_identificador=False)
                fatias.append(
                    ("incompleta_metodo_none", g, estado, "incompleta", None, "sem_identificador")
                )
            else:
                empate = [_candidato_sintetico(4, g.tipo), _candidato_sintetico(5, g.tipo)]
                estado = _estado_sintetico(g, empate, busca)
                fatias.append(
                    (
                        "incompleta_2mais_limpos",
                        g,
                        estado,
                        "incompleta",
                        None,
                        "cardinalidade_2mais",
                    )
                )
    return fatias


# Ids sintéticos das fatias de juiz, fora da faixa dos ids reais; o
# `JuizFalso` responde pelo conjunto oferecido, então cada fatia tem o seu.
IDS_JUIZ_VALIDO = (101, 102)
IDS_JUIZ_FORA = (103, 104)
IDS_JUIZ_INDECISO = (105, 106)
ID_FORA_DA_LISTA = 999
JUIZ_FALSO_ISOLADO = JuizFalso(
    {
        frozenset(IDS_JUIZ_VALIDO): IDS_JUIZ_VALIDO[0],
        frozenset(IDS_JUIZ_FORA): ID_FORA_DA_LISTA,
        frozenset(IDS_JUIZ_INDECISO): None,
    }
)


@dataclass(frozen=True)
class FatiaDesempate:
    """Uma entrada do bloco de desempate/juiz: além do esperado, carrega os
    parâmetros e o oráculo de duplicatas com que `decidir` deve rodar."""

    nome: str
    gold: Gold
    estado: EstadoCitacao
    classe: str
    id_esperado: int | None
    metodo: str
    parametros: ParametrosDecisao
    duplicatas: Duplicatas = SemDuplicatas()


def _fatias_desempate(gold: list[Gold], juiz_ligado: bool) -> list[FatiaDesempate]:
    """Bloco à parte: desempates determinísticos e os três desfechos do
    juiz. Com o juiz desligado, as fatias de juiz esperam `incompleta` /
    `cardinalidade_2mais` — prova de que o backend não é consultado."""
    fatias: list[FatiaDesempate] = []
    com_juiz = ParametrosDecisao(habilitar_juiz=juiz_ligado)
    com_score = ParametrosDecisao(habilitar_desempate_score=True)
    com_score_e_margem = ParametrosDecisao(habilitar_desempate_score=True, margem_minima=0.5)
    for g in gold:
        busca = "lei_sumula" if g.tipo == "lei" else "catalogo"
        if g.classificacao == "real" and g.id_canonico is not None:
            # 1a: o id do gabarito e um "clone" de texto com id maior → menor id
            clone = g.id_canonico + 1
            dup = DuplicatasPorAssinatura(
                {g.id_canonico: f"sha-{g.citacao_id}", clone: f"sha-{g.citacao_id}"}
            )
            estado = _estado_sintetico(
                g,
                [_candidato_sintetico(clone, g.tipo), _candidato_sintetico(g.id_canonico, g.tipo)],
                busca,
            )
            fatias.append(
                FatiaDesempate(
                    "desempate_duplicata",
                    g,
                    estado,
                    "real",
                    g.id_canonico,
                    "desempate_duplicata",
                    ParametrosDecisao(),
                    dup,
                )
            )
            # 1b: gabarito com score 1.0 contra 0.7 → maior score (só com a flag)
            empate_score = [
                _candidato_sintetico(7, g.tipo, score=0.7),
                _candidato_sintetico(g.id_canonico, g.tipo, score=1.0),
            ]
            fatias.append(
                FatiaDesempate(
                    "desempate_score_ligado",
                    g,
                    _estado_sintetico(g, empate_score, busca),
                    "real",
                    g.id_canonico,
                    "desempate_score",
                    com_score,
                )
            )
            fatias.append(
                FatiaDesempate(
                    "desempate_score_desligado",
                    g,
                    _estado_sintetico(g, empate_score, busca),
                    "incompleta",
                    None,
                    "cardinalidade_2mais",
                    ParametrosDecisao(),
                )
            )
            fatias.append(
                FatiaDesempate(
                    "desempate_score_margem_insuficiente",
                    g,
                    _estado_sintetico(g, empate_score, busca),
                    "incompleta",
                    None,
                    "cardinalidade_2mais",
                    com_score_e_margem,
                )
            )
        elif g.classificacao == "incompleta":
            for nome, ids, classe, id_esp in (
                ("juiz_id_valido", IDS_JUIZ_VALIDO, "real", IDS_JUIZ_VALIDO[0]),
                ("juiz_id_fora_da_lista", IDS_JUIZ_FORA, "incompleta", None),
                ("juiz_indeciso", IDS_JUIZ_INDECISO, "incompleta", None),
            ):
                estado = _estado_sintetico(g, [_candidato_sintetico(i, g.tipo) for i in ids], busca)
                if juiz_ligado:
                    fatias.append(FatiaDesempate(nome, g, estado, classe, id_esp, "juiz", com_juiz))
                else:
                    fatias.append(
                        FatiaDesempate(
                            nome, g, estado, "incompleta", None, "cardinalidade_2mais", com_juiz
                        )
                    )
    return fatias


def _conferir(resultados: list[Resultado]) -> list[Resultado]:
    return [
        r
        for r in resultados
        if not (
            r.categoria == "acerto"
            and r.saida["metodo_decisao"] == r.esperado_metodo
            and r.saida["tipo"] == r.esperado_tipo
        )
    ]


def _imprimir_erros(erros: list[Resultado]) -> None:
    for r in erros:
        print(
            f"  ERRO {r.rotulo} {r.gold.documento_id} {r.gold.citacao_id}: esperado "
            f"{r.esperado_classe}/{r.esperado_id}/{r.esperado_tipo}/{r.esperado_metodo}, "
            f"obtido {r.saida}"
        )


def _precisao_do_juiz(resultados: list[Resultado]) -> None:
    """Entre as saídas com `metodo_decisao="juiz"`: quantas o juiz decidiu,
    quantas com o id certo, quantas erradas e quantas ficaram indecisas.
    Id fora da lista já foi descartado por `decidir` e conta como indecisa
    — é exatamente a proteção de τ."""
    do_juiz = [r for r in resultados if r.saida["metodo_decisao"] == "juiz"]
    decididas = [r for r in do_juiz if r.saida["id_canonico"] is not None]
    certas = [r for r in decididas if r.saida["id_canonico"] == r.esperado_id]
    _secao("Precisão do juiz (só saídas com metodo_decisao=juiz)")
    print(
        f"consultadas: {len(do_juiz)}  decididas: {len(decididas)}  indecisas: {len(do_juiz) - len(decididas)}"
    )
    if decididas:
        print(
            f"id certo: {len(certas)}  id errado: {len(decididas) - len(certas)}  "
            f"precisão = {len(certas) / len(decididas):.3f}"
        )
    tau = [r for r in decididas if r.esperado_classe == "inventada"]
    print(f"decididas sobre gold inventada (τ): {len(tau)}")


def modo_isolado(gold: list[Gold], pasta_saida: Path, juiz_ligado: bool) -> int:
    _secao("MODO ISOLADO — entradas sintéticas derivadas do gabarito")
    resultados: list[Resultado] = []
    for fatia, g, estado, classe, id_esp, metodo in _fatias_isoladas(gold):
        saida = decidir(estado, ParametrosDecisao())
        resultados.append(Resultado(g, fatia, estado, saida, classe, id_esp, g.tipo, metodo))

    por_fatia: Counter = Counter(r.rotulo for r in resultados)
    erros = _conferir(resultados)
    print(f"{len(resultados)} entradas sintéticas em {len(por_fatia)} fatias:")
    for fatia, n in sorted(por_fatia.items()):
        print(f"  {fatia.ljust(36)} {n:4d}")
    _relatar_metricas(resultados, chave_grupo=lambda r: r.estado.metodo_busca)
    _histograma_metodo_decisao(resultados)

    _secao(
        f"Acertos exatos (classe + id + tipo + metodo_decisao): {len(resultados) - len(erros)}/{len(resultados)}"
    )
    _imprimir_erros(erros)
    _escrever_csv_erros(resultados, pasta_saida / "avalia_decisao_isolado.csv")

    # ── bloco à parte: desempates determinísticos e juiz ──
    _secao(f"MODO ISOLADO — desempates e juiz (juiz {'falso' if juiz_ligado else 'desligado'})")
    resultados_d: list[Resultado] = []
    for f in _fatias_desempate(gold, juiz_ligado):
        saida = decidir(f.estado, f.parametros, JUIZ_FALSO_ISOLADO, f.duplicatas)
        resultados_d.append(
            Resultado(
                f.gold, f.nome, f.estado, saida, f.classe, f.id_esperado, f.gold.tipo, f.metodo
            )
        )
    por_fatia_d: Counter = Counter(r.rotulo for r in resultados_d)
    erros_d = _conferir(resultados_d)
    print(f"{len(resultados_d)} entradas sintéticas em {len(por_fatia_d)} fatias:")
    for fatia, n in sorted(por_fatia_d.items()):
        esperado = next(r.esperado_metodo for r in resultados_d if r.rotulo == fatia)
        print(f"  {fatia.ljust(36)} {n:4d}   esperado: {esperado}")
    _histograma_metodo_decisao(resultados_d)
    _precisao_do_juiz(resultados_d)
    _secao(
        f"Acertos exatos (classe + id + tipo + metodo_decisao): {len(resultados_d) - len(erros_d)}/{len(resultados_d)}"
    )
    _imprimir_erros(erros_d)
    _escrever_csv_erros(resultados_d, pasta_saida / "avalia_decisao_isolado_desempate.csv")
    return 1 if (erros or erros_d) else 0


# ── modo integrado ──────────────────────────────────────────────────────────


def _carregar_catalogo(pasta_dados: Path, pasta_artifacts: Path) -> CatalogoCanonico:
    cache = pasta_artifacts / NOME_CACHE_CATALOGO
    if cache.exists():
        inicio = time.perf_counter()
        catalogo = carregar(cache)
        print(f"catálogo carregado do cache {cache} em {time.perf_counter() - inicio:.1f}s")
        return catalogo
    db = pasta_dados / "desafio1_bracis.db"
    print(f"construindo catálogo a partir de {db} (demora; será cacheado em {cache})...")
    inicio = time.perf_counter()
    catalogo = construir_catalogo_de_arquivo(db)
    pasta_artifacts.mkdir(parents=True, exist_ok=True)
    salvar(catalogo, cache)
    print(f"catálogo construído em {time.perf_counter() - inicio:.1f}s")
    return catalogo


def _carregar_assinaturas(pasta_dados: Path, pasta_artifacts: Path) -> DuplicatasPorAssinatura:
    """Assinatura de conteúdo (sha1 do `texto`) por id, lida da base em modo
    somente leitura e cacheada ao lado do catálogo. É o oráculo do
    desempate 1a — em produção teria de vir do catálogo (pedido ao M3)."""
    cache = pasta_artifacts / NOME_CACHE_ASSINATURAS
    if cache.exists():
        with open(cache, encoding="utf-8") as f:
            return DuplicatasPorAssinatura({int(k): v for k, v in json.load(f).items()})
    db = pasta_dados / "desafio1_bracis.db"
    conexao = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        assinaturas = {
            int(id_): hashlib.sha1(texto.encode("utf-8")).hexdigest()
            for id_, texto in conexao.execute("SELECT id, texto FROM documentos")
        }
    finally:
        conexao.close()
    pasta_artifacts.mkdir(parents=True, exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in assinaturas.items()}, f)
    return DuplicatasPorAssinatura(assinaturas)


@dataclass(frozen=True)
class JuizOraculo:
    """Teto do juiz no integrado: devolve o id do gabarito se ele estiver
    entre os candidatos, senão `None`. Mede o máximo que um juiz perfeito
    mudaria — não é um juiz de verdade."""

    gold_por_trecho: dict[tuple[str, int, int], int | None]

    def escolher(self, estado: EstadoCitacao, candidatos) -> int | None:
        esperado = self.gold_por_trecho.get((estado.trecho, estado.inicio, estado.fim))
        return esperado if esperado in {c.id for c in candidatos} else None


def _aplicar(estado: EstadoCitacao, atualizacao: dict) -> None:
    for chave, valor in atualizacao.items():
        setattr(estado, chave, valor)


def _estado_oraculo(g: Gold) -> EstadoCitacao:
    """Extração-oráculo: offsets, trecho e `tipo_bruto` do gabarito.
    `tem_identificador` não está no gabarito; a aproximação é "há algum
    dígito no trecho" — o Módulo 2/3 já rejeitam número com menos de 5
    dígitos, então uma menção vaga com ano cai em `sem_busca` do mesmo
    jeito que cairia com `tem_identificador=False`."""
    return EstadoCitacao(
        inicio=g.inicio,
        fim=g.fim,
        trecho=g.trecho,
        tipo_bruto=g.tipo,
        tem_identificador=any(c.isdigit() for c in g.trecho),
        origem="regex_camada1",
    )


def modo_integrado(
    gold: list[Gold],
    pasta_dados: Path,
    pasta_artifacts: Path,
    pasta_saida: Path,
    juiz_ligado: bool,
) -> int:
    _secao("MODO INTEGRADO — gabarito como oráculo de extração → M2 → M3 → M4")
    catalogo = _carregar_catalogo(pasta_dados, pasta_artifacts)
    assinaturas = _carregar_assinaturas(pasta_dados, pasta_artifacts)
    colisoes = catalogo.relatorio_colisoes()
    print(
        f"catálogo: {len(catalogo.registros)} registros, {len(catalogo.por_chave)} chaves de "
        f"jurisprudência, {len(catalogo.leis_sumulas)} leis/súmulas, "
        f"{len(colisoes)} colisões"
    )
    colisoes_duplicata = sum(
        1 for ids in colisoes.values() if len({assinaturas.assinatura(i) for i in ids}) == 1
    )
    grupos = Counter(assinaturas.assinaturas.values())
    print(
        f"colisões cujos registros são o mesmo texto: {colisoes_duplicata}/{len(colisoes)}; "
        f"grupos de texto duplicado na base inteira: {sum(1 for n in grupos.values() if n > 1)} "
        f"({sum(n for n in grupos.values() if n > 1)} registros)"
    )

    # A passada principal é fiel à produção: sem oráculo de duplicatas
    # (o catálogo não expõe hash) e juiz conforme `--juiz`.
    juiz: Juiz = JuizDesligado()
    if juiz_ligado:
        juiz = JuizOraculo({(g.trecho, g.inicio, g.fim): g.id_canonico for g in gold})
    parametros = ParametrosDecisao(habilitar_juiz=juiz_ligado)
    print(
        f"decidir com: {parametros}, juiz={'oráculo do gabarito' if juiz_ligado else 'desligado'}"
    )

    resultados: list[Resultado] = []
    for g in gold:
        estado = _estado_oraculo(g)
        _aplicar(estado, normalizar(estado))
        _aplicar(estado, resolver(estado, catalogo))
        saida = decidir(estado, parametros, juiz)
        resultados.append(
            Resultado(g, "gabarito", estado, saida, g.classificacao, g.id_canonico, g.tipo)
        )

    print(f"{len(resultados)} citações do gabarito (edital: 225; faltam as demais incompletas)")
    print(f"por classe: {dict(Counter(g.classificacao for g in gold))}")
    print(f"por tipo:   {dict(Counter(g.tipo for g in gold))}")

    _relatar_metricas(resultados, chave_grupo=lambda r: f"metodo_busca={r.estado.metodo_busca}")
    _histograma_metodo_decisao(resultados)
    if juiz_ligado:
        _precisao_do_juiz(resultados)
    _diagnosticos(resultados)
    _diagnostico_desempate_e_juiz(resultados, gold, assinaturas)
    _escrever_csv_erros(resultados, pasta_saida / "avalia_decisao_integrado.csv")
    return 0


def _macro_f1_de(resultados: list[Resultado], saidas: dict[str, dict]) -> Acumulador:
    """Acumulador com as saídas substituídas por `saidas` (chave: citacao_id)."""
    acc = Acumulador()
    for r in resultados:
        clone = Resultado(
            r.gold,
            r.rotulo,
            r.estado,
            saidas.get(r.gold.citacao_id, r.saida),
            r.esperado_classe,
            r.esperado_id,
            r.esperado_tipo,
        )
        acc.acumular(clone)
    return acc


def _diagnostico_desempate_e_juiz(
    resultados: list[Resultado], gold: list[Gold], assinaturas: DuplicatasPorAssinatura
) -> None:
    """Contrafactuais sobre os mesmos estados: o que cada alavanca do ramo
    2+ mudaria hoje, e a projeção de impacto de um juiz perfeito."""
    _secao("Diagnóstico — ramo 2+: desempates e juiz (contrafactuais)")
    base = Acumulador()
    for r in resultados:
        base.acumular(r)

    empates = [
        r
        for r in resultados
        if len({c.id for c in r.estado.candidatos if not c.conflitos_duros}) >= 2
    ]
    print(f"citações que entram no ramo 2+ (ids limpos distintos ≥ 2): {len(empates)}")

    # (a) duplicata de conteúdo, com as assinaturas da base
    por_dup = {
        r.gold.citacao_id: decidir(r.estado, ParametrosDecisao(), duplicatas=assinaturas)
        for r in empates
    }
    n_dup = sum(1 for s in por_dup.values() if s["metodo_decisao"] == "desempate_duplicata")
    # (b) margem de score (margem mínima 0: qualquer diferença estrita)
    por_score = {
        r.gold.citacao_id: decidir(
            r.estado,
            ParametrosDecisao(habilitar_desempate_score=True),
            duplicatas=assinaturas,
        )
        for r in empates
    }
    n_score = sum(1 for s in por_score.values() if s["metodo_decisao"] == "desempate_score")
    # (c) o que sobra para o juiz depois de (a) e (b)
    restam = [
        r
        for r in empates
        if por_score[r.gold.citacao_id]["metodo_decisao"] == "cardinalidade_2mais"
    ]
    print(f"resolvidas antes do juiz por duplicata de conteúdo: {n_dup}")
    print(f"resolvidas antes do juiz por margem de score:       {n_score}")
    print(f"chegariam ao juiz hoje (sobra de 1a e 1b):          {len(restam)}")
    for r in restam:
        ids = ";".join(str(c.id) for c in r.estado.candidatos)
        print(
            f"    {r.gold.citacao_id} gold={r.esperado_classe}/{r.esperado_id} ids={ids} {r.gold.trecho!r}"
        )

    # projeção: todo cardinalidade_2mais vira real com o id certo (quando o
    # gabarito é real e o id está entre os candidatos); gold inventada em
    # empate viraria... `incompleta` continua (juiz perfeito diz None).
    projecao: dict[str, dict] = {}
    n_real_recuperavel = 0
    for r in resultados:
        if r.saida["metodo_decisao"] != "cardinalidade_2mais":
            continue
        ids = {c.id for c in r.estado.candidatos if not c.conflitos_duros}
        if r.esperado_classe == "real" and r.esperado_id in ids:
            n_real_recuperavel += 1
            projecao[r.gold.citacao_id] = {
                **r.saida,
                "classificacao": "real",
                "id_canonico": r.esperado_id,
                "metodo_decisao": "juiz",
            }
    proj = _macro_f1_de(resultados, projecao)
    print(
        f"projeção (juiz perfeito): {n_real_recuperavel} gold real recuperáveis em cardinalidade_2mais; "
        f"macro-F1 {base.macro_f1():.3f} → {proj.macro_f1():.3f} "
        f"(Δ = {proj.macro_f1() - base.macro_f1():+.3f}); τ {base.tau():.3f} → {proj.tau():.3f}"
    )
    # e o pior caso: juiz chuta em todo empate (id errado / real em inventada)
    pior: dict[str, dict] = {}
    for r in resultados:
        if r.saida["metodo_decisao"] != "cardinalidade_2mais":
            continue
        ids = sorted(c.id for c in r.estado.candidatos if not c.conflitos_duros)
        errado = next((i for i in ids if i != r.esperado_id), ids[0])
        pior[r.gold.citacao_id] = {
            **r.saida,
            "classificacao": "real",
            "id_canonico": errado,
            "metodo_decisao": "juiz",
        }
    pior_acc = _macro_f1_de(resultados, pior)
    print(
        f"pior caso (juiz chuta errado em todo empate): macro-F1 → {pior_acc.macro_f1():.3f} "
        f"(Δ = {pior_acc.macro_f1() - base.macro_f1():+.3f}); τ → {pior_acc.tau():.3f}"
    )


def _diagnosticos(resultados: list[Resultado]) -> None:
    _secao("Diagnóstico — o que chega ao Módulo 4")

    reais = [r for r in resultados if r.esperado_classe == "real"]
    c0 = [r for r in reais if r.saida["metodo_decisao"] == "cardinalidade_0"]
    print(f"gold `real` total: {len(reais)}")
    print(
        f"gold `real` em cardinalidade_0 (defeito do M3, chave não resolve): {len(c0)}  "
        f"por metodo_busca: {dict(Counter(str(r.estado.metodo_busca) for r in c0))}"
    )
    sem_id = [r for r in reais if r.saida["metodo_decisao"] == "sem_identificador"]
    print(f"gold `real` em sem_identificador (<5 dígitos ou sem número buscável): {len(sem_id)}")
    for r in sem_id:
        print(f"    {r.gold.documento_id} {r.gold.citacao_id} {r.gold.trecho!r}")
    c1 = [r for r in reais if r.saida["metodo_decisao"] == "cardinalidade_1"]
    certos = sum(1 for r in c1 if r.saida["id_canonico"] == r.esperado_id)
    print(
        f"gold `real` em cardinalidade_1: {len(c1)} (id certo: {certos}, id errado: {len(c1) - certos})"
    )

    _secao("Diagnóstico — cardinalidade_1 vindas de lei_sumula com score 1.0 e zero conflitos")
    lei_c1 = [
        r
        for r in resultados
        if r.estado.metodo_busca == "lei_sumula"
        and r.saida["metodo_decisao"] == "cardinalidade_1"
        and all(c.score == 1.0 and not c.conflitos_duros for c in r.estado.candidatos)
    ]
    print(f"total: {len(lei_c1)}")
    for r in lei_c1:
        marca = "OK " if r.categoria == "acerto" else f"{r.categoria.upper()}"
        print(
            f"    [{marca}] N{r.gold.nivel} {r.gold.documento_id} {r.gold.citacao_id} gold="
            f"{r.esperado_classe}/{r.esperado_id} pred=real/{r.saida['id_canonico']} {r.gold.trecho!r}"
        )
    lei_empate = [
        r
        for r in resultados
        if r.estado.metodo_busca == "lei_sumula"
        and r.saida["metodo_decisao"] == "cardinalidade_2mais"
    ]
    com_score_distinto = [
        r
        for r in lei_empate
        if len({c.score for c in r.estado.candidatos if not c.conflitos_duros}) > 1
    ]
    print(
        f"lei_sumula em cardinalidade_2mais: {len(lei_empate)}; destes, com scores distintos "
        f"entre os limpos (o score discriminaria): {len(com_score_distinto)}"
    )
    for r in com_score_distinto:
        scores = ";".join(f"{c.id}:{c.score:.1f}" for c in r.estado.candidatos)
        print(
            f"    N{r.gold.nivel} {r.gold.citacao_id} gold={r.esperado_classe}/{r.esperado_id} {scores} {r.gold.trecho!r}"
        )

    _secao("Diagnóstico — veto e divergências brandas")
    vetos = [r for r in resultados if r.saida["metodo_decisao"] == "veto_quimera"]
    print(f"veto_quimera: {len(vetos)}")
    for r in vetos:
        print(f"    {r.gold.citacao_id} gold={r.esperado_classe} {r.gold.trecho!r}")
    com_duro = [r for r in resultados if any(c.conflitos_duros for c in r.estado.candidatos)]
    print(f"citações com algum candidato em conflito duro: {len(com_duro)}")
    com_brandas = [
        r for r in resultados if any(c.divergencias_brandas for c in r.estado.candidatos)
    ]
    n_cand_brandas = sum(
        1 for r in resultados for c in r.estado.candidatos if c.divergencias_brandas
    )
    print(
        f"citações com candidato de divergências_brandas não vazias: {len(com_brandas)} "
        f"({n_cand_brandas} candidatos); por atributo: "
        f"{dict(Counter(a for r in resultados for c in r.estado.candidatos for a in c.divergencias_brandas))}"
    )
    for r in com_brandas:
        detalhe = ";".join(
            f"{c.id}:{','.join(c.divergencias_brandas)}" for c in r.estado.candidatos
        )
        print(
            f"    {r.gold.citacao_id} gold={r.esperado_classe}/{r.esperado_id} pred={r.saida['classificacao']}/{r.saida['id_canonico']} {detalhe} {r.gold.trecho!r}"
        )

    _secao("Diagnóstico — tipo")
    tipo_default = sum(
        1
        for r in resultados
        if r.estado.tipo_bruto == "indefinido" and r.saida["id_canonico"] is None
    )
    tipo_errado = [r for r in resultados if r.saida["tipo"] != r.esperado_tipo]
    print(f"tipo por default (tipo_bruto indefinido sem candidato): {tipo_default}")
    print(f"tipo diferente do gabarito: {len(tipo_errado)}")
    for r in tipo_errado:
        print(
            f"    {r.gold.citacao_id} gold={r.esperado_tipo} pred={r.saida['tipo']} {r.gold.trecho!r}"
        )

    _secao("Diagnóstico — cardinalidade bruta por metodo_busca")
    for busca in sorted({str(r.estado.metodo_busca) for r in resultados}):
        dist = Counter(
            len({c.id for c in r.estado.candidatos if not c.conflitos_duros})
            for r in resultados
            if str(r.estado.metodo_busca) == busca
        )
        print(f"  {busca.ljust(12)} ids limpos distintos → citações: {dict(sorted(dist.items()))}")


# ── cli ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dados",
        type=Path,
        required=True,
        help="pasta com goldenset.csv, txt/ e desafio1_bracis.db",
    )
    parser.add_argument("--modo", choices=("isolado", "integrado", "ambos"), default="ambos")
    parser.add_argument(
        "--juiz",
        choices=("desligado", "falso"),
        default="desligado",
        help="`falso` liga o juiz com JuizFalso (isolado) / oráculo do gabarito (integrado); "
        "nenhum modo carrega pesos aqui",
    )
    parser.add_argument(
        "--artifacts", type=Path, default=RAIZ / "artifacts", help="cache do catálogo (gitignored)"
    )
    parser.add_argument(
        "--saida", type=Path, default=RAIZ / "outputs", help="CSVs por citação (gitignored)"
    )
    args = parser.parse_args(argv)

    gold = ler_gabarito(args.dados)
    juiz_ligado = args.juiz == "falso"
    codigo = 0
    if args.modo in ("isolado", "ambos"):
        codigo |= modo_isolado(gold, args.saida, juiz_ligado)
    if args.modo in ("integrado", "ambos"):
        codigo |= modo_integrado(gold, args.dados, args.artifacts, args.saida, juiz_ligado)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
