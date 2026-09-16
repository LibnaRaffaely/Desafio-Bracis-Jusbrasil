# grafo/

Só orquestração (ver `docs/arquitetura.md`):

- definição de `EstadoDocumento`, `EstadoCitacao` e `Contexto`;
- montagem do grafo do documento e do subgrafo da citação;
- funções de roteamento das arestas condicionais (distribuir por `Send`,
  rota após normalizar, rota após buscar).

Regra de negócio não entra aqui: ela vive nos nós.
