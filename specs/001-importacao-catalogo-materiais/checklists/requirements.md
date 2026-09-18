# Specification Quality Checklist: Importação Inicial e Consulta do Catálogo de Materiais

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-18
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Iteração 1 — 2026-09-18

Três marcadores [NEEDS CLARIFICATION] permaneciam, todos por ausência de padrão razoável: destino
dos campos de classificação recebidos do SCPI, comportamento em reexecução da importação e meio de
entrega do arquivo de carga.

### Iteração 2 — 2026-09-18

Todas as três questões respondidas e incorporadas à spec, registradas na seção Clarifications.
Nenhum marcador remanescente; todos os itens do checklist passam.

A resposta sobre reexecução ampliou a feature: deixou de ser carga única e passou a incluir
reconciliação com o SCPI, com preservação obrigatória do saldo do WMS e registro de divergências
(User Story 4, FR-025 a FR-032, FR-047, SC-009, SC-010).

Terminologia de campo (`CADPRO`, `DISC1`, `UNID1`, `QUAN3`, `DISCR1`, `GRUPO`, `SUBGRUPO`,
`NOMEGRUPO`, `NOMESUBGRUPO`) e formato CSV foram mantidos por serem o contrato de dados do SCPI,
não escolha de implementação.

### Iteração 3 — 2026-09-18 (validação contra o arquivo real)

A spec foi confrontada com o export real do SCPI (1588 materiais). Dois requisitos estavam
factualmente errados e foram corrigidos; um terceiro foi acrescentado:

- **FR-009** presumia que toda continuação de linha pertencia a `DISCR1`. Falso: o material
  `004.001.002` tem a descrição principal partida em três linhas. A regra passou a recompor o
  registro lógico antes de separar os campos.
- **FR-012** proibia arredondamento, o que gravaria `53,4000000000001` como saldo. Definida escala
  de três casas decimais.
- **FR-007a** foi criado para as 434 aspas duplas literais (polegadas). Nenhum campo do arquivo é
  delimitado por aspas, então um parser com quoting habilitado desalinharia as colunas — falha que
  não apareceria em testes com dados sintéticos.

Acrescentados os cenários de aceitação 10 a 12 da User Story 1, ancorados em registros reais
(`004.001.002`, `000.029.742`), e três edge cases correspondentes. Todos os itens seguem passando.
