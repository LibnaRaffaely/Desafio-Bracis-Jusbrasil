# Registro de decisões

Uma entrada por decisão que muda regra do pipeline, sempre com evidência.

| # | Pergunta | Evidência | Decisão | Onde muda |
|---|---|---|---|---|
| D1 | Módulo 3 consulta `documentos_fts` (FTS5 MATCH por frase) a cada citação, como descrito em Plano_de_acao.docx §3.3, ou usa um catálogo pré-indexado em memória? | Analise_Exploratoria.docx §b mediu o FTS5 real: tolerância a ruído zero — um número real com 1 dígito trocado por letra (`"7OOO449..."`) ou 1 dígito faltando dá 0 resultados, indistinguível de "não existe". Sem normalização *antes* da query, a query em si não resolve o Nível 2. Além disso, `catalogo/README.md` já definia "indexar só os identificadores próprios de cada registro (cabeçalho)" antes desta implementação — o que faz o filtro de posição (cabeçalho vs. corpo) do Contrato de Dados §5 ser uma propriedade da *construção* do catálogo, não uma consulta em tempo de busca. | Módulo 3 usa `catalogo.buscar_jurisprudencia`/`buscar_lei_sumula` (lookup exato pela chave-esqueleto de `dominio.chave`, construída offline por `catalogo/construir.py`), não `FTS5 MATCH`. `documentos_fts` fica disponível no banco mas não é consultado pelo pipeline. Mesma normalização (`dominio.campos.extrair_campos`) roda dos dois lados — citação e catálogo —, o que é o que garante a chave bater. | `catalogo/construir.py`, `nos/buscar_no_catalogo.py`, `docs/contratos.md` (já refletia isso: `metodo_busca` é `catalogo`/`lei_sumula`/`sem_busca`, não `fts5`) |

