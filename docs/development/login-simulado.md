# Login simulado por papel

No servidor de desenvolvimento (`make run`, ou as configurações de
`.claude/launch.json`), nenhuma tela exige passar pelo formulário de login: o
middleware `contas/login_simulado.py` autentica automaticamente uma conta do
`seed_dev`. Isso existe para que o `impeccable critique`, capturas de tela e
agentes naveguem o app sem barreira — mas **com o contexto de permissões real**.

## O que é simulado e o que não é

Só o formulário é pulado. A sessão é criada por `django.contrib.auth.login` para
uma conta real do banco, com os papéis e o setor que o `seed_dev` lhe deu.
Menus da Home, links visíveis, recortes por setor e respostas 403 são
exatamente os que essa conta teria depois de digitar a senha. Nenhuma checagem
de autorização é contornada.

## Trocar de identidade

Acrescente `?dev_como=<valor>` a qualquer URL (GET). O middleware troca a
sessão, grava a escolha num cookie e redireciona para a mesma URL sem o
parâmetro — as navegações seguintes, inclusive requisições HTMX, mantêm a
identidade.

| Valor | Conta do seed | Papéis além de Requisitante |
|---|---|---|
| `requisitante` | `requisitante` | — |
| `auxiliar-setor` | `eta.auxiliar` | Auxiliar de setor (ETA) |
| `chefe-setor` | `eta.chefe` | Chefe de setor (ETA) |
| `funcionario-almoxarifado` | `funcionario` | Funcionário do almoxarifado |
| `chefe-almoxarifado` (padrão) | `chefe` | Chefe de setor, funcionário e chefe do almoxarifado |
| `auditor` | `auditor` | Gestor/auditor |
| `administrador-sistema` | `administrador` | Administrador de sistema |
| `anonimo` | — | Sai e para de autenticar automaticamente |

Qualquer matrícula de conta ativa também é aceita (`?dev_como=redes.chefe`,
`?dev_como=admin` para o Django Admin). Valor desconhecido ou conta inativa
responde 400 com a lista de opções. O mapeamento vive em
`contas/dev_seed/dados.py` → `CONTA_POR_PAPEL`.

Exemplos:

```text
http://localhost:8010/estoque/entradas/?dev_como=auditor
http://localhost:8010/catalogo/?dev_como=requisitante
http://localhost:8010/login/?dev_como=anonimo
```

Para criticar a tela de login, use `?dev_como=anonimo`; para voltar ao
automático, informe outro papel. O logout pelo app também volta a autenticar
na navegação seguinte, a menos que a identidade seja `anonimo`.

## Configuração e limites

- Carregado só por `config/settings/development.py` e só com `DEBUG`; o
  próprio middleware se desliga sem `DEBUG` e `WMS_LOGIN_SIMULADO`. Production
  e test nunca o carregam.
- Só atende requisições vindas da própria máquina (127.0.0.1/::1): um
  `runserver 0.0.0.0` não abre o app sem senha para a rede local — de outro
  dispositivo, o login é o real.
- `WMS_LOGIN_SIMULADO=False` no `.env` desliga (para exercitar o login real);
  `WMS_LOGIN_SIMULADO_PADRAO` escolhe a identidade inicial.
- A autenticação automática acontece só em GET/HEAD: `login()` rotaciona o
  token CSRF, o que invalidaria um POST em curso.
- Um login feito pelo formulário não é sobrescrito, exceto por `?dev_como=`.
- Requer o banco populado (`make seed_dev`). Sem a conta, o visitante continua
  anônimo e o console registra um aviso.
