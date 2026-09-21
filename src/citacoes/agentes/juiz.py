"""Agente-Juiz (Módulo 4) — docs/arquitetura.md ("Agentes LLM") e
docs/contratos.md (linha `escolha_juiz`: "id escolhido ou nada, e
justificativa (só log)").

Separação em duas camadas, para desenvolver e testar sem GPU:

- `JuizLLM` tem a lógica — monta o prompt, chama o backend, parseia e
  valida a resposta — e não sabe carregar modelo.
- `BackendLLM` (Protocol `gerar(prompt) -> str`) é quem gera texto:
  `BackendFalso` devolve resposta programada (testes, harness);
  `BackendTransformers` carrega pesos de verdade e não sabe nada de citação.

Regras que protegem τ (docs/avaliacao.md): o id devolvido só vale se
pertencer ao conjunto de candidatos empatados — validação por pertinência,
nunca por formato; qualquer falha de parsing vira `None`, nunca exceção; e
`None` vira `incompleta` em `nos/decidir.py`. A `justificativa` é log e
auditoria, nunca confiança. O prompt é função pura das entradas
(candidatos ordenados por id, sem timestamp), e a geração é greedy com
seed fixa, conforme docs/reprodutibilidade.md.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any, Protocol

from citacoes.catalogo.esquema import Candidato, CatalogoCanonico, RegistroCatalogo
from citacoes.grafo.estados import EstadoCitacao

# ── contrato de saída ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContextoDecisao:
    """Resultado do juiz: um id dentre os candidatos, ou `None` (sem sinal
    decisivo, resposta inválida ou não parseável). `justificativa` é texto
    livre para log — `decidir` não a lê e `calibrar` não pode lê-la."""

    id_canonico: int | None
    justificativa: str


# ── backends ────────────────────────────────────────────────────────────────


class BackendLLM(Protocol):
    """Gera texto a partir de um prompt. Determinismo (greedy, seed fixa) é
    responsabilidade da implementação; o juiz só exige que a mesma entrada
    produza a mesma saída."""

    def gerar(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class BackendFalso:
    """Backend de teste: devolve `resposta` para qualquer prompt e guarda os
    prompts recebidos em `chamadas` (para afirmar que o backend não foi
    chamado, ou que dois prompts são idênticos). Roda em CPU, em
    milissegundos."""

    resposta: str = ""
    chamadas: list[str] = field(default_factory=list, compare=False, repr=False)

    def gerar(self, prompt: str) -> str:
        self.chamadas.append(prompt)
        return self.resposta


@dataclass(frozen=True)
class BackendTransformers:
    """Backend com `transformers` + `torch` (grupo opcional `juiz` do
    `pyproject.toml`). Importa as bibliotecas só em `gerar`, para que o
    pipeline determinístico nem precise delas instaladas.

    Sem rede em tempo de execução (docs/reprodutibilidade.md): `repositorio`
    é um caminho local ou um id do Hugging Face já baixado por script, e
    nesse caso `revisao` (commit fixo) é obrigatória — nunca "latest". A
    geração é greedy (`do_sample=False`), com `torch.manual_seed(seed)`
    antes de cada chamada, e decodifica só os tokens novos.
    """

    repositorio: str
    revisao: str | None = None
    max_tokens_novos: int = 200
    seed: int = 42
    dispositivo: str = "auto"
    _cache: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.revisao is None and not Path(self.repositorio).exists():
            raise ValueError(
                "BackendTransformers: `repositorio` não é caminho local e `revisao` está "
                "vazia — a revisão tem de ser fixada (docs/reprodutibilidade.md)."
            )

    def _carregar(self) -> tuple[Any, Any]:
        if "modelo" not in self._cache:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            comuns = {"revision": self.revisao, "local_files_only": True}
            tokenizador = AutoTokenizer.from_pretrained(self.repositorio, **comuns)
            modelo = AutoModelForCausalLM.from_pretrained(
                self.repositorio, device_map=self.dispositivo, dtype=torch.bfloat16, **comuns
            )
            modelo.eval()
            self._cache["tokenizador"] = tokenizador
            self._cache["modelo"] = modelo
        return self._cache["tokenizador"], self._cache["modelo"]

    def gerar(self, prompt: str) -> str:
        import torch

        tokenizador, modelo = self._carregar()
        torch.manual_seed(self.seed)
        mensagens = [{"role": "user", "content": prompt}]
        if getattr(tokenizador, "chat_template", None):
            entrada = tokenizador.apply_chat_template(
                mensagens, add_generation_prompt=True, return_tensors="pt", return_dict=True
            )
        else:
            entrada = tokenizador(prompt, return_tensors="pt")
        entrada = {k: v.to(modelo.device) for k, v in entrada.items()}
        with torch.no_grad():
            saida = modelo.generate(
                **entrada,
                max_new_tokens=self.max_tokens_novos,
                do_sample=False,
                temperature=None,
                top_p=None,
                top_k=None,
                pad_token_id=tokenizador.pad_token_id or tokenizador.eos_token_id,
            )
        novos = saida[0, entrada["input_ids"].shape[1] :]
        return tokenizador.decode(novos, skip_special_tokens=True)


# ── prompt ──────────────────────────────────────────────────────────────────

# Versionado aqui, como constante, para ser auditável no diff. Placeholders
# via `string.Template` ($trecho, $campos, $contexto, $candidatos, $ids)
# porque o exemplo de JSON usa chaves literais.
PROMPT_JUIZ = Template(
    """\
Você apoia a verificação de citações jurídicas. Uma citação casou com o mesmo identificador em mais de um documento da base, e todos os candidatos abaixo passaram pelas verificações automáticas de tribunal e número. Sua tarefa é dizer se algum sinal da citação aponta com segurança para UM candidato específico.

Citação (texto literal): $trecho
Campos extraídos da citação: $campos
Contexto no documento de origem: $contexto

Candidatos (ids válidos: $ids):
$candidatos

Regras:
1. Responda SOMENTE com um objeto JSON, sem texto antes ou depois, sem cercas de markdown, neste formato:
   {"id_canonico": <um dos ids válidos, como número inteiro, ou null>, "justificativa": "<uma frase curta>"}
2. Só escolha um id se um dado da citação (ano, relator, órgão, classe, tribunal, UF) distinguir esse candidato dos demais. Um candidato "mais provável" sem dado que o distinga NÃO é sinal decisivo.
3. Se não houver sinal decisivo, responda {"id_canonico": null, "justificativa": "..."}. Declarar indecisão é uma resposta correta e preferível a chutar: um id errado custa mais do que nenhum id.
4. Nunca invente um id que não esteja na lista de ids válidos.
"""
)

CONTEXTO_INDISPONIVEL = "(indisponível: EstadoCitacao não carrega o texto do documento)"

_CERCA_MARKDOWN = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_DECODIFICADOR = json.JSONDecoder()


def _primeiro_objeto_json(texto: str) -> dict | None:
    """Primeiro objeto JSON completo dentro de `texto`, ignorando o que vier
    antes e depois; `None` se não houver nenhum válido."""
    for inicio, caractere in enumerate(texto):
        if caractere != "{":
            continue
        try:
            dados, _ = _DECODIFICADOR.raw_decode(texto, inicio)
        except ValueError:
            continue
        if isinstance(dados, dict):
            return dados
    return None


# ── juiz ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class JuizLLM:
    """Juiz com modelo de linguagem, por trás de um `BackendLLM` injetado.
    Implementa o Protocol `Juiz` de `nos/decidir.py` (`escolher` ->
    `int | None`); `julgar` devolve também a `justificativa`, para o
    harness e para log. `catalogo` é opcional e só enriquece os candidatos
    com `ano`/`relator`, que `Candidato` não carrega (docs/arquitetura.md
    liga o catálogo ao `agente_juiz` pelo contexto)."""

    backend: BackendLLM
    catalogo: CatalogoCanonico | None = None

    # -- entrada -----------------------------------------------------------

    def _registro(self, id_: int) -> RegistroCatalogo | None:
        if self.catalogo is None:
            return None
        for registro in self.catalogo.registros:
            if registro.id == id_:
                return registro
        return None

    def _descrever_candidato(self, candidato: Candidato) -> str:
        registro = self._registro(candidato.id)
        partes = [
            f"id={candidato.id}",
            f"tribunal={candidato.tribunal or '?'}",
            f"natureza={candidato.natureza}",
            f"ano={registro.ano if registro and registro.ano is not None else '?'}",
            f"relator={registro.relator if registro and registro.relator else '?'}",
        ]
        if candidato.divergencias_brandas:
            partes.append(f"divergencias_brandas={','.join(candidato.divergencias_brandas)}")
        return "- " + " | ".join(partes)

    @staticmethod
    def _descrever_campos(estado: EstadoCitacao) -> str:
        campos = estado.campos
        if campos is None:
            return "(nenhum)"
        pares = []
        for nome in ("classe", "tribunal", "uf", "ano", "relator", "orgao", "numero_normalizado"):
            valor = getattr(campos, nome, None)
            if valor not in (None, "", ()):
                pares.append(f"{nome}={valor}")
        return "; ".join(pares) if pares else "(nenhum)"

    def montar_prompt(self, estado: EstadoCitacao, candidatos: Sequence[Candidato]) -> str:
        """Função pura das entradas: candidatos ordenados por id, trecho com
        espaços colapsados, nada de relógio ou aleatoriedade."""
        ordenados = sorted(candidatos, key=lambda c: c.id)
        return PROMPT_JUIZ.substitute(
            trecho=" ".join(estado.trecho.split()),
            campos=self._descrever_campos(estado),
            contexto=CONTEXTO_INDISPONIVEL,
            ids=", ".join(str(c.id) for c in ordenados),
            candidatos="\n".join(self._descrever_candidato(c) for c in ordenados),
        )

    # -- saída -------------------------------------------------------------

    @staticmethod
    def parsear(resposta: str) -> tuple[Any, str]:
        """Extrai `(id_bruto, justificativa)` da resposta do modelo, sem
        levantar exceção: aceita cerca de markdown e texto ao redor do
        objeto; resposta vazia ou sem JSON válido -> `(None, motivo)`."""
        texto = (resposta or "").strip()
        if not texto:
            return None, "resposta vazia do modelo"
        cercado = _CERCA_MARKDOWN.search(texto)
        if cercado:
            texto = cercado.group(1).strip()
        dados = _primeiro_objeto_json(texto)
        if dados is None:
            return None, "resposta sem objeto JSON válido"
        justificativa = dados.get("justificativa", "")
        if not isinstance(justificativa, str):
            justificativa = str(justificativa)
        return dados.get("id_canonico"), justificativa

    @staticmethod
    def validar(id_bruto: Any, candidatos: Sequence[Candidato]) -> int | None:
        """Pertinência ao conjunto, nunca formato: `bool` não conta como
        inteiro, string numérica só vale se for exatamente um id da lista."""
        validos = {c.id for c in candidatos}
        if isinstance(id_bruto, bool) or id_bruto is None:
            return None
        if isinstance(id_bruto, int):
            return id_bruto if id_bruto in validos else None
        if isinstance(id_bruto, str) and id_bruto.strip().isdigit():
            valor = int(id_bruto.strip())
            return valor if valor in validos else None
        return None

    def julgar(self, estado: EstadoCitacao, candidatos: Sequence[Candidato]) -> ContextoDecisao:
        if len(candidatos) < 2:
            # Não há empate; o juiz não é a instância certa (nunca converte
            # 0 candidatos em real, nem "confirma" 1).
            return ContextoDecisao(None, "juiz não consultado: menos de 2 candidatos")
        resposta = self.backend.gerar(self.montar_prompt(estado, candidatos))
        id_bruto, justificativa = self.parsear(resposta)
        id_valido = self.validar(id_bruto, candidatos)
        if id_valido is None and id_bruto is not None:
            justificativa = f"id fora dos candidatos ({id_bruto!r}); {justificativa}".strip("; ")
        return ContextoDecisao(id_valido, justificativa)

    def escolher(self, estado: EstadoCitacao, candidatos: Sequence[Candidato]) -> int | None:
        return self.julgar(estado, candidatos).id_canonico
