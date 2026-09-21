# Relatório — Módulo 4 (Decisão, `nos/decidir.py`)

Duas entregas empilhadas:

- **v1** (branch `modulo4-decisao`, commit `4e87837`): `src/citacoes/nos/decidir.py`
  (+ export em `nos/__init__.py`), `tests/test_nos_decidir.py`,
  `scripts/avalia_decisao.py`, este relatório — seções 1 a 7.
- **v2** (branch `modulo4-juiz`, sobre `modulo4-decisao`): desempate
  determinístico em `decidir.py`, Agente-Juiz em `src/citacoes/agentes/juiz.py`,
  `tests/test_nos_juiz.py`, harness e `pyproject.toml` (grupo opcional
  `juiz`) — seções 8 a 14.

Ambiente de medição v1: Python 3.14 do sistema, venv temporário com
`PYTHONPATH=src`. v2: `uv run` (Python 3.12, `.venv` do repo), sem GPU,
sem `torch` instalado — tudo do juiz testado com `BackendFalso` em CPU.
Dados em pasta externa passada por `--dados`; base aberta em `?mode=ro`.
Catálogo real cacheado em `artifacts/catalogo_canonico.json` (e, na v2,
assinaturas de conteúdo em `artifacts/assinaturas_conteudo.json`), CSVs por
citação em `outputs/` — tudo gitignored.

## 1. O que foi implementado

Função pura `decidir(estado, parametros=ParametrosDecisao(), juiz=JuizDesligado())`
→ `dict` com exatamente `classificacao`, `id_canonico`, `tipo`, `metodo_decisao`.
Ordem das guardas (docs/arquitetura.md, "Regra de decisão"):

1. `metodo_busca in (None, "sem_busca")` → `incompleta` / `sem_identificador`,
   sem olhar candidatos (cobre o roteamento que pula `buscar` e o `sem_busca`
   do Módulo 3 para <5 dígitos).
2. candidatos não vazios e nenhum sem `conflitos_duros` → `inventada` / `veto_quimera`.
3. n = ids distintos entre os limpos: 0 → `inventada`/`cardinalidade_0`;
   1 → `real`/`cardinalidade_1` com `id_canonico = Candidato.id`;
   2+ → `incompleta`/`cardinalidade_2mais`, salvo `habilitar_juiz`
   (na v2, salvo também os desempates da seção 8).
4. Juiz habilitado: `metodo_decisao="juiz"` nos dois desfechos; `None` ou id
   fora dos candidatos → `incompleta`.
5. `tipo`: candidato escolhido → `dispositivo`→`lei`, `acordao`/`sumula`→`jurisprudencia`;
   sem candidato → `tipo_bruto`, e `"indefinido"` → `"jurisprudencia"`.

`score` não é consumido (constante `1.0` em jurisprudência; sem informação de
desempate). `divergencias_brandas` não é consumido — só contado no harness.

Wrapper de nó `decidir_classe(estado, runtime)`: lê apenas `Contexto.usar_juiz`
(flag já documentada em docs/contratos.md); com a flag ligada e
`Contexto.modelo_llm=None` levanta `RuntimeError` (mesmo padrão de
`buscar_no_catalogo`); com modelo, injeta `JuizLLM` (na v1 um esqueleto com
`NotImplementedError`; na v2, a implementação da seção 9).

## 2. Testes

`tests/test_nos_decidir.py`: 32 testes, todos passando — um por ramo, os
casos de borda pedidos (guarda 1 vencendo candidatos populados; `sem_busca`
com `tem_identificador=True`; ids repetidos → n=1; 1 limpo + 2 conflitados →
real; todos conflitados → veto e nunca `cardinalidade_2mais`; `[]` com
`catalogo` e com `lei_sumula` → `cardinalidade_0`; `\n` no trecho; juiz
devolvendo `None`; juiz escolhendo id fora da lista; wrapper com/sem
`usar_juiz`) e quatro propriedades Hypothesis (`real ⟺ id_canonico`;
`id_canonico` é `int` vindo de `Candidato.id`; não muta o estado; sempre as
quatro chaves), mais um teste que bloqueia `sqlite3.connect` e `open`
durante `decidir`.

Suíte inteira: 69 passam, 2 falham — as duas falhas são pré-existentes
(seção 6). `ruff check` e `ruff format --check` passam nos arquivos novos.

## 3. Modo isolado (validação do Módulo 4 sozinho)

451 entradas sintéticas derivadas das 195 linhas do gabarito, em 8 fatias:

| fatia | n | esperado |
|---|---|---|
| `real_1_limpo` | 96 | real / id do gabarito / `cardinalidade_1` |
| `real_1_limpo_2_conflitados` | 96 | real pelo limpo / `cardinalidade_1` |
| `veto_todos_conflitados` | 96 | inventada / `veto_quimera` |
| `inventada_0_candidatos` | 64 | inventada / `cardinalidade_0` |
| `inventada_quimera` | 64 | inventada / `veto_quimera` |
| `incompleta_sem_busca` | 12 | incompleta / `sem_identificador` |
| `incompleta_metodo_none` | 12 | incompleta / `sem_identificador` |
| `incompleta_2mais_limpos` | 11 | incompleta / `cardinalidade_2mais` |

Resultado: **451/451 acertos exatos** (classe + id + tipo + `metodo_decisao`),
macro-F1 = 1,000 e τ = 0 em todos os cortes (geral, por nível, por
`metodo_busca`). O nó faz o que a tabela manda.

## 4. Modo integrado (gabarito → M2 → M3 real → M4)

195 citações do gabarito (edital: 225; faltam 30 incompletas — nada foi
ajustado por isso). Extração-oráculo: offsets/trecho/`tipo_bruto` do
gabarito; `tem_identificador` aproximado por "há dígito no trecho" (o M2/M3
já rejeitam <5 dígitos, então menção vaga com ano cai em `sem_busca` de
qualquer jeito). Catálogo real: 1016 registros, 176 chaves de
jurisprudência, 18 leis/súmulas, 14 colisões; construção 491 s.

### Métrica (semântica de `kaggle_metric.py`)

| corte | macro-F1 | F1 real | F1 inventada | F1 incompleta | τ | s |
|---|---|---|---|---|---|---|
| geral | **0,591** | 0,265 | 0,587 | 0,921 | **0,031** (2/64) | 0,582 |
| nível 1 | 0,606 | 0,262 | 0,585 | 0,971 | 0,031 (1/32) | 0,597 |
| nível 2 | 0,579 | 0,269 | 0,589 | 0,878 | 0,031 (1/32) | 0,570 |
| `metodo_busca=catalogo` (116) | 0,261 | 0,000 | 0,522 | — | 0,000 (0/41) | 0,261 |
| `metodo_busca=lei_sumula` (38) | 0,868 | 0,857 | 0,878 | — | 0,100 (2/20) | 0,824 |
| `metodo_busca=sem_busca` (41) | 0,307 | 0,000 | 0,000 | 0,921 | 0 (0/3) | 0,307 |

Final `(1×N1 + 2×N2)/3` sem bônus de confiança: 0,579.

Matriz de confusão geral (gold nas linhas):

| | real | inventada | incompleta |
|---|---|---|---|
| real (96) | 15 | 78 | 3 |
| inventada (64) | 2 | 59 | 3 |
| incompleta (35) | 0 | 0 | 35 |

### Casos de τ (lista completa — os dois vêm de `lei_sumula` / `cardinalidade_1`, score 1,0, zero conflitos)

1. N1 `gen_n1_002` g9 `art. 1.134 da Lei nº\n13.105/2015` → `real`/11304039
   (art. 1º, I, "g", da LC 64/1990). Verificado com `extrair_campos`: a
   citação sai com `artigo="1"` (a regex `_ARTIGO` para no separador de
   milhar de "1.134") e `diploma=None` ("Lei nº 13.105" não está no léxico
   de diplomas); o registro tem `artigo="1"`, e com `diploma=None` de um
   lado `_score_lei_sumula` pula a checagem de diploma → score 1,0.
2. N2 `gen_n2_007` g2 `art 290 da Constituição\nFederal` → `real`/10590194
   (art. 290 do CPM). A citação sai certa (`diploma="CF"`, `artigo="290"`),
   mas o **registro** do CPM no catálogo está com `diploma=None` (o
   cabeçalho do registro não rendeu diploma na construção) — de novo a
   checagem é pulada e o art. 290 casa com score 1,0. Aliás, a citação
   real `art.\n290 do Código Penal Militar` sai com `diploma="CP"`, então
   nem com o registro preenchido a comparação bateria hoje.

Os dois são exatamente os falsos positivos previstos. Não há fallback no
M4 para eles: a informação que separaria os casos (diploma) não chega até
o nó.

### Histograma de `metodo_decisao`

| metodo_decisao | geral | catalogo | lei_sumula | sem_busca |
|---|---|---|---|---|
| sem_identificador | 41 | 0 | 0 | 41 |
| cardinalidade_0 | 137 | 116 | 21 | 0 |
| cardinalidade_1 | 17 | 0 | 17 | 0 |
| cardinalidade_2mais | **0** | 0 | 0 | 0 |
| veto_quimera | **0** | 0 | 0 | 0 |
| juiz | 0 | 0 | 0 | 0 |

### Contadores de diagnóstico

- gold `real` em `cardinalidade_0`: **78 de 96** (75 via `catalogo`, 3 via
  `lei_sumula`). Impacto direto do defeito do M3 (seção 6). Os 3 de lei:
  `Súmula Vinculante 10` (1289712966), `Súmula 331 do TST` (1431369957),
  `art. 896, § 1º-A, da CLT` (10637358).
- gold `real` em `sem_identificador`: **3** — `Agravo Interno na Suspensão\nde
  Liminar e de Sentença nº 2.883/MA`, `5úmula 211 do STJ`, `AR\nn. 2785 (SP)`
  (todos com <5 dígitos após a normalização; regra documentada, não
  recuperados aqui).
- gold `inventada` em `sem_identificador`: 3 — `Súm. 166 do TSE`,
  `Temã 2.680 da repercussão geral`, `Recl. n° 6G.838/ BA` (preditas
  `incompleta`; erro barato, não conta em τ).
- `cardinalidade_1` de `lei_sumula` com score 1,0 e zero conflitos: **17**
  — 15 reais com id certo (nenhum `id_errado`), 2 são os casos de τ acima.
- `lei_sumula` em `cardinalidade_2mais`: 0 (logo 0 com scores distintos —
  o score não teria discriminado nada neste dev set).
- `veto_quimera`: **0**. Citações com algum candidato em conflito duro: 0.
  Candidatos com `divergencias_brandas` não vazias: 0 (0 citações). Só 1
  dos 998 acórdãos do catálogo tem `uf` preenchida e nenhum acórdão chega a
  candidato — o veto não tem como disparar antes do M3 resolver.
- `tipo` por default (`tipo_bruto` indefinido sem candidato): 0. `tipo`
  diferente do gabarito: 0.
- Cardinalidade bruta de ids limpos por citação: `catalogo` {0: 116};
  `lei_sumula` {0: 21, 1: 17}; `sem_busca` {0: 41}.
- `cardinalidade_1` do gabarito com id errado: 0 — quando o M3 devolve
  um candidato, o id é o certo.

Conferência da conta prévia: trocar `cardinalidade_0 → incompleta` como
salvaguarda mandaria 137 citações (78 reais + 59 inventadas) para
`incompleta` — inflaria a classe e derrubaria o F1 de `inventada` e
`incompleta` sem tocar em τ. A regra literal fica.

## 5. Onde o código/os docs divergiram da tarefa (avisos)

- `estados.py` não tem `Literal` para `classificacao`/`metodo_decisao`
  (são `str | None`); `Classificacao`, `MetodoDecisao` e `TipoCitacao` foram
  definidos em `decidir.py`. `TipoBruto`/`MetodoBusca` vêm de `estados.py`
  e `Natureza` de `esquema.py`.
- `docs/arquitetura.md` (L32-34, L99) e `docs/contratos.md` (L46) preveem o
  juiz como **nó separado** (`agente_juiz` → `escolha_juiz` no estado) e
  `decidir` só lendo o resultado; o campo `escolha_juiz` **não existe** em
  `EstadoCitacao`. Decisão tomada (com a Isadora): juiz como `Protocol`
  injetado em `decidir` na v1. Se o trio quiser voltar ao desenho dos docs,
  o que muda é: adicionar `escolha_juiz` ao estado, a aresta condicional
  em `grafo/`, e `decidir` passar a ler o campo em vez de chamar `juiz.escolher`.
- `Contexto.usar_juiz` já existe; o wrapper o lê. `ParametrosDecisao` não
  entra em `Contexto` — **pergunta em aberto**: se um dia houver mais
  parâmetros que `habilitar_juiz`, onde eles vivem (contexto ou `params/`
  como a tabela de confiança)?
- `tests/test_catalogo_construir.py` aqui **coleta e falha** (não "não
  coleta"): com `PYTHONPATH=src`, `from src.citacoes` importa um segundo
  módulo e as dataclasses não batem.

## 6. Defeitos alheios anotados (não corrigidos)

1. `EstadoDocumento` usa `Annotated` e `operator` sem importar
   (`grafo/estados.py`); `get_type_hints` levanta `NameError` — vai quebrar
   na montagem do grafo.
2. `tests/test_catalogo_construir.py` importa `from src.citacoes...` (falha).
3. `test_propriedade_esqueleto_ruido_igual_esqueleto_original` falha com
   contraexemplo determinístico (`seed=5340538`).
4. `scripts/testar_extracao.py` exige `data/goldenset_offsets.csv`, que não
   existe, e hardcoda `data/`.
5. `ruff` falha em `nos/extrair_spans.py` (I001, UP037) e
   `nos/ler_documento.py` (I001, F401) — Módulo 1.
6. **Catálogo de jurisprudência não resolve (M3/M2, causa dos 75 reais em
   `cardinalidade_0`).** Evidência colhida do `artifacts/catalogo_canonico.json`:
   só 193 dos 998 acórdãos têm `numero_normalizado`; para o registro
   5665364632 (`APL 7000449-40.2023.7.00.0000/RS`, gabarito g6) a chave
   tem milhares de dígitos — `extrair_cabecalho` devolveu o texto inteiro e
   `extrair_campos` concatenou todos os dígitos. Registros do STJ como
   3576055165 (`RHC 57.763/PR`) e 1922829498 ficaram com `classe="Súmula"` e
   `numero_normalizado=None`, porque o corpo menciona uma súmula e a regex
   `_SUMULA` vence antes do número de processo. Só 1 acórdão tem `uf`.
7. Caminho de lei (M2/M3), causa dos dois casos de τ: `_ARTIGO` trunca
   número com separador de milhar (`1.134` → `1`); `diploma_legal` não
   reconhece "Lei nº 13.105/2015" e mapeia "Código Penal Militar" para
   `CP`; registros de dispositivo no catálogo podem ficar com
   `diploma=None`, e `_score_lei_sumula` pula a checagem de diploma quando
   qualquer lado é `None` — artigo de diploma errado passa com score 1,0.

## 7. Recomendação sobre o juiz na v2

**Manter desligado.** Motivos medidos, não estimados:

- `cardinalidade_2mais` = 0 no dev set integrado. No goldenset local,
  0 das 35 incompletas têm ≥5 dígitos: todas caem em `sem_identificador`,
  e o ramo que o juiz atenderia não tem exemplo positivo.
- Enquanto o catálogo de acórdãos não resolver (defeito 6), nenhum acórdão
  vira candidato; o juiz não teria o que desempatar. As 14 colisões do
  catálogo são o único lugar onde empate genuíno poderia surgir, e nenhuma
  foi atingida.
- Os dois erros de τ são `cardinalidade_1` de lei — o juiz, por contrato,
  só atua em 2+ candidatos; não os tocaria.
- O ganho possível do juiz hoje é zero e o custo (GPU, determinismo, um
  agente a validar) é integral. Reavaliar **depois** que o M3 resolver
  jurisprudência: se `cardinalidade_2mais` passar a ter suporte (>0 no dev
  set) e a maioria desses empates for `real` no gabarito, aí vale ligar com
  `Contexto.usar_juiz=True` e implementar `JuizLLM.escolher`.

O sinal de calibração para o Módulo 5 é o histograma da seção 4:
`cardinalidade_1` (17) acertou 15/17 e é o único ramo que emite `real`;
`sem_identificador` acertou 35/41; `cardinalidade_0` hoje mistura 59
inventadas com 78 reais por defeito a montante — a confiança desse ramo
só faz sentido depois do M3 consertado.

---

# v2 — desempate determinístico e Agente-Juiz (branch `modulo4-juiz`)

## 8. O que muda em `decidir` com o desempate

Nada muda nas guardas 1–3 (sem busca, veto, cardinalidade 0/1). No ramo
`n >= 2`, antes do juiz, entram dois passos, nesta ordem:

| passo | condição | resultado | flag |
|---|---|---|---|
| 1a `desempate_duplicata` | todos os ids limpos que sobraram têm a **mesma assinatura de conteúdo** (ids sem assinatura nunca colapsam; grupos parciais só colapsam o grupo) | `real` com o **menor id** do grupo | sempre ativo; sem oráculo (`SemDuplicatas`, o default) nunca dispara |
| 1b `desempate_score` | maior score supera o segundo **estritamente** e por `>= margem_minima` (score de um id = maior entre as suas ocorrências; empate no topo não resolve) | `real` com o maior score | `ParametrosDecisao.habilitar_desempate_score=False`, `margem_minima=0.0` |
| juiz | o que sobrar de 1a/1b, se `habilitar_juiz` | `real`/`incompleta` com `metodo_decisao="juiz"` | `habilitar_juiz=False` |
| senão | — | `incompleta`/`cardinalidade_2mais`, **exatamente como na v1** | — |

Assinatura: `decidir(estado, parametros, juiz, duplicatas=SEM_DUPLICATAS)`.
`Duplicatas` é um Protocol (`assinatura(id) -> str | None`) injetado como o
juiz, com `DuplicatasPorAssinatura({id: hash})` de implementação.

**Por que injetar em vez de "detectar a partir do `Candidato` ou do
catálogo"**: nem `Candidato` nem `RegistroCatalogo` carregam texto ou hash, e
igualdade de metadados é um proxy falso. Medido na base (`?mode=ro`):

- das 14 colisões do catálogo, **9 são texto idêntico** (sha1 igual) e
  **5 não são** — pares do STM (`doc_0844/0856`, `0854/0870`, `0802/0803`,
  `0827/0887`) com mesmo tribunal/ano/relator/campos e texto diferente, e um
  par do TSE com o relator grafado de dois jeitos. Colapsar por metadados
  escolheria um acórdão errado em 5 de 14 casos. A afirmação prévia de que
  as 14 eram duplicatas de texto **não se confirmou** integralmente.
- na base inteira há **35 grupos de texto duplicado (73 registros)**, e
  **nenhum id do gabarito** pertence a um deles — a regra "menor id" não é
  verificável no dev set. No conjunto cego ela é uma aposta 1/2 (ou 1/3)
  entre ids equivalentes; ainda assim é melhor que `incompleta` em valor
  esperado para F1 de `real` (acerto → TP; erro → FP sem FN, contra FN+FP
  de `incompleta`) e não toca τ mais do que `cardinalidade_1` já toca.

Em produção o oráculo tem de vir do catálogo (`Contexto.catalogo`): **pedido
ao Módulo 3** — um campo `hash_texto: str` em `RegistroCatalogo`, preenchido
em `construir_registro` com `sha1(linha["texto"])`; o adaptador no meu lado é
uma linha (`DuplicatasPorAssinatura({r.id: r.hash_texto for r in catalogo.registros})`).
Enquanto isso o harness calcula as assinaturas lendo a base em modo leitura.

**Enum de `metodo_decisao`** (decisão com a Isadora, 2026-09-20, opção (a)):
`desempate_duplicata` e `desempate_score` são valores novos. É **mudança de
contrato** — `docs/contratos.md:48` precisa passar a listar
`sem_identificador, cardinalidade_0, cardinalidade_1, cardinalidade_2mais,
veto_quimera, desempate_duplicata, desempate_score, juiz` — e a
`tabela_confianca` do Módulo 5 precisa de duas linhas novas. **Não editei
`docs/contratos.md`**; fica para o acordo do trio. Motivo de não reusar
`cardinalidade_2mais`: hoje ele significa `incompleta`, e um `real` sob esse
rótulo receberia no M5 a confiança de um ramo de incompleta.

## 9. Contrato do Agente-Juiz (`agentes/juiz.py`)

```
Juiz (Protocol em nos/decidir.py, já existia): escolher(estado, candidatos) -> int | None
 ├── JuizDesligado                 → None. Continua o default (JUIZ_PADRAO).
 ├── JuizFalso(respostas, padrao)  → resposta programada pelo conjunto de ids oferecido.
 └── JuizLLM(backend, catalogo=None)
      ├── montar_prompt(estado, candidatos) -> str        (função pura)
      ├── julgar(estado, candidatos) -> ContextoDecisao   (id + justificativa)
      └── escolher(...) = julgar(...).id_canonico
      BackendLLM (Protocol): gerar(prompt: str) -> str
       ├── BackendFalso(resposta)                       → CPU, ms; guarda os prompts em `chamadas`
       └── BackendTransformers(repositorio, revisao, …) → transformers + torch, importados só em `gerar`
```

Regras implementadas, todas testadas em `tests/test_nos_juiz.py`:

- **Entrada**: `trecho` (espaços colapsados), `campos` normalizados
  (classe, tribunal, uf, ano, relator, orgao, numero_normalizado, só os
  preenchidos), candidatos ordenados por id com `tribunal`, `natureza`,
  `ano`, `relator` (estes dois vêm do `catalogo` quando fornecido; `?` quando
  não) e `divergencias_brandas`. A **janela de contexto no documento não
  existe em `EstadoCitacao`** — o prompt declara a lacuna
  (`CONTEXTO_INDISPONIVEL`), não inventei caminho para buscá-la (ver 12).
- **Saída**: `ContextoDecisao(id_canonico: int | None, justificativa: str)`.
- **Pertinência**: o id só vale se estiver no conjunto oferecido; `bool`,
  float, lista, string não numérica → `None`; string numérica só se for
  exatamente um dos ids. Id plausível mas fora da lista → `None` com a
  justificativa registrando `id fora dos candidatos (…)`.
- **Parsing defensivo**: pede JSON estrito; aceita cerca ```` ```json ````,
  texto antes/depois (primeiro objeto JSON completo via `raw_decode`),
  chaves em qualquer ordem; vazio, `{`, JSON inválido, array, escalar →
  `None`. Nenhum caminho levanta exceção (propriedade Hypothesis com texto
  arbitrário ao redor do objeto).
- **`None` → `incompleta`** em `decidir`; **justificativa nunca entra na
  saída de `decidir`** (testado: as quatro chaves só).
- **Determinismo**: prompt idêntico caractere a caractere para a mesma
  entrada e para qualquer ordem dos candidatos (testado); `BackendTransformers`
  faz `torch.manual_seed(seed)` antes de cada geração, `do_sample=False`
  (greedy; `temperature/top_p/top_k=None` para não disparar o aviso do
  `transformers`), decodifica só os tokens novos.
- **Sem rede**: `local_files_only=True` sempre; id remoto sem `revisao`
  levanta `ValueError` na construção; caminho local dispensa revisão.
- **Menos de 2 candidatos**: `julgar` devolve `None` sem chamar o backend —
  o juiz nunca converte 0 candidatos em `real` (propriedade).
- **Prompt** em português na constante `PROMPT_JUIZ` (`string.Template`,
  placeholders `$trecho $campos $contexto $ids $candidatos`), pedindo
  escolher um id **ou** declarar indecisão, com a frase explícita de que
  indecisão é correta e preferível a chutar.

`decidir_classe` (nó do grafo) com `usar_juiz=True` monta
`JuizLLM(backend=contexto.modelo_llm, catalogo=contexto.catalogo)` — ou
seja, **`Contexto.modelo_llm` passa a ser um `BackendLLM`** (objeto com
`gerar`), não um `ChatLlamaCpp` (ver divergência em 12).

## 10. Testes e harness (v2)

- `tests/test_nos_decidir.py`: 32 → **45** testes. Novos: duplicata resolve
  pelo menor id sem chamar o backend; duplicata com juiz desligado; grupo
  parcial colapsa só o par e o juiz vê `{1, 3}`; id sem assinatura nunca
  colapsa; scores distintos com desempate desligado → `cardinalidade_2mais`;
  ligado → `desempate_score`; margem insuficiente cai para o juiz ou para
  incompleta; empate no topo não resolve; score constante nunca desempata;
  maior score por id; duplicata vence score; `JuizFalso` por conjunto.
  Propriedades estendidas com `habilitar_desempate_score`, `margem_minima`,
  `JuizLLM(BackendFalso(resposta))` com respostas válidas/lixo/cercadas e
  oráculos de duplicata aleatórios: `real ⟺ id_canonico`; `real ⟹ id ∈
  candidatos limpos` em todos os caminhos; juiz nunca converte 0 candidatos;
  juiz desligado nunca chama o backend; `decidir` não muta o estado; quatro
  chaves. O teste sem I/O (`sqlite3.connect`/`open` bloqueados) cobre os
  desempates ligados.
- `tests/test_nos_juiz.py` (novo): **35** testes — os três desfechos, 13
  variantes malformadas parametrizadas, 5 variantes aceitas (cerca, texto
  extra, string numérica, ordem das chaves), backend nunca chamado com juiz
  desligado ou com <2 candidatos, prompt idêntico/independente da ordem/com
  a lacuna declarada/enriquecido pelo catálogo, backend recebe exatamente o
  prompt montado, justificativa fora da saída, `BackendTransformers` exige
  revisão, e três propriedades Hypothesis.
- Suíte inteira: **111 passam, 1 falha pré-existente**
  (`test_propriedade_esqueleto_ruido_igual_esqueleto_original`) + 1 erro de
  coleta pré-existente (`test_catalogo_construir.py`). `ruff check` e
  `ruff format --check` limpos nos cinco arquivos meus.
- Harness: **modo isolado continua 451/451** com os parâmetros default
  (regressão obrigatória). Bloco novo, reportado à parte: **489/489** em 7
  fatias — `desempate_duplicata` (96), `desempate_score_ligado` (96),
  `desempate_score_desligado` (96), `desempate_score_margem_insuficiente`
  (96), `juiz_id_valido`/`juiz_id_fora_da_lista`/`juiz_indeciso` (35 cada).
  Com `--juiz desligado` (default) as três fatias de juiz esperam
  `cardinalidade_2mais` e o histograma mostra `juiz = 0`; com `--juiz falso`
  esperam `juiz` e a seção "Precisão do juiz" reporta consultadas 105,
  decididas 35, indecisas 70 (as 35 de id fora da lista contam como
  indecisas — é a proteção de τ), precisão 1,000, 0 decisões sobre
  inventada. `--juiz` nunca carrega pesos.

## 11. Modo integrado v2 — nada muda, e a projeção

Passada principal fiel à produção (sem oráculo de duplicatas, juiz conforme
`--juiz`): **macro-F1 0,591, τ 0,031 (2/64), s 0,582 — idêntico à v1** nos
dois modos de `--juiz`. Histograma: `desempate_duplicata = 0`,
`desempate_score = 0`, `juiz = 0`.

Diagnóstico novo "ramo 2+: desempates e juiz (contrafactuais)", calculado
sobre os mesmos estados:

| contador | valor |
|---|---|
| citações que entram no ramo 2+ (ids limpos distintos ≥ 2) | **0** |
| resolvidas antes do juiz por duplicata de conteúdo (assinaturas da base) | 0 |
| resolvidas antes do juiz por margem de score (`margem_minima=0`) | 0 |
| chegariam ao juiz hoje | **0** (esperado) |
| gold `real` recuperáveis em `cardinalidade_2mais` | 0 |
| projeção (juiz perfeito): macro-F1 | 0,591 → 0,591 (Δ +0,000); τ 0,031 → 0,031 |
| pior caso (juiz chuta errado em todo empate): macro-F1 | 0,591 (Δ +0,000); τ 0,031 |
| colisões do catálogo cujos registros são o mesmo texto | 9/14 |
| grupos de texto duplicado na base | 35 (73 registros); 0 no gabarito |

A projeção é o número que decide se ligar o juiz paga o custo de
reprodutibilidade: hoje é **zero**, nos dois sentidos. O código da projeção
foi conferido num caso sintético fora do gabarito (4 empates: 1 duplicata, 1
margem, 2 para o juiz → macro-F1 0,133 → 0,333 no teto, 0,111 e τ 1,0 no
pior caso), então quando o M3 passar a devolver acórdãos o harness já
reporta os números certos sem mais código.

## 12. Nada disto tem caso no dev set atual — e por quê

Explicitamente: **nenhuma citação das 195 do gabarito chega ao ramo 2+**
no modo integrado, então desempate 1a, 1b e juiz têm **zero** exemplos
reais. A corretude está provada só em fixture sintética (testes + bloco
isolado do harness). Causas, todas a montante do Módulo 4:

1. `metodo_busca=catalogo` (116 citações) devolve **0 candidatos em todas**
   — defeito 6 da seção 6 (chave-esqueleto do catálogo com milhares de
   dígitos, `numero_normalizado` ausente em 805/998 acórdãos). Sem acórdão
   candidato não há empate de jurisprudência, e as 14 colisões do catálogo
   (o único lugar onde duplicata de conteúdo dispararia) nunca são atingidas.
2. `metodo_busca=lei_sumula` (38) dá {0: 21, 1: 17} ids limpos — nunca 2+.
   Os 18 registros de lei/súmula não têm dois com o mesmo artigo/súmula que
   passem o filtro, então o score (o único que varia: 1,0/0,7/0,5) nunca é
   comparado entre dois ids.
3. As 35 `incompleta` do gabarito têm todas <5 dígitos → `sem_busca`, e o
   ramo que o juiz atenderia não tem exemplo positivo.

Quando o M3 for corrigido: rodar `--modo integrado` e olhar o bloco
"ramo 2+" — se `chegariam ao juiz hoje` continuar 0 e as duplicatas
resolverem tudo, o juiz não precisa ser ligado nunca. **Se o bloco mostrar
empates reais e o gabarito for `real` na maioria deles, aí vale ligar**, e
nesse momento a decisão sobre pesos (13) precisa estar tomada.

**Se a colega do M3 não corrigir o catálogo antes do congelamento (28/09),
este trabalho fica sem caso e o juiz deve continuar desligado** — não há
como calibrar a `tabela_confianca` do ramo `juiz` sem suporte.

## 13. Pesos abertos para o `BackendTransformers` (recomendação, não decisão)

Envelope: 1 GPU de 24 GB, sem rede em execução. O backend é parametrizado
por `(repositorio, revisao)`; nada foi baixado nesta sessão. Três opções que
cabem, com o que cada uma implica:

| opção | VRAM (bf16, pesos) | prós | contras |
|---|---|---|---|
| **Qwen3-8B (instruct)** | ~16 GB + KV | melhor pt-BR e JSON entre os 8B; segue instruções de formato; sobra VRAM para lote | tem "modo pensante" — precisa `enable_thinking=False` no chat template (ajuste de 1 linha em `gerar`) ou o JSON vem depois de um bloco `<think>`; licença Apache-2.0 |
| **Llama-3.1-8B-Instruct** | ~16 GB + KV | ecossistema mais testado; JSON confiável com prompt estrito | pt-BR um pouco pior que o Qwen; licença Llama (aceite no HF, gated — o script de download precisa de token, a execução não) |
| **Gemma-3-12B-it** | ~24 GB em bf16 — **não cabe**; exige 8-bit (~13 GB) ou 4-bit (~8 GB) | pt-BR forte, 12B pesa mais que 8B em raciocínio sobre metadados | quantização em `transformers` puxa `bitsandbytes` (dependência extra) ou GGUF via llama.cpp (que é o extra `llm` já existente, não o `juiz`) |

Recomendação: **Qwen3-8B em bf16** com revisão fixada — é o único que cabe
sem quantizar e com o melhor pt-BR; o custo é o `enable_thinking=False`.
Alternativa alinhada ao que `docs/arquitetura.md` já previa (Gemma 4 26B-A4B
QAT GGUF via `ChatLlamaCpp`): implica um `BackendLlamaCpp` (~30 linhas atrás
do mesmo `BackendLLM`) e o extra `llm`, não o `juiz`. A escolha é do grupo e
entra em `docs/decisoes.md`.

Vale lembrar o que o modelo teria para julgar hoje: `trecho` + campos +
`tribunal/natureza/ano/relator` dos candidatos — **sem a janela de
contexto do documento**. Para os pares de duplicata (9/14) nenhum modelo
distingue nada, e por isso 1a vem antes; para os 5 pares do STM com
metadados idênticos e texto diferente, também não há sinal no que o
`EstadoCitacao` carrega. O juiz só tem chance com a janela de contexto (12).

## 14. Divergências, avisos e pedidos ao grupo (v2)

- **Branch**: o commit da v1 estava só em `modulo4-decisao`, não em `main`
  (`origin/main` = `eadc3b6`); `modulo4-juiz` foi criada a partir de
  `modulo4-decisao`. O PR fica empilhado.
- **`pyproject.toml` foi tocado**: grupo opcional `juiz = ["transformers>=4.56",
  "torch>=2.4"]` em `[project.optional-dependencies]`, ao lado do `llm` já
  existente. `uv lock` regenerou o **`uv.lock`** (+567 linhas, só metadados;
  nada instalado — `import torch` continua falhando aqui e a suíte roda sem
  ele). Levar ao grupo: há dois extras de LLM agora (`llm` = llama.cpp, do
  plano original; `juiz` = transformers, desta tarefa) e um deles deve sair
  quando os pesos forem escolhidos.
- **`docs/contratos.md:48`** precisa dos dois valores novos (seção 8). Não editei.
- **`docs/contratos.md` não tem §8.2**; o contrato do juiz é a linha 46
  (`escolha_juiz`), campo que **não existe** em `EstadoCitacao`. A
  justificativa hoje só é acessível por `JuizLLM.julgar` (harness/log);
  persistir no estado exige o campo — decisão do trio.
- **Campo que falta para a janela de contexto**: `EstadoCitacao` não carrega
  `texto` do documento nem uma janela; sugiro `contexto_documento: str | None`
  preenchido por `extrair_spans`/`distribuir` (Módulo 1/grafo) com
  `texto[max(0, inicio-N):fim+N]`. Até lá o prompt declara a lacuna.
- **`Candidato` não tem `ano`/`relator`**: `JuizLLM` os busca em
  `catalogo.registros` (busca linear por id — 1016 registros × 2-3
  candidatos, irrelevante). Se o M3 preferir, adicionar os dois campos ao
  `Candidato` dispensa o catálogo no juiz.
- **`hash_texto` em `RegistroCatalogo`** (pedido ao M3, seção 8).
- **Backend**: `docs/arquitetura.md` ("Agentes LLM") e o extra `llm` preveem
  `ChatLlamaCpp` + GGUF + `with_structured_output` pydantic; a tarefa pediu
  `transformers`. Implementei o pedido; o Protocol `BackendLLM` permite o
  `BackendLlamaCpp` sem tocar em `JuizLLM`. Também não usei
  `with_structured_output`: o parsing defensivo + validação por pertinência
  cobre o mesmo risco sem depender de `langchain`.
- **Prompt**: `docs/arquitetura.md` manda prompts em `agentes/prompts/*.txt`;
  ficou em constante nomeada (`PROMPT_JUIZ`) como pedido — sem I/O, testável,
  auditável no diff.
- **Nome do Protocol**: é `Juiz` (não `AgenteJuiz`) e devolve `int | None`;
  mantido para não tocar no ramo validado. `ContextoDecisao` vive em
  `JuizLLM.julgar`.
- **`JuizFalso(respostas)`**: programado por **conjunto de ids oferecido**
  (`Mapping[frozenset[int], int | None]` + `padrao`), não por sequência —
  para continuar puro e sem estado.
- **Cache novo em `artifacts/`**: `assinaturas_conteudo.json` (sha1 do
  `texto` por id, gitignored).
