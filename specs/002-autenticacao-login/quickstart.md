# Quickstart — validação de ponta a ponta

Guia de validação manual e automatizada da feature 002 depois de implementada
(`/speckit-tasks` → implementação). Não contém código de implementação — apenas os passos para
comprovar que o comportamento da spec funciona.

## Pré-requisitos

- Ambiente local configurado conforme `.env.example` (PostgreSQL acessível).
- Migrations aplicadas: `python manage.py migrate`.

## 1. Provisionar dados mínimos de desenvolvimento

**Ordem obrigatória** — `createsuperuser` exige um `Setor` já existente (`setor` está em
`REQUIRED_FIELDS`, é FK obrigatória), mas ainda não existe nenhuma conta capaz de acessar o Django
Admin nesse momento. O Django Admin **não pode** ser usado para criar o primeiro `Setor` — só existe
depois que o primeiro superusuário já existir. Por isso o primeiro `Setor` é criado por shell:

### 1.1 Criar o primeiro `Setor` (via shell, antes de qualquer conta)

```bash
python manage.py shell -c "from contas.models import Setor; Setor.objects.create(nome='Almoxarifado')"
```

### 1.2 Criar o primeiro superusuário técnico

```bash
python manage.py createsuperuser
# Django solicitará: matrícula, setor (informe o Setor criado em 1.1), senha.
# Cria uma conta técnica (is_staff=True, is_superuser=True) — sem papel de negócio.
```

### 1.3 Demais dados (setores adicionais, usuários de negócio, papéis)

A partir daqui, com o superusuário já existente, o Django Admin
(`/admin/contas/user/`, `/admin/contas/setor/`, `/admin/contas/papelusuario/`) pode ser usado
normalmente: criar setores adicionais, criar um `User` de negócio com `matricula`/senha/setor, e
adicionar uma ou mais linhas de `PapelUsuario` para ele.

## 2. Validar login (User Story 1)

1. Acessar `/login/` deslogado → formulário pedindo matrícula e senha.
2. Informar matrícula+senha válidas de um usuário ativo → redirecionado para `/` (Home mínima).
3. Repetir com senha errada → mensagem de erro genérica, sem indicar se a matrícula existe.
4. Repetir com matrícula inexistente → mesma mensagem genérica do passo 3.
5. Desativar um usuário (`is_active=False` via Admin) e tentar autenticar com credenciais que
   seriam válidas → mesma mensagem genérica.

## 3. Validar proteção de superfícies e retorno pós-login (User Story 2)

1. Sem sessão, acessar `/` (Home, protegida) diretamente → redirecionado para `/login/?next=/`.
2. Autenticar → retorna a `/` automaticamente; a URL final não contém nenhum parâmetro técnico de
   retorno (o mecanismo vive em sessão, nunca na URL); acessar novamente qualquer página não repete
   o redirecionamento automático (o marcador de sessão já foi consumido na primeira requisição).
3. Tentar manipular `next` para um domínio externo (`/login/?next=https://exemplo-externo.com`) →
   após autenticar, o sistema não redireciona para o domínio externo (vai para a Home).
4. Usar `next` apontando para um caminho que não corresponde a nenhuma rota → após autenticar, vai
   para a Home em vez de 404.
5. Usar `next` apontando para um destino real com query string legítima (ex.:
   `/login/?next=/materiais/%3Fpagina%3D2`, ou o equivalente já usado pela própria feature 001
   quando existir) → após autenticar, a rota é reconhecida como existente e a query string é
   preservada no destino final (verifica a correção desta revisão: `resolve()` não recebe mais a
   query string).
6. (Requer uma view de teste que levante `PermissionDenied`) Login com `next` apontando para essa
   view → ao seguir o redirecionamento (a primeira requisição imediatamente após o login), cai na
   Home em vez do 403 padrão.
7. Acessar essa mesma view de teste **de novo**, depois, fora do fluxo de login (sem ter acabado de
   autenticar) → mostra o 403 padrão do Django normalmente — prova de que o fallback não é global e
   já foi consumido.
8. Nessa mesma view de teste, adicionar manualmente `?_retorno_pos_login=1` à URL e acessá-la
   diretamente (sem vir de um login) → não muda nada, continua 403 normal — prova de que a query
   string não tem nenhum efeito sobre a decisão (o marcador real vive em sessão, não na URL).

## 4. Validar identificação de usuário e papel (User Story 3)

Via shell (`python manage.py shell`) ou teste automatizado:

```python
user.is_authenticated  # True após autenticar
user.setor              # instância de Setor, nunca None
user.papeis.all()       # todas as atribuições explícitas
user.tem_papel("ROLE-WAREHOUSE-HEAD")  # True/False conforme atribuição
```

## 5. Validar conta desativada durante sessão (edge case crítico)

1. Autenticar normalmente e confirmar acesso à Home.
2. Em outra aba/sessão administrativa, definir `is_active=False` para esse mesmo usuário.
3. Com a sessão já aberta, acessar novamente qualquer superfície protegida → acesso negado /
   redirecionado ao login, sem precisar fazer logout manual antes. Isso acontece por comportamento
   nativo do Django (`AuthenticationMiddleware` recarrega o usuário a cada request e já o trata
   como anônimo quando `is_active=False`) — não há nenhum código próprio de verificação para testar
   aqui além do uso comum de `login_required`/`LoginRequiredMixin`.

## 6. Validar logout (User Story 4)

1. Autenticado, enviar `POST` para `/logout/` (botão "Sair" na Home) → redirecionado para
   `/login/`.
2. Tentar acessar `/` novamente com a mesma sessão de navegador → exige novo login.
3. Enviar `POST /logout/` sem sessão válida (ex.: cookies limpos) → continua redirecionando para
   `/login/` normalmente, como no-op seguro — não é um caso de erro, `LogoutView` não exige sessão
   autenticada (ver `contracts/protecao-e-redirecionamento.md`).

## 7. Rodar a suíte automatizada

```bash
uv run pytest tests/ -k contas
```

Deve cobrir, no mínimo, os cenários acima (ver `plan.md` → seção Testes para a lista completa por
arquivo).

## Critério de aceite do quickstart

Todos os 6 roteiros manuais acima produzem o resultado descrito, e a suíte automatizada
correspondente passa sem intervenção manual adicional.
