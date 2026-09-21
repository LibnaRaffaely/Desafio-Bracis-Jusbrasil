"""Avaliação do Módulo 4 (`nos/decidir.py`) contra o goldenset. Só biblioteca
padrão além do próprio pacote.

Uso:
    python scripts/avalia_decisao.py --dados /caminho/da/pasta_do_desafio
    python scripts/avalia_decisao.py --dados ... --modo isolado
    python scripts/avalia_decisao.py --dados ... --modo integrado

Modos (docs/avaliacao.md, modo `resolucao`):

- `isolado`: entradas sintéticas derivadas do gabarito (gold `real` -> 1
  candidato limpo com o id do gabarito; `inventada` -> 0 candidatos;
  `incompleta` -> sem busca ou 2+ candidatos limpos), mais uma fatia com
  conflitos duros para exercitar o veto. Mede só o Módulo 4: tem de dar
  100%, senão o defeito é do nó de decisão. Sai com código 1 se não der.
- `integrado`: spans do gabarito como extração-oráculo -> `normalizar`
  (Módulo 2) -> `resolver` (Módulo 3, catálogo real) -> `decidir`. Tudo
  reportado separado por `metodo_busca`, porque o caminho de lei/súmula e o
  de jurisprudência têm defeitos independentes a montante.

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
from citacoes.nos.decidir import ParametrosDecisao, decidir  # noqa: E402
from citacoes.nos.normalizar import normalizar  # noqa: E402

CLASSES = ("real", "inventada", "incompleta")
METODOS_DECISAO = (
    "sem_identificador",
    "cardinalidade_0",
    "cardinalidade_1",
    "cardinalidade_2mais",
    "veto_quimera",
    "juiz",
)
GAMMA = 0.5
NOME_CACHE_CATALOGO = "catalogo_canonico.json"


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


def _candidato_sintetico(id_: int, tipo: str, conflitos: tuple[str, ...] = ()) -> Candidato:
    return Candidato(
        id=id_,
        tribunal=None,
        natureza="dispositivo" if tipo == "lei" else "acordao",
        score=1.0,
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


def modo_isolado(gold: list[Gold], pasta_saida: Path) -> int:
    _secao("MODO ISOLADO — entradas sintéticas derivadas do gabarito")
    resultados: list[Resultado] = []
    for fatia, g, estado, classe, id_esp, metodo in _fatias_isoladas(gold):
        saida = decidir(estado, ParametrosDecisao())
        resultados.append(Resultado(g, fatia, estado, saida, classe, id_esp, g.tipo, metodo))

    por_fatia: Counter = Counter()
    erros: list[Resultado] = []
    for r in resultados:
        por_fatia[r.rotulo] += 1
        ok = (
            r.categoria == "acerto"
            and r.saida["metodo_decisao"] == r.esperado_metodo
            and r.saida["tipo"] == r.esperado_tipo
        )
        if not ok:
            erros.append(r)
    print(f"{len(resultados)} entradas sintéticas em {len(por_fatia)} fatias:")
    for fatia, n in sorted(por_fatia.items()):
        print(f"  {fatia.ljust(30)} {n:4d}")
    _relatar_metricas(resultados, chave_grupo=lambda r: r.estado.metodo_busca)
    _histograma_metodo_decisao(resultados)

    _secao(
        f"Acertos exatos (classe + id + tipo + metodo_decisao): {len(resultados) - len(erros)}/{len(resultados)}"
    )
    for r in erros:
        print(
            f"  ERRO {r.rotulo} {r.gold.documento_id} {r.gold.citacao_id}: esperado "
            f"{r.esperado_classe}/{r.esperado_id}/{r.esperado_tipo}/{r.esperado_metodo}, "
            f"obtido {r.saida}"
        )
    _escrever_csv_erros(resultados, pasta_saida / "avalia_decisao_isolado.csv")
    return 1 if erros else 0


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
    gold: list[Gold], pasta_dados: Path, pasta_artifacts: Path, pasta_saida: Path
) -> int:
    _secao("MODO INTEGRADO — gabarito como oráculo de extração → M2 → M3 → M4")
    catalogo = _carregar_catalogo(pasta_dados, pasta_artifacts)
    print(
        f"catálogo: {len(catalogo.registros)} registros, {len(catalogo.por_chave)} chaves de "
        f"jurisprudência, {len(catalogo.leis_sumulas)} leis/súmulas, "
        f"{len(catalogo.relatorio_colisoes())} colisões"
    )

    resultados: list[Resultado] = []
    for g in gold:
        estado = _estado_oraculo(g)
        _aplicar(estado, normalizar(estado))
        _aplicar(estado, resolver(estado, catalogo))
        saida = decidir(estado, ParametrosDecisao())
        resultados.append(
            Resultado(g, "gabarito", estado, saida, g.classificacao, g.id_canonico, g.tipo)
        )

    print(f"{len(resultados)} citações do gabarito (edital: 225; faltam as demais incompletas)")
    print(f"por classe: {dict(Counter(g.classificacao for g in gold))}")
    print(f"por tipo:   {dict(Counter(g.tipo for g in gold))}")

    _relatar_metricas(resultados, chave_grupo=lambda r: f"metodo_busca={r.estado.metodo_busca}")
    _histograma_metodo_decisao(resultados)
    _diagnosticos(resultados)
    _escrever_csv_erros(resultados, pasta_saida / "avalia_decisao_integrado.csv")
    return 0


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
        "--artifacts", type=Path, default=RAIZ / "artifacts", help="cache do catálogo (gitignored)"
    )
    parser.add_argument(
        "--saida", type=Path, default=RAIZ / "outputs", help="CSVs por citação (gitignored)"
    )
    args = parser.parse_args(argv)

    gold = ler_gabarito(args.dados)
    codigo = 0
    if args.modo in ("isolado", "ambos"):
        codigo |= modo_isolado(gold, args.saida)
    if args.modo in ("integrado", "ambos"):
        codigo |= modo_integrado(gold, args.dados, args.artifacts, args.saida)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
