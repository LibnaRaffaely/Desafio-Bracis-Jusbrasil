# agentes/

Os três agentes LLM opcionais, todos desligados por padrão:

| Agente | Quando entra | Devolve |
|---|---|---|
| extrator | gatilho descritivo sem span encontrado | spans extras |
| parser | normalizar não conseguiu estruturar a citação | campos estruturados |
| juiz | 2+ candidatos empatados | um dos ids dados, ou nenhum |

Também ficam aqui: a carga do modelo (`ChatLlamaCpp`, seed explícita,
`temperature=0`) e os schemas pydantic usados em `with_structured_output`.
Prompts em `prompts/`, um arquivo por agente, versionados como texto.

Agente nunca define classe nem confiança.
