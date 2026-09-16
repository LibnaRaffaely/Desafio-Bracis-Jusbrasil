# catalogo/

Construção offline do catálogo canônico a partir de `desafio1_bracis.db`
e carga para o contexto do grafo.

- Indexar só os identificadores **próprios** de cada registro (cabeçalho),
  para que acórdãos que apenas citam outros não virem candidatos.
- Guardar, por registro: `id` (o valor de `id_canonico`), tribunal, ano,
  relator, natureza, classe, número, CNJ, UF, órgão; tupla para leis e
  súmulas.
- Gerar o relatório de colisões (chaves que apontam para 2+ registros).
- Saída em `artifacts/`, fora do git.
