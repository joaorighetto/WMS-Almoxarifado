<!--
Sync Impact Report
Version change: 1.0.0 → 1.1.0 (MINOR — expansão material de princípio existente, sem remoção ou
  redefinição incompatível de regra).
Modified principles:
  - VIII. Interface Operacional Consistente e Eficiente → VIII. Design System e Interface
    Operacional Consistente (renomeado e materialmente expandido: design system explícito e
    versionado; DESIGN.md; uso de Impeccable; uso obrigatório da skill frontend-design para
    implementação significativa de frontend com Claude Code; ordem de precedência de decisões de
    frontend; restrição a novos componentes/padrões; proibição de decoração sem função, animação
    excessiva e espaçamento excessivo quando prejudicarem a eficiência; exigência de revisão visual
    para mudanças significativas de frontend. Regra de exclusão de acessibilidade preservada sem
    alteração de conteúdo.)
Added sections: nenhuma (conteúdo adicionado dentro do Princípio VIII existente).
Removed sections: nenhuma.
Other changes:
  - Restrições Tecnológicas → item "Estilo" atualizado para exigir CSS organizado sobre o design
    system e uso de tokens/variáveis (antes: apenas "CSS próprio").
Deferred / TODO: nenhum.
-->

# WMS Almoxarifado Constitution

Sistema web operacional e administrativo de uso diário para gestão de materiais, locais de
armazenamento, estoque, movimentações, inventários, requisições, rastreabilidade e relatórios.
Esta constituição estabelece regras duráveis de engenharia e arquitetura, não funcionalidades.

Os termos **DEVE**, **NÃO DEVE**, **DEVERIA** e **PODE** são normativos. "DEVE" e "NÃO DEVE"
são obrigações verificáveis em revisão; "DEVERIA" admite exceção documentada com justificativa;
"PODE" é permissão.

## Core Principles

### I. Simplicidade Arquitetural

Toda solução DEVE usar o recurso convencional do Django (models, forms, views, templates, ORM,
admin, middleware) antes de introduzir estrutura própria. Camadas adicionais — services,
repositories, DTOs, factories, gerenciadores de eventos e similares — NÃO DEVEM ser criadas sem
um problema concreto e identificável que a camada resolva. Generalizações especulativas
justificadas por necessidade futura hipotética NÃO DEVEM ser adicionadas. Toda complexidade
adicional DEVE ser justificada por escrito na descrição da mudança, nomeando o problema concreto
que resolve; complexidade sem justificativa é motivo suficiente para rejeitar a mudança.

**Racional**: o custo de manutenção de abstrações desnecessárias é pago em toda leitura futura do
código, enquanto o benefício de flexibilidade especulativa frequentemente nunca se realiza.

### II. Arquitetura Server-Driven

A aplicação DEVE ser predominantemente renderizada no servidor, com Django Templates como
mecanismo padrão de renderização. HTMX DEVE ser o meio de implementar interações incrementais —
atualização parcial de página, filtros, busca, paginação, modais, submissão de formulários e
interações equivalentes que não exijam uma aplicação SPA. JavaScript próprio DEVE ser pequeno,
modular e introduzido somente quando HTML, CSS e HTMX comprovadamente não forem suficientes.
React, Vue, Angular ou qualquer outro framework SPA NÃO DEVEM ser introduzidos sem necessidade
técnica documentada e aprovada como emenda a esta constituição.

**Racional**: uma única fonte de renderização elimina duplicação de estado e de regras entre
cliente e servidor, reduzindo superfície de erro em um sistema cujo valor está na correção dos
dados operacionais.

### III. Integridade de Dados (NÃO NEGOCIÁVEL)

Integridade de estoque prevalece sobre conveniência de implementação. Toda operação que altere
estado crítico de estoque DEVE: ter regras de negócio explícitas e localizáveis no backend;
validar suas pré-condições antes de efetivar qualquer alteração; preservar consistência sob
execução concorrente; executar atomicamente quando envolver mais de uma alteração dependente;
impedir a criação de estados inválidos; e ser rastreável conforme o Princípio IV.

Atualizações concorrentes NÃO DEVEM produzir saldo inconsistente, movimentação duplicada ou
quantidade inválida. Operações de escrita sobre saldo DEVEM usar transação explícita combinada
com bloqueio ou atualização atômica ao nível do banco, nunca leitura-em-memória seguida de
escrita sem proteção. Sempre que uma invariante crítica puder ser expressa como constraint de
banco de dados (unicidade, verificação de não-negatividade, chave estrangeira, exclusão mútua),
ela DEVE também ser protegida nesse nível, além da validação na aplicação.

**Racional**: validação apenas na aplicação falha sob concorrência, importação de dados e acesso
administrativo; o banco é a última linha de defesa e a única compartilhada por todos os caminhos
de escrita.

### IV. Rastreabilidade e Auditoria

Operações relevantes DEVEM permitir determinar quem executou, o que foi alterado, quando ocorreu e
qual era o contexto da operação. Informação histórica relevante NÃO DEVE desaparecer
silenciosamente em consequência de edição ou remoção posterior. Exclusão física de registros NÃO
DEVE ser usada quando prejudicar rastreabilidade ou integridade histórica; nesses casos DEVE ser
adotada inativação, cancelamento ou estorno, preservando o registro original e o vínculo com a
operação que o alterou.

**Racional**: divergências de estoque são investigadas depois do fato, frequentemente semanas
depois; sem histórico preservado a investigação é impossível e a responsabilidade indeterminável.

### V. Regras de Negócio no Backend

O navegador NUNCA DEVE ser considerado responsável por garantir integridade ou autorização. Todas
as regras de negócio, permissões e invariantes DEVEM ser garantidas no backend, independentemente
do que a interface apresente ou impeça. Validações de interface PODEM ser adicionadas para melhorar
a experiência do usuário, mas DEVEM duplicar — nunca substituir — a validação de servidor. Regras
de negócio relevantes NÃO DEVEM residir em templates ou em JavaScript; templates DEVEM se limitar
a apresentação e os dados de decisão DEVEM chegar prontos da view.

**Racional**: qualquer requisição pode ser construída fora da interface; uma regra que só existe no
cliente não é uma regra, é uma sugestão.

### VI. Segurança por Padrão

O princípio do menor privilégio DEVE ser aplicado a usuários, papéis e integrações. Toda operação
protegida DEVE verificar autenticação e autorização no servidor, na própria view ou em mecanismo
equivalente aplicado antes de qualquer efeito; ocultar um elemento na interface NÃO constitui
autorização. Toda entrada externa DEVE ser validada antes de uso. As proteções fornecidas pelo
Django — CSRF, escaping de template, ORM parametrizado, proteções de sessão e cabeçalhos de
segurança — DEVEM ser mantidas ativas; desativá-las pontualmente exige justificativa documentada.
Credenciais, tokens, senhas e segredos NÃO DEVEM ser armazenados em código-fonte ou em arquivos
versionados; DEVEM vir de variáveis de ambiente ou mecanismo equivalente de configuração externa.
Mensagens de erro exibidas ao usuário NÃO DEVEM revelar detalhes internos sensíveis como stack
traces, consultas, caminhos de arquivo ou dados de outros usuários.

**Racional**: o sistema é acessado por múltiplos perfis operacionais com poderes distintos sobre
patrimônio público; falhas de autorização têm consequência material, não apenas técnica.

### VII. Testes como Parte da Implementação

Uma funcionalidade NÃO DEVE ser considerada concluída sem testes automatizados proporcionais ao seu
risco. DEVEM ter cobertura de teste, prioritariamente: regras de negócio; permissões e
autorização; validações; transições de estado; operações de estoque; concorrência e transações
críticas; regressões conhecidas; e os fluxos principais de cada funcionalidade. Correção de bug
DEVERIA incluir um teste que reproduza o defeito e falhe antes da correção.

**Racional**: as regras mais valiosas deste sistema são invisíveis na interface — saldo correto sob
concorrência, permissão negada corretamente — e só um teste demonstra que continuam valendo.

### VIII. Design System e Interface Operacional Consistente

O projeto DEVE possuir um design system explícito e versionado, definido antes da implementação
significativa de interfaces. As decisões consolidadas de design — cores, tipografia, espaçamento,
estados, padrões de interação e demais tokens visuais — DEVEM ser registradas em `DESIGN.md` e
refletidas em tokens CSS e componentes compartilhados. Impeccable DEVE ser usado para estabelecer,
documentar, avaliar e evoluir esse design system, e PODE ser usado como ferramenta de apoio para
auditoria e refinamento visual.

Para implementação significativa de frontend com Claude Code, a skill `frontend-design` DEVE ser
utilizada. Essa skill DEVE respeitar o design system existente e NÃO DEVE reinventar padrões
visuais já definidos. Novos componentes ou padrões visuais só DEVEM ser introduzidos quando os
existentes não resolverem adequadamente o problema.

A precedência para decisões de frontend, da mais para a menos autoritativa, é: requisitos da
feature → esta constituição → `DESIGN.md` → tokens e componentes existentes → skill
`frontend-design` → decisão específica da interface. Uma camada só PODE ser sobreposta pela
seguinte quando a anterior não cobrir o caso em questão.

O WMS é uma ferramenta operacional de uso diário. A interface DEVE priorizar clareza, velocidade de
operação, previsibilidade, baixa carga cognitiva, boa densidade de informação, redução de erros e
consistência. Componentes reutilizáveis DEVEM ser preferidos a markup duplicado. Tabelas,
formulários, modais, paginação, filtros, busca, autocomplete e ações compartilhadas DEVEM ter
comportamento e aparência consistentes em todo o sistema. A interface DEVE apresentar de forma
explícita os estados relevantes: carregamento, sucesso, erro, ausência de resultados,
indisponibilidade e confirmação de ações destrutivas ou irreversíveis. Fluxos de uso frequente
DEVEM exigir o mínimo razoável de etapas e interações. Decoração sem função, animações excessivas e
layouts excessivamente espaçados NÃO DEVEM ser usados quando prejudicarem a eficiência operacional.

Mudanças significativas de frontend DEVEM passar por revisão visual quanto à aderência ao
`DESIGN.md`, reutilização de componentes, consistência visual e eficiência operacional.

Requisitos específicos de acessibilidade — WCAG, ARIA, leitores de tela, navegação por teclado —
NÃO DEVEM ser adicionados por padrão, exceto quando necessários ao funcionamento correto de um
componente ou quando explicitamente exigidos por uma feature.

**Racional**: o sistema é operado diariamente e em volume; inconsistência visual e decisões de
design ad-hoc transferem carga cognitiva ao operador e produzem erro de lançamento. Um design
system explícito e uma ordem de precedência clara evitam que cada tela reinvente padrões e tornam a
implementação de frontend previsível mesmo quando conduzida por agentes automatizados.

### IX. Progressive Enhancement

Funcionalidades essenciais DEVEM permanecer baseadas em comportamento de servidor sempre que
possível. HTMX DEVE aprimorar a experiência, sem transferir regras de domínio para o cliente.
Operações que podem ser executadas por requisições HTTP convencionais NÃO DEVEM depender de
JavaScript para funcionar. Quando JavaScript for necessário, ele DEVE complementar a aplicação e
NÃO DEVE se tornar fonte primária de regra de negócio.

**Racional**: reduz modos de falha em ambiente operacional heterogêneo e mantém o servidor como
única autoridade sobre o domínio, coerente com os Princípios II e V.

### X. Performance Baseada em Evidências

Otimização prematura DEVE ser evitada, mas problemas conhecidos DEVEM ser prevenidos desde a
implementação: consultas N+1; carregamento de grandes conjuntos de dados sem necessidade; listagens
sem paginação; consultas de filtro e busca sem índice adequado; e processamento síncrono
desnecessariamente pesado no ciclo de requisição. Otimizações complexas DEVEM ser justificadas por
necessidade observável ou requisito mensurável, não por suposição. Fluxos operacionais frequentes
DEVEM receber atenção específica à latência percebida pelo usuário.

**Racional**: os problemas listados são previsíveis e baratos de evitar na escrita, e caros de
diagnosticar depois que o volume de dados cresce em produção.

### XI. Dependências com Parcimônia

Antes de adicionar uma biblioteca externa, DEVEM ser avaliados, nesta ordem: (1) se Django, Python,
HTMX ou a biblioteca padrão já resolvem adequadamente o problema; (2) custo de manutenção;
(3) maturidade e manutenção ativa do projeto; (4) impacto de segurança; (5) benefício concreto.
Dependências NÃO DEVEM ser adicionadas apenas para substituir poucas linhas de código simples.

**Racional**: cada dependência é superfície de segurança, ponto de quebra em atualização e dívida
de manutenção permanente, paga mesmo quando o benefício foi pontual.

### XII. Manutenibilidade

Código DEVE favorecer clareza sobre concisão excessiva. Nomes DEVEM representar conceitos do
domínio — material, local de armazenamento, movimentação, requisição, inventário — e não conceitos
técnicos genéricos. Funções, classes e módulos DEVEM ter responsabilidade compreensível e
enunciável. Duplicação relevante DEVE ser removida, mas abstrações NÃO DEVEM ser criadas apenas
para eliminar semelhanças pequenas ou ocasionais. Código crítico DEVE ser compreensível sem exigir
conhecimento de abstrações desnecessariamente complexas.

**Racional**: o código de estoque será lido sob pressão durante investigação de divergência; o que
não puder ser entendido nessa situação não poderá ser corrigido com segurança.

### XIII. Migrações Seguras

Alterações de banco de dados DEVEM preservar dados existentes. Migrações destrutivas ou
irreversíveis DEVEM ser justificadas explicitamente na mudança que as introduz. Quando uma
alteração estrutural representar risco significativo, DEVEM ser planejadas a migração de dados e a
estratégia de recuperação antes da execução.

**Racional**: os dados históricos de estoque não são reproduzíveis; perdê-los invalida a
rastreabilidade exigida pelo Princípio IV.

### XIV. Observabilidade

Erros importantes e operações críticas DEVEM produzir informação suficiente para diagnóstico.
Logging DEVE ser útil e estruturado, evitando tanto ausência de informação quanto ruído excessivo.
Dados sensíveis NÃO DEVEM ser registrados em log. Operações críticas de estoque DEVEM produzir
informação suficiente para investigar inconsistências posteriormente, incluindo identificação da
operação, do ator e dos valores envolvidos.

**Racional**: sem registro adequado, a investigação de uma divergência de saldo depende de
reconstrução manual e inconclusiva.

## Restrições Tecnológicas

A stack a seguir é normativa. Alterações exigem emenda a esta constituição.

- **Backend**: Python com Django.
- **Banco de dados**: PostgreSQL como único banco de dados de produção. Recursos específicos do
  PostgreSQL PODEM ser usados quando expressarem melhor uma invariante ou consulta.
- **Renderização**: Django Templates.
- **Interatividade**: HTMX, conforme Princípios II e IX.
- **Estilo**: CSS próprio, organizado sobre o design system definido em `DESIGN.md`, utilizando
  tokens/variáveis para valores recorrentes (cores, espaçamento, tipografia e afins).
- **JavaScript**: pontual, pequeno e modular, apenas onde HTML, CSS e HTMX não bastem.

Configuração sensível DEVE vir do ambiente e NÃO DEVE ser versionada (Princípio VI). Novas
dependências estão sujeitas ao Princípio XI.

## Definition of Done

Uma funcionalidade só PODE ser considerada concluída quando todos os itens abaixo forem
verdadeiros:

1. Atende aos requisitos e aos cenários de aceitação definidos.
2. Respeita esta constituição.
3. Possui validações adequadas no backend.
4. Possui autorização adequada verificada no servidor.
5. Possui os testes necessários, proporcionais ao risco (Princípio VII).
6. Não introduz regressões conhecidas.
7. Mantém consistência visual e comportamental com o restante do sistema.
8. Mantém integridade e rastreabilidade dos dados.
9. Apresenta corretamente os estados de sucesso, erro e ausência de dados, quando aplicável.
10. Não deixa código temporário, TODO crítico ou solução provisória sem registro explícito.

## Governance

Esta constituição prevalece sobre outras práticas, convenções e preferências do projeto. Em
conflito entre conveniência de implementação e integridade, segurança, rastreabilidade ou clareza,
estes últimos DEVEM prevalecer.

**Emendas**: alterações a este documento DEVEM ser propostas por escrito, com justificativa,
impacto sobre princípios existentes e, quando aplicável, plano de adequação do código já
existente. A emenda só entra em vigor quando registrada neste arquivo com nova versão e data.

**Versionamento**: este documento usa versionamento semântico.
- **MAJOR**: remoção ou redefinição incompatível de princípio ou regra de governança.
- **MINOR**: adição de princípio ou seção, ou expansão material de orientação existente.
- **PATCH**: esclarecimento, correção de redação ou refinamento não semântico.

**Conformidade**: toda mudança de código DEVE ser verificada contra esta constituição antes de ser
aceita. Desvio consciente DEVE ser documentado na própria mudança, com justificativa e, quando for
provisório, com registro do que precisa ser corrigido. Complexidade adicional DEVE ser justificada
(Princípio I).

**Orientação de desenvolvimento**: arquivos de orientação para agentes e colaboradores — como
`CLAUDE.md` na raiz do repositório, quando existir — NÃO DEVEM contradizer esta constituição. Em
caso de divergência, esta constituição prevalece e o arquivo de orientação DEVE ser corrigido.

**Version**: 1.1.0 | **Ratified**: 2026-09-18 | **Last Amended**: 2026-09-18
