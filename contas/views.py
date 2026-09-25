from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.shortcuts import resolve_url
from django.urls import resolve
from django.urls.exceptions import Resolver404
from django.views.generic import TemplateView

from contas.models import Papel


class WMSLoginView(LoginView):
    """Login com resolução segura do destino pós-login (`next`, User Story 2).

    `get_redirect_url()` reaproveita a checagem nativa de host/esquema de
    `RedirectURLMixin` (`url_has_allowed_host_and_scheme`, cobre `FR-011`) e
    adiciona a checagem de existência de rota via `django.urls.resolve()` —
    só o `path` é passado a `resolve()` (nunca a URL completa: `query
    string` quebra o casamento de padrão, ver `research.md` R8).

    `get_success_url()` grava, em sessão, o destino exato (path + query)
    concedido, para consumo único por `RetornoPosLoginMiddleware` (ver
    `contracts/protecao-e-redirecionamento.md`). Nenhum parâmetro técnico é
    adicionado à URL de redirecionamento.
    """

    MARCADOR_SESSAO = "_retorno_pos_login_destino"

    def get_redirect_url(self, request=None):
        url = super().get_redirect_url(request)
        if not url:
            return ""
        caminho = urlsplit(url).path
        try:
            resolve(caminho)
        except Resolver404:
            return ""
        # `next` apontando para a própria página de login: o `LoginView` nativo
        # levanta ValueError ("Redirection loop for authenticated user detected")
        # quando `redirect_authenticated_user=True` e o destino é o próprio path —
        # um 500 acionável por link enviado a quem já está autenticado.
        if caminho == urlsplit(resolve_url(settings.LOGIN_URL)).path:
            return ""
        return url

    def form_valid(self, form):
        # O marcador é gravado SOMENTE aqui, depois de um login efetivamente
        # bem-sucedido. Gravá-lo em `get_success_url()` não serve: o
        # `LoginView.dispatch()` nativo também chama esse método para um usuário
        # já autenticado (`redirect_authenticated_user`), o que permitiria armar o
        # marcador por `GET /login/?next=...` — escrita de estado de sessão sem
        # autenticação e sem CSRF, mascarando como Home um 403 legítimo posterior
        # (contracts/protecao-e-redirecionamento.md → Garantias 2 e 3).
        #
        # A escrita vem depois de `super()`, porque `auth_login()` cicla a chave de
        # sessão; gravar antes perderia o valor.
        resposta = super().form_valid(form)
        destino = self.get_redirect_url()
        if destino:
            self.request.session[self.MARCADOR_SESSAO] = destino
        return resposta


# Capacidades futuras do ROADMAP.md, ainda sem rota implementada. Cada item cita a feature do
# roadmap e a capability canônica de `docs/domain/permissions-matrix.md` que a fundamenta. É
# conteúdo puramente informativo da Home: quando a feature correspondente for entregue, o item
# sai daqui e vira um atalho real, com autorização verificada na própria rota (não aqui).
CAPACIDADES_PLANEJADAS = (
    # REQ — PERM-REQ-CREATE-SELF
    {
        "papeis": (Papel.REQUISITANTE,),
        "titulo": "Solicitar material",
        "descricao": (
            "Peça material ao almoxarifado; a solicitação segue para a autorização do chefe "
            "do seu setor."
        ),
    },
    # REQ — PERM-REQ-AUTHORIZE
    {
        "papeis": (Papel.CHEFE_SETOR,),
        "titulo": "Autorizar requisições do setor",
        "descricao": "Decida as solicitações criadas pela equipe do setor que você chefia.",
    },
    # ENT — PERM-STOCK-ENTRY-CREATE
    {
        "papeis": (Papel.FUNCIONARIO_ALMOXARIFADO,),
        "titulo": "Registrar entrada de materiais",
        "descricao": "Lance recebimentos com motivo e referência, com efeito no saldo.",
    },
    # ATE — PERM-REQUEST-FULFILL
    {
        "papeis": (Papel.FUNCIONARIO_ALMOXARIFADO,),
        "titulo": "Atender requisições autorizadas",
        "descricao": "Entregue o material solicitado e conclua a requisição.",
    },
    # HIS — PERM-STOCK-HISTORY-VIEW
    {
        "papeis": (
            Papel.AUXILIAR_SETOR,
            Papel.CHEFE_SETOR,
            Papel.FUNCIONARIO_ALMOXARIFADO,
            Papel.AUDITOR,
        ),
        "titulo": "Histórico de movimentações",
        "descricao": (
            "Confira origem, responsável, quantidade e momento de cada movimento no seu "
            "escopo."
        ),
    },
    # SAE — PERM-SAE-VIEW
    {
        "papeis": (Papel.FUNCIONARIO_ALMOXARIFADO,),
        "titulo": "Saídas excepcionais",
        "descricao": (
            "Baixas fora de requisição, por deterioração, vencimento, doação e outros motivos."
        ),
    },
    # DEV — PERM-RETURN-CREATE
    {
        "papeis": (Papel.CHEFE_ALMOXARIFADO,),
        "titulo": "Devoluções",
        "descricao": "Retorno ao estoque de material atendido, vinculado à requisição de origem.",
    },
    # INV — PERM-INVENTORY-ADJUST
    {
        "papeis": (Papel.CHEFE_ALMOXARIFADO,),
        "titulo": "Ajuste de saldo por inventário",
        "descricao": "Correção rastreável de uma divergência de saldo apurada.",
    },
    # MAT — PERM-MATERIAL-EDIT-NOTE
    {
        "papeis": (Papel.FUNCIONARIO_ALMOXARIFADO,),
        "titulo": "Observações internas de materiais",
        "descricao": "Anotações da equipe sobre um material, sem alterar o cadastro do SCPI.",
    },
    # ORG — PERM-USER-MANAGE, PERM-SECTOR-MANAGE
    {
        "papeis": (Papel.ADMINISTRADOR_SISTEMA,),
        "titulo": "Administração de usuários e setores",
        "descricao": "Manutenção de contas, papéis, setores e chefias.",
    },
)


class HomeView(LoginRequiredMixin, TemplateView):
    """Home autenticada mínima (User Story 1).

    Usa `LoginRequiredMixin` nativo — sem wrapper próprio. `request.user` já
    é `AnonymousUser()` para conta desativada em qualquer requisição
    subsequente (`ModelBackend.get_user()`, `research.md` R9), então nenhuma
    checagem manual de `is_active` é necessária aqui.
    """

    template_name = "contas/home.html"

    def get_context_data(self, **kwargs):
        """Monta o contexto de apresentação da Home (Constitution V: a decisão fica na view,
        o template só apresenta). `pode_importar_catalogo` cobre a capability
        `PERM-SCPI-IMPORT-EXECUTE` (importação) e `PERM-SCPI-IMPORT-HISTORY-VIEW` (histórico),
        ambas exigindo `ROLE-WAREHOUSE-HEAD` (`contracts/rotas-e-autorizacao.md`, 001).
        `pode_consultar_catalogo` cobre `PERM-MATERIAL-VIEW` (`ROLE-REQUESTER`, concedido a
        toda identidade de negócio). Os links são conveniência de navegação — a autorização
        efetiva continua nas próprias rotas (Constitution VI).

        `setor` e `papeis` são só apresentação. `capacidades_planejadas` filtra
        `CAPACIDADES_PLANEJADAS` pelos papéis do usuário e é puramente informativo: nenhum item
        corresponde a rota, URL, contagem ou ação real — nenhum deles concede autorização.

        Os códigos de papel são lidos do banco uma única vez (`set`), e tanto as flags quanto
        `papeis`/`capacidades_planejadas` são derivados dele — sem N+1 (Constitution X). A
        checagem de posse é a mesma de `tem_papel`: só papel explicitamente atribuído, sem
        herança."""
        contexto = super().get_context_data(**kwargs)
        usuario = self.request.user
        codigos_papeis = set(usuario.papeis.values_list("papel", flat=True))

        contexto["pode_importar_catalogo"] = Papel.CHEFE_ALMOXARIFADO in codigos_papeis
        contexto["pode_consultar_catalogo"] = Papel.REQUISITANTE in codigos_papeis
        contexto["setor"] = usuario.setor
        contexto["papeis"] = [
            Papel(codigo).label for codigo in Papel.values if codigo in codigos_papeis
        ]
        contexto["capacidades_planejadas"] = [
            {"titulo": item["titulo"], "descricao": item["descricao"]}
            for item in CAPACIDADES_PLANEJADAS
            if codigos_papeis & {papel.value for papel in item["papeis"]}
        ]
        return contexto
