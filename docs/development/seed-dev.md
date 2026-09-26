# Dados de desenvolvimento

`make setup` executa `seed_dev` ao terminar a recriação do schema. Antes de subir
o PostgreSQL ou apagar dados, executa `seed_dev --check` para conferir ambiente,
senha e arquivo de catálogo. O comando aceita somente
`config.settings.development`.

## Configuração e execução

Defina `SEED_DEV_PASSWORD` no `.env`. Essa senha é usada em todas as contas
criadas, passa pelos validadores do Django e nunca é exibida pelo comando.
Não versione o `.env`.

O CSV padrão é
`docs/CSVs/relacao-de-todos-produtos-importados-do-SCPI.csv`. Ele está
ignorado pelo Git; um clone novo precisa receber o arquivo localmente.

O cadastro de fornecedores é **opcional**: se
`docs/CSVs/fornecedores.csv` existir (também ignorado pelo Git), o seed o
importa pelo mesmo `fornecedores.importacao.confirmar_importacao` usado pela
aplicação; se estiver ausente — padrão ou caminho informado por
`--fornecedores` —, o comando emite um aviso e segue sem falhar. Diferente do
catálogo, não é um pré-requisito do seed.

```bash
make setup
# Para popular um schema já criado e vazio:
make seed_dev
# Para usar outro CSV do SCPI:
uv run --env-file .env python manage.py seed_dev --catalogo /caminho/catalogo.csv
# Para usar outro CSV de fornecedores (opcional):
uv run --env-file .env python manage.py seed_dev --fornecedores /caminho/fornecedores.csv
# Para conferir os pré-requisitos sem escrever no banco:
uv run --env-file .env python manage.py seed_dev --check
```

`make resetdb` continua criando somente o schema; execute `make seed_dev` depois
para repor os dados. `make setup` já faz as duas etapas.

## Contas e organização

O conjunto inclui 8 setores, 32 contas, todos os sete papéis de negócio, setores
ativos com exatamente um chefe ativo e contas inativas para conferir o bloqueio
de login. Setores e matrículas são fictícios, inspirados na operação de um serviço
municipal de saneamento. Os modelos atuais não têm campos de nome ou e-mail.

| Setor | Contas | Estado |
|---|---:|---|
| Almoxarifado | 6, incluindo `admin` e um funcionário inativo | Ativo |
| Estação de Tratamento de Água | 4 | Ativo |
| Estação de Tratamento de Esgoto | 4 | Ativo |
| Operação e Manutenção de Redes | 4 | Ativo |
| Manutenção Eletromecânica | 4 | Ativo |
| Laboratório de Controle de Qualidade | 4 | Ativo |
| Administração e Atendimento | 4, incluindo auditor e administrador de sistema | Ativo |
| Obras e Expansão — Unidade Desativada | 2, ambas inativas | Inativo |

| Matrícula | Uso |
|---|---|
| `admin` | Superusuário técnico do Django Admin, sem papéis de negócio |
| `chefe` | Chefe do almoxarifado e do setor Almoxarifado; importa, consulta e vê histórico |
| `funcionario` | Funcionário do almoxarifado; consulta o catálogo |
| `requisitante` | Requisitante do setor Almoxarifado; consulta o catálogo |

Todas usam a senha definida em `SEED_DEV_PASSWORD`. A conta técnica acessa
`/admin/`; as contas de negócio acessam `/login/`. Os demais perfis e matrículas
estão declarados em `contas/dev_seed/dados.py` e podem ser consultados no Admin.

## Catálogo e histórico

São executadas três importações pelo processamento existente da aplicação:

1. **Carga original:** importa integralmente o CSV local, estabelecendo os saldos
   iniciais e a execução de origem dos materiais.
2. **Revisão demonstrativa:** gera em memória um CSV de amostra com mudanças nos
   sete campos cadastrais, quantidades divergentes, materiais ausentes e registros
   recusados. O nome da execução identifica seu caráter simulado.
3. **Restauração:** reimporta o CSV original, restaurando os dados cadastrais e
   registrando as alterações correspondentes no histórico.

Ao final, os materiais mantêm os valores cadastrais e saldos do arquivo original.
As divergências são informativas: nenhuma reimportação sobrescreve saldo.
O arquivo original não é alterado nem copiado para arquivos versionados.
Datas, hashes, totais, atores e vínculos são produzidos pelo fluxo real de
importação; os históricos demonstrativos podem ser explorados pela conta `chefe`.

Com o CSV local validado nesta implementação, a carga resulta em 1.588 materiais,
3 execuções de importação, 12 exceções cobrindo os 11 motivos de recusa,
2 divergências de saldo e 14 alterações cadastrais (sete na simulação e sete na
restauração). Há 52 atribuições explícitas de papéis. As contagens do catálogo e
do histórico podem variar quando outro CSV é fornecido.

O seed cobre os oito modelos de negócio do catálogo: `Setor`, `User`,
`PapelUsuario`, `Material`, `ExecucaoImportacao`, `ExcecaoImportacao`,
`DivergenciaSaldo` e `AlteracaoCadastralMaterial`. Tabelas internas do Django são
administradas pelos próprios mecanismos do framework. Não são criadas
movimentações, reservas ou requisições, cujos modelos ainda não existem.

Esse provisionamento automático é exclusivo do ambiente de desenvolvimento.
A importação operacional pela interface continua exigindo prévia e confirmação.

## Fornecedores (opcional)

Se `docs/CSVs/fornecedores.csv` existir — ou o caminho informado por
`--fornecedores` —, o seed importa o cadastro de fornecedores pelo mesmo
`fornecedores.importacao.confirmar_importacao` da aplicação (feature 004),
como uma quarta importação, executada pela conta `chefe`. A ausência do
arquivo (padrão ou informado) só emite um aviso no console; o comando
continua e o restante do seed (contas, catálogo, histórico) é criado
normalmente. Um arquivo presente, mas inválido (estrutura recusada,
`contracts/arquivo-fornecedores.md` da spec 004), falha o comando inteiro,
como o catálogo.

A saída do comando só informa totais da importação de fornecedores
(recebidos, inseridos, atualizados, rejeitados) — nunca nome, documento ou
qualquer outro valor do arquivo, o mesmo cuidado que a interface de
importação já tem com dados pessoais do cadastro (`INV-SUPPLIER-004`).

O seed cobre os quatro modelos de negócio de `fornecedores`: `Fornecedor`,
`ExecucaoImportacaoFornecedores`, `ExcecaoImportacaoFornecedores` e
`AlteracaoFornecedor` — só quando o arquivo é fornecido.

## Repetição e falhas

O conjunto inteiro (contas, setores, catálogo, histórico e, quando o arquivo
existe, fornecedores) é criado em uma única transação. Uma falha desfaz tudo
dessa tentativa. Execuções concorrentes do seed usam o mesmo bloqueio de
importação para evitar duplicação.

Os três tokens fixos de importação do catálogo identificam um seed já
concluído. Repetir `make seed_dev` nesse estado não cria registros, não troca
senhas e não desfaz edições feitas depois, mesmo que os arquivos ou a senha
inicial já não estejam disponíveis — inclusive a importação de fornecedores,
que tem seu próprio token fixo, mas cuja repetição está protegida pelo mesmo
reconhecimento: como todo o comando é uma única unidade de bootstrap, a
segunda chamada nunca chega a tentar importar fornecedores de novo (nem a
validar o arquivo), então nunca duplica nem falha por token já usado. Esse
reconhecimento não repara dados modificados ou removidos, e não reimporta
fornecedores retroativamente num banco já seedado sem esse arquivo antes —
para isso, reconstrua o ambiente (abaixo).

Se houver dados de negócio e o conjunto de tokens não estiver completo, o comando
recusa a carga sem alterar a base. Para reconstruir deliberadamente o ambiente
descartável, use `make setup`, que apaga os dados locais.
