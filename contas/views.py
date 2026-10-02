import logging
import uuid
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.urls import resolve, reverse
from django.urls.exceptions import Resolver404
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.generic import FormView, TemplateView, View

from catalogo.views import ExigePapelMixin
from config.texto import normalizar_para_busca
from contas.credenciais import (
    VALIDADE_SENHA_PROVISORIA,
    definir_propria_senha,
    trocar_propria_senha,
)
from contas.forms import (
    PAPEIS_ADICIONAIS,
    ChefiaForm,
    ConfirmacaoForm,
    DefinirSenhaForm,
    DesativacaoForm,
    FiltroSetoresForm,
    FiltroUsuariosForm,
    ReativacaoForm,
    RedefinicaoSenhaForm,
    SetorForm,
    TransferenciaForm,
    TrocarSenhaForm,
    UsuarioCadastroForm,
    UsuarioEdicaoForm,
    UsuarioPapeisForm,
)
from contas.middleware import RetornoPosLoginMiddleware
from contas.models import EventoOrganizacional, Papel, Setor, User, chefes_ativos
from contas.organizacao import (
    PAPEIS_QUE_ACOMPANHAM_O_CHEFE_DO_ALMOXARIFADO,
    RECUSA_CHEFE_DE_SETOR_ATIVO,
    RECUSA_CHEFIA_DE_ESTOQUE_INCOMPLETA,
    RECUSA_MATRICULA_EM_USO,
    RECUSA_SETOR_JA_TEM_CHEFE,
    RECUSA_SETOR_SEM_CHEFE,
    RECUSA_ULTIMO_ADMINISTRADOR,
    OperacaoJaExecutada,
    OperacaoRecusada,
    PreviaDesatualizada,
    alterar_papeis,
    ativar_setor,
    bloqueios_de_papeis,
    bloqueios_de_papeis_no_cadastro,
    cadastrar_usuario,
    criar_setor,
    desativar_setor,
    desativar_usuario,
    designar_chefia,
    editar_usuario,
    impedimento_de_ativar_setor,
    impedimento_de_desativar_setor,
    impedimento_de_desativar_usuario,
    impedimento_de_transferir_usuario,
    previa_reativacao,
    previa_substituicao,
    previa_transferencia,
    prontidao_do_setor,
    reativar_usuario,
    redefinir_senha,
    renomear_setor,
    retirar_chefia,
    substituir_chefia,
    transferir_usuario,
)

logger = logging.getLogger(__name__)


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
            "Confira origem, responsável, quantidade e momento de cada movimento no seu escopo."
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
        toda identidade de negócio). `pode_importar_fornecedores` cobre
        `PERM-SUPPLIER-IMPORT-EXECUTE` (`ROLE-WAREHOUSE-HEAD`) e `pode_consultar_fornecedores`
        cobre `PERM-SUPPLIER-VIEW` (`ROLE-WAREHOUSE-STAFF`) — feature 004
        (`specs/004-importacao-fornecedores/contracts/rotas-e-autorizacao.md`).
        `pode_registrar_entrada` cobre `PERM-STOCK-ENTRY-CREATE` (`ROLE-WAREHOUSE-STAFF`) e
        `pode_consultar_entradas` cobre o recorte de `PERM-STOCK-HISTORY-VIEW` aplicado à
        entrada (`ROLE-WAREHOUSE-STAFF` ou `ROLE-AUDITOR`) — feature 003
        (`specs/003-entrada-materiais/contracts/rotas-e-autorizacao.md`, research R12). Os
        links são conveniência de navegação — a autorização efetiva continua nas próprias
        rotas (Constitution VI).

        `pode_administrar_organizacao` cobre `PERM-USER-MANAGE` e `PERM-SECTOR-MANAGE`
        (`ROLE-SYSTEM-ADMIN`) — feature 005 (`specs/005-administracao-usuarios-setores/
        contracts/rotas-e-autorizacao.md`).

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

        contexto["pode_administrar_organizacao"] = Papel.ADMINISTRADOR_SISTEMA in codigos_papeis
        contexto["pode_importar_catalogo"] = Papel.CHEFE_ALMOXARIFADO in codigos_papeis
        contexto["pode_consultar_catalogo"] = Papel.REQUISITANTE in codigos_papeis
        contexto["pode_importar_fornecedores"] = Papel.CHEFE_ALMOXARIFADO in codigos_papeis
        contexto["pode_consultar_fornecedores"] = Papel.FUNCIONARIO_ALMOXARIFADO in codigos_papeis
        contexto["pode_registrar_entrada"] = Papel.FUNCIONARIO_ALMOXARIFADO in codigos_papeis
        contexto["pode_consultar_entradas"] = bool(
            codigos_papeis & {Papel.FUNCIONARIO_ALMOXARIFADO, Papel.AUDITOR}
        )
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


# ---------------------------------------------------------------------------
# Senha do próprio usuário (feature 005, US1) — `contracts/credenciais.md`
# ---------------------------------------------------------------------------


class SenhaView(LoginRequiredMixin, FormView):
    """`/senha/` (`definir_senha`): a senha do próprio usuário, nos dois estados da credencial.

    Alcançável por qualquer usuário autenticado e ativo, sem papel (D-27, FR-039); é a única rota
    (além do logout) que o `CredencialProvisoriaMiddleware` deixa passar enquanto a credencial é
    provisória. Com credencial provisória, é a definição obrigatória (sem senha atual); sucesso
    devolve ao destino pedido antes do login — o marcador de `WMSLoginView`, que o
    `RetornoPosLoginMiddleware` consome na requisição seguinte — ou à Home (FR-034). Com
    credencial definitiva, é a troca voluntária, com a senha atual: sucesso volta à Home com
    "Senha alterada." (FR-037).
    """

    template_name = "contas/senha.html"

    def _provisoria(self):
        return self.request.user.senha_provisoria_em is not None

    def get_form_class(self):
        return DefinirSenhaForm if self._provisoria() else TrocarSenhaForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["provisoria"] = self._provisoria()
        return contexto

    def form_valid(self, form):
        try:
            if self._provisoria():
                definir_propria_senha(
                    self.request, self.request.user, form.cleaned_data["new_password1"]
                )
            else:
                trocar_propria_senha(
                    self.request,
                    self.request.user,
                    form.cleaned_data["old_password"],
                    form.cleaned_data["new_password1"],
                )
                messages.success(self.request, "Senha alterada.")
                return redirect("home")
        except OperacaoRecusada as recusa:
            if self._provisoria():
                form.add_error("new_password1", recusa.motivo)
            else:
                form.add_error(None, f"{recusa.motivo} {recusa.caminho or ''}".strip())
            return self.form_invalid(form)
        return redirect(self._destino())

    def _destino(self):
        destino = self.request.session.get(RetornoPosLoginMiddleware.MARCADOR_SESSAO)
        if destino and url_has_allowed_host_and_scheme(
            destino,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return destino
        return resolve_url("home")


# ---------------------------------------------------------------------------
# Administração da organização (feature 005, US1 e US2) — `contracts/rotas-e-autorizacao.md`
# ---------------------------------------------------------------------------

TAMANHO_PAGINA_USUARIOS = 50
TAMANHO_PAGINA_HISTORICO = 25

MENSAGEM_JA_EXECUTADA = (
    "Esta operação já foi executada; a senha provisória não é exibida novamente."
)

MENSAGEM_ERRO_INESPERADO = "Não foi possível concluir a operação. Nada foi gravado."
CAMINHO_ERRO_INESPERADO = "Tente novamente; se o problema continuar, avise o suporte."

_ROTULOS_DE_CAMPO = {
    "matricula": "Matrícula",
    "nome": "Nome",
    "setor": "Setor",
    "papeis": "Papéis",
    "papeis_concedidos": "Papéis concedidos",
    "papeis_retirados": "Papéis retirados",
    "novo_chefe_recebeu": "Papéis concedidos ao novo chefe",
    "chefe_anterior_perdeu": "Papéis retirados do chefe anterior",
    "chefe": "Chefe",
    "motivo": "Motivo",
    "primeira_ativacao": "Primeira ativação",
    "situacao": "Situação",
    "papeis_preservados": "Papéis preservados",
    "papeis_confirmados": "Papéis confirmados",
    "papeis_desmarcados": "Papéis desmarcados",
}
_ROTULOS_DE_MOTIVO = {
    "cadastro": "Cadastro pelo administrador",
    "provisionamento": "Provisionamento técnico",
    "provisionamento_desenvolvimento": "Provisionamento de desenvolvimento",
    "definicao_obrigatoria": "Definição obrigatória no primeiro acesso",
    "troca_voluntaria": "Troca voluntária pelo próprio usuário",
    "redefinicao": "Redefinição pelo administrador",
}


class _AdministracaoView(ExigePapelMixin):
    """Base das telas de `/organizacao/`: só `ROLE-SYSTEM-ADMIN` (`PERM-USER-MANAGE`,
    `PERM-SECTOR-MANAGE`). A checagem de papel vem antes de qualquer consulta ao objeto: quem
    não é administrador recebe 403 mesmo para `<pk>` inexistente (FR-002)."""

    papel_exigido = Papel.ADMINISTRADOR_SISTEMA


class _OperacaoView(_AdministracaoView, View):
    """Base das telas de `/organizacao/` que executam uma operação (POST). `executar` chama a
    operação e converte qualquer erro inesperado em log com traceback e num alerta genérico —
    nada foi gravado, porque a operação é atômica —, pelo mesmo caminho da recusa. As exceções
    de domínio passam intactas para a view tratá-las."""

    def executar(self, operacao, *args, **kwargs):
        try:
            return operacao(*args, **kwargs)
        except (OperacaoRecusada, OperacaoJaExecutada, PreviaDesatualizada):
            raise
        except Exception:
            logger.exception("Erro inesperado na operação organizacional %s.", operacao.__name__)
            raise OperacaoRecusada(MENSAGEM_ERRO_INESPERADO, CAMINHO_ERRO_INESPERADO) from None


def _formatar_valor(valor):
    if valor is None or valor == "":
        return "—"
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, list | tuple):
        return ", ".join(_formatar_valor(item) for item in valor) or "—"
    if isinstance(valor, dict):
        return ", ".join(f"{chave}: {_formatar_valor(item)}" for chave, item in valor.items())
    texto = str(valor)
    if texto in Papel.values:
        return Papel(texto).label
    return _ROTULOS_DE_MOTIVO.get(texto, texto)


def _rotulo_de_campo(chave):
    return _ROTULOS_DE_CAMPO.get(chave, chave.replace("_", " ").capitalize())


def _detalhes_do_evento(dados):
    """Anterior/novo por campo e os demais detalhes de `EventoOrganizacional.dados`, em linhas
    prontas para exibição (FR-040). `dados` nunca leva senha (FR-031)."""
    anterior, novo = dados.get("anterior"), dados.get("novo")
    alteracoes, detalhes = [], []
    if isinstance(anterior, dict) or isinstance(novo, dict):
        anterior, novo = anterior or {}, novo or {}
        for chave in [*anterior, *(chave for chave in novo if chave not in anterior)]:
            alteracoes.append(
                {
                    "campo": _rotulo_de_campo(chave),
                    "anterior": _formatar_valor(anterior.get(chave)),
                    "novo": _formatar_valor(novo.get(chave)),
                }
            )
    else:
        for chave in ("anterior", "novo"):
            if chave in dados:
                detalhes.append((chave.capitalize(), _formatar_valor(dados[chave])))
    detalhes += [
        (_rotulo_de_campo(chave), _formatar_valor(valor))
        for chave, valor in dados.items()
        if chave not in ("anterior", "novo")
    ]
    return alteracoes, detalhes


def _historico(request, consulta):
    """Página do histórico organizacional de uma ficha, do mais antigo ao mais recente
    (FR-040 a FR-042). Devolve `(pagina, eventos)`: `eventos` são os da página com
    `alteracoes` e `detalhes` já montados."""
    eventos = consulta.select_related(
        "autor", "usuario", "usuario_relacionado", "setor", "setor_relacionado"
    ).order_by("momento", "pk")
    pagina = Paginator(eventos, TAMANHO_PAGINA_HISTORICO).get_page(request.GET.get("pagina"))
    lista = list(pagina.object_list)
    for evento in lista:
        evento.alteracoes, evento.detalhes = _detalhes_do_evento(evento.dados)
    return pagina, lista


def _rotulos_dos_papeis(usuario):
    """Rótulos dos papéis da conta na ordem do catálogo. Usa o `prefetch_related("papeis")`."""
    atribuidos = {papel_usuario.papel for papel_usuario in usuario.papeis.all()}
    return [Papel(codigo).label for codigo in Papel.values if codigo in atribuidos]


def _situacao_da_credencial(usuario):
    """`(estado, momento)` da credencial para a ficha — nunca a senha (FR-031):
    `definitiva`, `provisoria` (vence em `momento`) ou `provisoria_vencida` (venceu em
    `momento`)."""
    if usuario.senha_provisoria_em is None:
        return "definitiva", None
    vencimento = usuario.senha_provisoria_em + VALIDADE_SENHA_PROVISORIA
    return ("provisoria_vencida" if vencimento < timezone.now() else "provisoria"), vencimento


def _destino_do_impedimento(impedimento, setor=None):
    """Para onde o administrador vai resolver o `impedimento` (a `OperacaoRecusada` que a tela
    explica): `{"rotulo", "url"}` ou `None` quando a regra não tem destino. A regra é identificada
    pelo `codigo` da recusa, nunca pelo texto. `setor` é aquele de que a regra fala."""
    if impedimento is None:
        return None
    codigo = impedimento.codigo
    if setor is not None:
        chefia = reverse("setor_chefia", kwargs={"pk": setor.pk})
        if codigo == RECUSA_CHEFE_DE_SETOR_ATIVO:
            return {"rotulo": f"Substituir a chefia de {setor.nome}", "url": chefia}
        if codigo == RECUSA_SETOR_SEM_CHEFE:
            return {"rotulo": f"Designar a chefia de {setor.nome}", "url": chefia}
        if codigo == RECUSA_CHEFIA_DE_ESTOQUE_INCOMPLETA:
            return {"rotulo": f"Corrigir a chefia de {setor.nome}", "url": chefia}
        if codigo == RECUSA_SETOR_JA_TEM_CHEFE:
            rotulo = "Substituir a chefia de" if setor.ativo else "Ver a chefia de"
            return {"rotulo": f"{rotulo} {setor.nome}", "url": chefia}
    if codigo == RECUSA_ULTIMO_ADMINISTRADOR:
        return {"rotulo": "Escolher outra pessoa na lista de usuários", "url": reverse("usuarios")}
    return None


def _recusa_alem_do_impedimento(recusa, impedimento):
    """A `recusa` do POST que a tela ainda precisa mostrar: a que repete o `impedimento` (já
    explicado, sem botão) é descartada, para o motivo não aparecer duas vezes."""
    if recusa is not None and impedimento is not None and recusa.motivo == impedimento.motivo:
        return None
    return recusa


def _setor_do_formulario(valor):
    """O `Setor` cujo pk veio no formulário ou na query, ou `None` se ausente, malformado ou
    inexistente — a escolha de verdade é validada pelo formulário e pela operação."""
    try:
        return Setor.objects.filter(pk=int(valor)).first()
    except (TypeError, ValueError):
        return None


def _contexto_de_papeis_do_cadastro(setor, marcados):
    """Contexto da região de papéis do cadastro (`_papeis_cadastro.html`), conforme o setor
    escolhido (`None`: ainda não escolhido, nada bloqueado). `opcoes_de_papeis` tem um item por
    papel adicional — `papel`, `rotulo`, `id`, `marcado` (um papel bloqueado nunca vai marcado),
    `bloqueio` (a recusa que dá-lo a quem entra nesse setor daria, ou `None`) e `destino` (para
    onde resolver o bloqueio, ou `None`) —, e `implicados_pela_chefia` são os rótulos dos papéis
    que "Chefe de setor" leva junto no Almoxarifado (vazio nos demais setores). O servidor decide
    em `cadastrar_usuario`: o bloqueio é só antecipação."""
    bloqueios = bloqueios_de_papeis_no_cadastro(setor) if setor is not None else {}
    opcoes = []
    for indice, (codigo, rotulo) in enumerate(PAPEIS_ADICIONAIS):
        papel = Papel(codigo)
        bloqueio = bloqueios.get(papel)
        opcoes.append(
            {
                "papel": papel,
                "rotulo": rotulo,
                "id": f"id_papeis_{indice}",
                "marcado": papel in marcados and bloqueio is None,
                "bloqueio": bloqueio,
                "destino": _destino_do_impedimento(bloqueio, setor),
            }
        )
    implicados = []
    if setor is not None and setor.almoxarifado:
        implicados = [
            papel.label for papel in Papel if papel in PAPEIS_QUE_ACOMPANHAM_O_CHEFE_DO_ALMOXARIFADO
        ]
    return {
        "setor_escolhido": setor,
        "opcoes_de_papeis": opcoes,
        "implicados_pela_chefia": implicados,
    }


@method_decorator(never_cache, name="dispatch")
class UsuarioNovoView(_OperacaoView):
    """`usuario_novo`: cadastro de usuário (`PERM-USER-MANAGE`).

    O POST de sucesso devolve 200 com a senha provisória, uma única vez, sem redirect e sem
    cache (R8): nada de senha em sessão, mensagem, log ou evento. Repetir o POST (mesma
    `chave_confirmacao`) avisa e leva à ficha; recusa re-renderiza com motivo e caminho, os
    dados digitados e a mesma chave (a chave só é gasta por uma operação efetivada). Chave ausente
    ou inválida não é recuperável pelo reenvio: a tela volta com uma chave nova.
    """

    def get(self, request):
        setor = _setor_do_formulario(request.GET.get("setor"))
        marcados = {
            Papel(codigo) for codigo in request.GET.getlist("papeis") if codigo in Papel.values
        }
        form = UsuarioCadastroForm(
            initial={
                "chave_confirmacao": uuid.uuid4(),
                "setor": setor.pk if setor else None,
                "papeis": [papel.value for papel in marcados],
            }
        )
        if request.headers.get("HX-Request") == "true":
            resposta = render(
                request,
                "contas/organizacao/_papeis_cadastro.html",
                {"form": form, **_contexto_de_papeis_do_cadastro(setor, marcados)},
            )
            patch_vary_headers(resposta, ["HX-Request"])
            return resposta
        return self._formulario(request, form, setor=setor, marcados=marcados)

    def post(self, request):
        form = UsuarioCadastroForm(request.POST)
        if not form.is_valid():
            if "chave_confirmacao" in form.errors:
                form = self._com_chave_nova(request)
            return self._formulario(request, form)
        dados = form.cleaned_data
        try:
            usuario, senha = self.executar(
                cadastrar_usuario,
                request.user,
                matricula=dados["matricula"],
                nome=dados["nome"],
                setor_id=dados["setor"].pk,
                papeis_adicionais={Papel(papel) for papel in dados["papeis"]},
                chave_confirmacao=dados["chave_confirmacao"],
            )
        except OperacaoJaExecutada as repetida:
            messages.warning(request, MENSAGEM_JA_EXECUTADA)
            return redirect("usuario", pk=repetida.evento.usuario_id)
        except OperacaoRecusada as recusa:
            if recusa.codigo == RECUSA_MATRICULA_EM_USO:
                return self._matricula_em_uso(request, form, recusa, dados["matricula"])
            return self._formulario(request, form, recusa)
        usuario = User.objects.select_related("setor").prefetch_related("papeis").get(pk=usuario.pk)
        return render(
            request,
            "contas/organizacao/usuario_senha_entregue.html",
            {"usuario": usuario, "papeis": _rotulos_dos_papeis(usuario), "senha": senha},
        )

    def _com_chave_nova(self, request):
        dados = request.POST.copy()
        dados["chave_confirmacao"] = uuid.uuid4()
        form = UsuarioCadastroForm(dados)
        form.is_valid()
        form.add_error(
            None, "Não foi possível confirmar o envio. Confira os dados e envie de novo."
        )
        return form

    def _matricula_em_uso(self, request, form, recusa, matricula):
        """A recusa de matrícula repetida vira erro do campo `matricula`; `conta_existente`
        (`pk`, `nome`, `ativo`, `situacao`) leva à ficha da conta e, se inativa, à reativação. A
        conta técnica não tem ficha: o erro fica, sem `conta_existente`."""
        form.add_error("matricula", recusa.motivo)
        existente = User.objects.filter(matricula=matricula, is_superuser=False).first()
        conta = None
        if existente is not None:
            conta = {
                "pk": existente.pk,
                "nome": existente.nome,
                "ativo": existente.is_active,
                "situacao": "Ativo" if existente.is_active else "Inativo",
            }
        return self._formulario(request, form, conta_existente=conta)

    def _formulario(
        self, request, form, recusa=None, *, conta_existente=None, setor=None, marcados=None
    ):
        if setor is None:
            setor = _setor_do_formulario(form["setor"].value())
        if marcados is None:
            marcados = {
                Papel(codigo) for codigo in form["papeis"].value() or [] if codigo in Papel.values
            }
        return render(
            request,
            "contas/organizacao/usuario_form.html",
            {
                "form": form,
                "recusa": recusa,
                "conta_existente": conta_existente,
                **_contexto_de_papeis_do_cadastro(setor, marcados),
            },
        )


class UsuarioFichaView(_AdministracaoView, View):
    """`usuario`: ficha com dados, papéis, situação da credencial e histórico paginado.
    A conta técnica não existe para estas telas (404, FR-004)."""

    def get(self, request, pk):
        usuario = get_object_or_404(
            User.objects.filter(is_superuser=False)
            .select_related("setor")
            .prefetch_related("papeis"),
            pk=pk,
        )
        estado, momento = _situacao_da_credencial(usuario)
        pagina, eventos = _historico(
            request,
            EventoOrganizacional.objects.filter(
                Q(usuario=usuario) | Q(usuario_relacionado=usuario)
            ),
        )
        return render(
            request,
            "contas/organizacao/usuario.html",
            {
                "usuario": usuario,
                "papeis": _rotulos_dos_papeis(usuario),
                "credencial_estado": estado,
                "credencial_momento": momento,
                "impedimento_transferir": impedimento_de_transferir_usuario(usuario),
                "impedimento_desativar": impedimento_de_desativar_usuario(request.user, usuario),
                "pode_desativar": usuario.is_active,
                "pode_reativar": not usuario.is_active,
                "pagina": pagina,
                "eventos": eventos,
            },
        )


class UsuariosView(_AdministracaoView, View):
    """`usuarios`: lista paginada (50) com busca por nome ou matrícula e filtros de setor,
    situação e papel. Com `HX-Request`, só a região de resultados. Nunca lista a conta técnica."""

    def get(self, request):
        filtro = FiltroUsuariosForm(request.GET)
        filtro.is_valid()  # valor inválido de um filtro é ignorado: só os válidos entram
        escolhas = filtro.cleaned_data
        usuarios = (
            User.objects.filter(is_superuser=False)
            .select_related("setor")
            .prefetch_related("papeis")
            .order_by("nome_busca", "matricula")
        )
        if termo := escolhas.get("q", "").strip():
            usuarios = usuarios.filter(
                Q(nome_busca__contains=normalizar_para_busca(termo)) | Q(matricula=termo)
            )
        if escolhas.get("setor"):
            usuarios = usuarios.filter(setor=escolhas["setor"])
        if escolhas.get("situacao"):
            usuarios = usuarios.filter(is_active=escolhas["situacao"] == "ativo")
        if escolhas.get("papel"):
            usuarios = usuarios.filter(papeis__papel=escolhas["papel"])

        pagina = Paginator(usuarios, TAMANHO_PAGINA_USUARIOS).get_page(request.GET.get("pagina"))
        linhas = list(pagina.object_list)
        for usuario in linhas:
            usuario.rotulos_dos_papeis = _rotulos_dos_papeis(usuario)
        htmx = request.headers.get("HX-Request") == "true"
        resposta = render(
            request,
            "contas/organizacao/_resultados_usuarios.html"
            if htmx
            else "contas/organizacao/usuarios.html",
            {"filtro": filtro, "pagina": pagina, "usuarios": linhas},
        )
        patch_vary_headers(resposta, ["HX-Request"])
        return resposta


class SetoresView(_AdministracaoView, View):
    """`setores`: lista com situação, chefe, membros ativos (a conta técnica não conta) e a
    marca de Almoxarifado, numa única consulta, com busca por nome e filtro de situação."""

    def get(self, request):
        filtro = FiltroSetoresForm(request.GET)
        filtro.is_valid()
        escolhas = filtro.cleaned_data
        chefes = User.objects.filter(
            setor=OuterRef("pk"),
            is_active=True,
            is_superuser=False,
            papeis__papel=Papel.CHEFE_SETOR,
        )
        setores = Setor.objects.annotate(
            chefe_pk=Subquery(chefes.values("pk")[:1]),
            chefe_nome=Subquery(chefes.values("nome")[:1]),
            membros_ativos=Count("user", filter=Q(user__is_active=True, user__is_superuser=False)),
        ).order_by("nome")
        if termo := escolhas.get("q", "").strip():
            setores = setores.filter(nome__icontains=termo)
        if escolhas.get("situacao"):
            setores = setores.filter(ativo=escolhas["situacao"] == "ativo")
        return render(
            request, "contas/organizacao/setores.html", {"filtro": filtro, "setores": setores}
        )


class SetorFichaView(_AdministracaoView, View):
    """`setor`: ficha com dados, chefe, membros ativos e inativos (sem a conta técnica) e
    histórico paginado."""

    def get(self, request, pk):
        setor = get_object_or_404(Setor, pk=pk)
        membros = list(
            User.objects.filter(setor=setor, is_superuser=False)
            .prefetch_related("papeis")
            .order_by("-is_active", "nome_busca", "matricula")
        )
        chefe = chefes_ativos(setor.pk).filter(is_superuser=False).first()
        for membro in membros:
            membro.rotulos_dos_papeis = _rotulos_dos_papeis(membro)
            if not membro.is_active:
                # O papel de chefe fica preservado na conta inativa (FR-019), mas ela não chefia.
                membro.rotulos_dos_papeis = [
                    f"{rotulo} (inativo)" if rotulo == Papel.CHEFE_SETOR.label else rotulo
                    for rotulo in membro.rotulos_dos_papeis
                ]
        prontidao = [] if setor.ativo else prontidao_do_setor(setor)
        acao_chefia = "substituir" if setor.ativo else ("retirar" if chefe else "designar")
        pagina, eventos = _historico(
            request,
            EventoOrganizacional.objects.filter(Q(setor=setor) | Q(setor_relacionado=setor)),
        )
        return render(
            request,
            "contas/organizacao/setor.html",
            {
                "setor": setor,
                "chefe": chefe,
                "acao_chefia": acao_chefia,
                "pode_ativar": not setor.ativo,
                "pode_desativar": setor.ativo and not setor.almoxarifado,
                "prontidao": prontidao,
                "impedimento_ativar": next(
                    (item["recusa"] for item in prontidao if item["recusa"]), None
                ),
                "impedimento_desativar": impedimento_de_desativar_setor(setor),
                "membros": membros,
                "pagina": pagina,
                "eventos": eventos,
            },
        )


# ---------------------------------------------------------------------------
# Manutenção de usuários e chefia de setor (feature 005, US3 e US4)
# ---------------------------------------------------------------------------


def _usuario_administravel(pk):
    """Usuário de negócio da URL; a conta técnica não existe para estas telas (404, FR-004)."""
    return get_object_or_404(
        User.objects.filter(is_superuser=False).select_related("setor").prefetch_related("papeis"),
        pk=pk,
    )


class UsuarioEditarView(_OperacaoView):
    """`usuario_editar`: nome e matrícula (correção). Sem mudança volta à ficha sem evento."""

    def get(self, request, pk):
        usuario = _usuario_administravel(pk)
        form = UsuarioEdicaoForm(initial={"nome": usuario.nome, "matricula": usuario.matricula})
        return self._tela(request, usuario, form)

    def post(self, request, pk):
        usuario = _usuario_administravel(pk)
        form = UsuarioEdicaoForm(request.POST)
        if not form.is_valid():
            return self._tela(request, usuario, form)
        nome, matricula = form.cleaned_data["nome"], form.cleaned_data["matricula"]
        try:
            self.executar(editar_usuario, request.user, usuario.pk, nome=nome, matricula=matricula)
        except OperacaoRecusada as recusa:
            return self._tela(request, usuario, form, recusa)
        if (nome, matricula) == (usuario.nome, usuario.matricula):
            messages.info(request, "Nenhuma alteração nos dados do usuário.")
        else:
            messages.success(request, "Dados do usuário atualizados.")
        return redirect("usuario", pk=usuario.pk)

    def _tela(self, request, usuario, form, recusa=None):
        return render(
            request,
            "contas/organizacao/usuario_editar.html",
            {"usuario": usuario, "form": form, "recusa": recusa},
        )


class UsuarioPapeisView(_OperacaoView):
    """`usuario_papeis`: os sete papéis com o estado atual. POST traz o conjunto desejado; a view
    calcula o que conceder e remover, e a operação decide. Os papéis que a operação recusaria
    alternar aparecem bloqueados, com o motivo — mas o servidor é quem decide (FR-048)."""

    def get(self, request, pk):
        usuario = _usuario_administravel(pk)
        atuais = self._atuais(usuario)
        return self._tela(request, usuario, UsuarioPapeisForm(), atuais)

    def post(self, request, pk):
        usuario = _usuario_administravel(pk)
        atuais = self._atuais(usuario)
        form = UsuarioPapeisForm(request.POST)
        if not form.is_valid():
            return self._tela(request, usuario, form, atuais)
        desejados = {Papel(papel) for papel in form.cleaned_data["papeis"]}
        conceder, remover = desejados - atuais, atuais - desejados
        if not (conceder or remover):
            messages.info(request, "Nenhuma alteração nos papéis.")
            return redirect("usuario", pk=usuario.pk)
        try:
            self.executar(
                alterar_papeis, request.user, usuario.pk, conceder=conceder, remover=remover
            )
        except OperacaoRecusada as recusa:
            return self._tela(request, usuario, form, atuais, recusa, marcados=desejados)
        messages.success(request, "Papéis atualizados.")
        return redirect("usuario", pk=usuario.pk)

    def _atuais(self, usuario):
        return {Papel(papel.papel) for papel in usuario.papeis.all()}

    def _tela(self, request, usuario, form, atuais, recusa=None, marcados=None):
        """`papeis`: um item por papel — `marcado` (o desejado, ou o atual), `atual` e `bloqueio`
        (a recusa que alternar o papel daria, ou `None`). Um papel bloqueado e atribuído vai
        também como campo oculto: o checkbox desabilitado não é enviado e a conta não pode
        perdê-lo por omissão."""
        bloqueios = bloqueios_de_papeis(usuario)
        marcados = atuais if marcados is None else marcados
        papeis = [
            {
                "papel": papel,
                "atual": papel in atuais,
                "marcado": papel in atuais if papel in bloqueios else papel in marcados,
                "bloqueio": bloqueios.get(papel),
            }
            for papel in Papel
        ]
        return render(
            request,
            "contas/organizacao/usuario_papeis.html",
            {"usuario": usuario, "form": form, "papeis": papeis, "recusa": recusa},
        )


class UsuarioTransferirView(_OperacaoView):
    """`usuario_transferir`, em duas etapas sobre o mesmo POST: sem `confirmar` mostra a prévia
    com os papéis que serão removidos; com `confirmar` e os papéis previstos executa. Se os
    efeitos recalculados forem outros, mostra a prévia nova e não executa (FR-049)."""

    def get(self, request, pk):
        usuario = _usuario_administravel(pk)
        return self._escolha(request, usuario, TransferenciaForm())

    def post(self, request, pk):
        usuario = _usuario_administravel(pk)
        form = TransferenciaForm(request.POST)
        if not form.is_valid():
            return self._escolha(request, usuario, form)
        destino = form.cleaned_data["setor"]
        try:
            if form.cleaned_data["confirmar"]:
                previstos = {
                    Papel(papel) for papel in form.cleaned_data["papeis_removidos_previstos"]
                }
                try:
                    self.executar(
                        transferir_usuario,
                        request.user,
                        usuario.pk,
                        destino.pk,
                        papeis_removidos_previstos=previstos,
                    )
                except PreviaDesatualizada as desatualizada:
                    return self._previa(request, usuario, desatualizada.previa)
                messages.success(
                    request, f"{usuario.nome} foi transferido para o setor {destino.nome}."
                )
                return redirect("usuario", pk=usuario.pk)
            previa = self.executar(previa_transferencia, usuario.pk, destino.pk)
        except OperacaoRecusada as recusa:
            return self._escolha(request, usuario, form, recusa)
        return self._previa(request, usuario, previa)

    def _escolha(self, request, usuario, form, recusa=None):
        """`impedimento`: a recusa que a transferência dá por quem o usuário é (chefe de setor
        ativo), com o `destino_impedimento` para resolvê-la; com ele a tela explica e não oferece
        o formulário. O POST segue recusado pela operação."""
        setores = Setor.objects.exclude(pk=usuario.setor_id).order_by("nome")
        impedimento = impedimento_de_transferir_usuario(usuario)
        return render(
            request,
            "contas/organizacao/usuario_transferir.html",
            {
                "usuario": usuario,
                "form": form,
                "setores": setores,
                "recusa": _recusa_alem_do_impedimento(recusa, impedimento),
                "impedimento": impedimento,
                "destino_impedimento": _destino_do_impedimento(impedimento, usuario.setor),
            },
        )

    def _previa(self, request, usuario, previa):
        return render(
            request,
            "contas/organizacao/usuario_transferir.html",
            {"usuario": usuario, "previa": previa},
        )


AUTORIDADE_DE_ESTOQUE = (
    "A autoridade exclusiva de estoque do chefe do almoxarifado — estorno, devolução e saída "
    "excepcional, entre outras atribuições — passa de {anterior} para {novo}. Só quem chefia o "
    "almoxarifado a exerce: depois da substituição, {anterior} deixa de poder exercê-la."
)


def _autoridade_de_estoque(previa):
    """O que a prévia da substituição diz sobre a autoridade exclusiva de estoque, ou `None` fora
    do Almoxarifado: `{"anterior", "novo", "texto"}`. Descreve a mudança de `ROLE-WAREHOUSE-HEAD`
    que a prévia já calcula; não cria nem concede capability."""
    if previa is None or Papel.CHEFE_ALMOXARIFADO not in previa.novo_ganha:
        return None
    return {
        "anterior": previa.chefe_atual,
        "novo": previa.novo_chefe,
        "texto": AUTORIDADE_DE_ESTOQUE.format(
            anterior=previa.chefe_atual.nome, novo=previa.novo_chefe.nome
        ),
    }


class SetorChefiaView(_OperacaoView):
    """`setor_chefia`: o estado do setor decide a operação — ativo: substituição (escolha →
    prévia → confirmação, com `chefe_esperado` e os efeitos previstos; se os efeitos recalculados
    forem outros, mostra a prévia nova e não executa, como em `usuario_transferir`); inativo sem
    chefe ativo: designação; inativo com chefe: retirada (com confirmação). Candidatos oferecidos:
    membros ativos do setor; a decisão sobre quem pode ser chefe é da operação."""

    def get(self, request, pk):
        setor = get_object_or_404(Setor, pk=pk)
        estado, chefe = self._estado(setor)
        return self._tela(request, setor, estado, chefe, ChefiaForm(estado=estado))

    def post(self, request, pk):
        setor = get_object_or_404(Setor, pk=pk)
        estado, chefe = self._estado(setor)
        # A tela envia o estado que mostrou. Se o setor mudou desde então, nada é executado: sem
        # isto, a confirmação de uma substituição viraria retirada da chefia (FR-049). A retirada,
        # a única operação acionada só por `confirmar`, exige o estado no envio.
        estado_visto = request.POST.get("estado", "")
        if estado_visto != estado and (estado_visto or estado == "retirar"):
            mudou = OperacaoRecusada(
                "A situação do setor mudou desde que você abriu esta tela.",
                "Confira a situação atual e escolha de novo.",
            )
            form = ChefiaForm(estado=estado)
            return self._tela(request, setor, estado, chefe, form, recusa=mudou)
        form = ChefiaForm(request.POST, estado=estado)
        if not form.is_valid():
            return self._tela(request, setor, estado, chefe, form)
        dados = form.cleaned_data
        try:
            if estado == "retirar":
                if not dados["confirmar"]:
                    return self._tela(request, setor, estado, chefe, form)
                ex_chefe = self.executar(retirar_chefia, request.user, setor.pk)
                mensagem = f"A chefia do setor {setor.nome} foi retirada de {ex_chefe.nome}."
            elif estado == "designar":
                novo = self.executar(designar_chefia, request.user, setor.pk, dados["usuario"])
                mensagem = f"{novo.nome} foi designado chefe do setor {setor.nome}."
            elif dados["confirmar"]:
                try:
                    novo = self.executar(
                        substituir_chefia,
                        request.user,
                        setor.pk,
                        chefe_esperado_id=dados["chefe_esperado"],
                        novo_chefe_id=dados["novo_chefe"],
                        novo_ganha_previsto=dados["novo_ganha_previsto"],
                        anterior_perde_previsto=dados["anterior_perde_previsto"],
                    )
                except PreviaDesatualizada as desatualizada:
                    return self._tela(
                        request, setor, estado, chefe, form, previa=desatualizada.previa
                    )
                mensagem = f"{novo.nome} é o novo chefe do setor {setor.nome}."
            else:
                previa = self.executar(previa_substituicao, setor.pk, dados["novo_chefe"])
                return self._tela(request, setor, estado, chefe, form, previa=previa)
        except OperacaoRecusada as recusa:
            return self._tela(request, setor, estado, chefe, form, recusa=recusa)
        messages.success(request, mensagem)
        return redirect("setor", pk=setor.pk)

    def _estado(self, setor):
        """`(estado, chefe)`: `substituir`, `retirar` ou `designar`; `chefe` pode ser `None`."""
        chefe = chefes_ativos(setor.pk).filter(is_superuser=False).first()
        if setor.ativo:
            return "substituir", chefe
        return ("retirar" if chefe else "designar"), chefe

    def _tela(self, request, setor, estado, chefe, form, recusa=None, previa=None):
        """Além do contrato do template: `autoridade_de_estoque` (na prévia da substituição do
        Almoxarifado: quem perde e quem passa a ter a autoridade exclusiva de estoque, com o texto
        fixo ligado a `ROLE-WAREHOUSE-HEAD`) e, na escolha sem candidatos, os links
        `url_cadastrar_no_setor` e `url_usuarios`."""
        candidatos = []
        if previa is None and estado != "retirar":
            candidatos = User.objects.filter(
                setor=setor, is_active=True, is_superuser=False
            ).order_by("nome_busca", "matricula")
            if chefe is not None:
                candidatos = candidatos.exclude(pk=chefe.pk)
        return render(
            request,
            "contas/organizacao/setor_chefia.html",
            {
                "setor": setor,
                "estado": estado,
                "chefe": chefe,
                "candidatos": candidatos,
                "form": form,
                "recusa": recusa,
                "previa": previa,
                "autoridade_de_estoque": _autoridade_de_estoque(previa),
                "url_cadastrar_no_setor": f"{reverse('usuario_novo')}?setor={setor.pk}",
                "url_usuarios": reverse("usuarios"),
            },
        )


# ---------------------------------------------------------------------------
# Situação do usuário, redefinição de senha e administração de setores
# (feature 005, US5, US6 e US7)
# ---------------------------------------------------------------------------


class UsuarioDesativarView(_OperacaoView):
    """`usuario_desativar`: confirmação com justificativa opcional. Sem `confirmar` só mostra a
    tela; a decisão sobre a própria conta, o último administrador e o chefe de setor ativo é da
    operação. Conta já inativa volta à ficha com um aviso."""

    def get(self, request, pk):
        usuario = _usuario_administravel(pk)
        if not usuario.is_active:
            return self._ja_inativo(request, usuario)
        return self._tela(request, usuario, DesativacaoForm())

    def post(self, request, pk):
        usuario = _usuario_administravel(pk)
        if not usuario.is_active:
            return self._ja_inativo(request, usuario)
        form = DesativacaoForm(request.POST)
        if not form.is_valid() or not form.cleaned_data["confirmar"]:
            return self._tela(request, usuario, form)
        try:
            self.executar(
                desativar_usuario,
                request.user,
                usuario.pk,
                justificativa=form.cleaned_data["justificativa"],
            )
        except OperacaoRecusada as recusa:
            return self._tela(request, usuario, form, recusa)
        messages.success(request, f"{usuario.nome} foi desativado.")
        return redirect("usuario", pk=usuario.pk)

    def _ja_inativo(self, request, usuario):
        messages.info(request, f"{usuario.nome} já está inativo.")
        return redirect("usuario", pk=usuario.pk)

    def _tela(self, request, usuario, form, recusa=None):
        """`impedimento`: a recusa que a desativação daria hoje, com o `destino_impedimento` para
        resolvê-la; com ele a tela explica e não oferece o botão de confirmar. O POST segue
        recusado pela operação."""
        impedimento = impedimento_de_desativar_usuario(self.request.user, usuario)
        return render(
            request,
            "contas/organizacao/usuario_desativar.html",
            {
                "usuario": usuario,
                "form": form,
                "recusa": _recusa_alem_do_impedimento(recusa, impedimento),
                "impedimento": impedimento,
                "destino_impedimento": _destino_do_impedimento(impedimento, usuario.setor),
            },
        )


class UsuarioReativarView(_OperacaoView):
    """`usuario_reativar`: revisão dos papéis preservados. O POST traz o conjunto MANTIDO
    (`papeis`) e, na segunda etapa, `confirmar`. `ROLE-REQUESTER` segue marcado e travado (campo
    oculto, como em `usuario_papeis`); cada papel que a reativação recusaria mostra o motivo da
    prévia na própria linha — mas o servidor é quem decide (FR-048). Conta inativa que perdeu
    `ROLE-REQUESTER` não pode ser reativada: a tela leva à de papéis. Conta já ativa volta à
    ficha com um aviso."""

    def get(self, request, pk):
        usuario = _usuario_administravel(pk)
        if usuario.is_active:
            return self._ja_ativo(request, usuario)
        return self._tela(request, usuario, ReativacaoForm())

    def post(self, request, pk):
        usuario = _usuario_administravel(pk)
        if usuario.is_active:
            return self._ja_ativo(request, usuario)
        form = ReativacaoForm(request.POST)
        if not form.is_valid():
            return self._tela(request, usuario, form)
        mantidos = {Papel(papel) for papel in form.cleaned_data["papeis"]}
        if not form.cleaned_data["confirmar"]:
            return self._tela(request, usuario, form, marcados=mantidos)
        try:
            self.executar(reativar_usuario, request.user, usuario.pk, papeis_mantidos=mantidos)
        except OperacaoRecusada as recusa:
            return self._tela(request, usuario, form, recusa, marcados=mantidos)
        messages.success(request, f"{usuario.nome} foi reativado.")
        return redirect("usuario", pk=usuario.pk)

    def _ja_ativo(self, request, usuario):
        messages.info(request, f"{usuario.nome} já está ativo.")
        return redirect("usuario", pk=usuario.pk)

    def _tela(self, request, usuario, form, recusa=None, marcados=None):
        """`papeis`: um item por papel preservado — `marcado` (o desejado; na primeira abertura,
        todos), `travado` (`ROLE-REQUESTER`) e `recusa` (a que mantê-lo daria, ou `None`)."""
        previa = previa_reativacao(usuario.pk)
        papeis = [
            {
                "papel": papel,
                "marcado": papel == Papel.REQUISITANTE or marcados is None or papel in marcados,
                "travado": papel == Papel.REQUISITANTE,
                "recusa": previa.recusas.get(papel),
            }
            for papel in previa.papeis_preservados
        ]
        return render(
            request,
            "contas/organizacao/usuario_reativar.html",
            {
                "usuario": usuario,
                "form": form,
                "papeis": papeis,
                "recusa": recusa,
                "recusa_sem_requisitante": previa.recusa_sem_requisitante,
            },
        )


@method_decorator(never_cache, name="dispatch")
class UsuarioRedefinirSenhaView(_OperacaoView):
    """`usuario_redefinir_senha`: confirmação → `redefinir_senha`. Como o cadastro, o POST de
    sucesso devolve 200 com a nova senha provisória, uma única vez, sem redirect e sem cache (R8,
    FR-031): nada de senha em sessão, mensagem, log ou evento. Repetir o POST (mesma
    `chave_confirmacao`) avisa e leva à ficha. Chave ausente ou inválida volta com chave nova."""

    def get(self, request, pk):
        usuario = _usuario_administravel(pk)
        form = RedefinicaoSenhaForm(initial={"chave_confirmacao": uuid.uuid4()})
        return self._tela(request, usuario, form)

    def post(self, request, pk):
        usuario = _usuario_administravel(pk)
        form = RedefinicaoSenhaForm(request.POST)
        if not form.is_valid():
            return self._tela(request, usuario, self._com_chave_nova())
        try:
            senha = self.executar(
                redefinir_senha,
                request.user,
                usuario.pk,
                chave_confirmacao=form.cleaned_data["chave_confirmacao"],
            )
        except OperacaoJaExecutada:
            messages.warning(request, MENSAGEM_JA_EXECUTADA)
            return redirect("usuario", pk=usuario.pk)
        except OperacaoRecusada as recusa:
            return self._tela(request, usuario, form, recusa)
        return render(
            request,
            "contas/organizacao/usuario_senha_entregue.html",
            {
                "usuario": usuario,
                "papeis": _rotulos_dos_papeis(usuario),
                "senha": senha,
                "redefinicao": True,
            },
        )

    def _com_chave_nova(self):
        form = RedefinicaoSenhaForm({"chave_confirmacao": uuid.uuid4()})
        form.is_valid()
        form.add_error(None, "Não foi possível confirmar o envio. Envie de novo.")
        return form

    def _tela(self, request, usuario, form, recusa=None):
        return render(
            request,
            "contas/organizacao/usuario_redefinir_senha.html",
            {"usuario": usuario, "form": form, "recusa": recusa},
        )


class SetorNovoView(_OperacaoView):
    """`setor_novo`: cria o setor (inativo, nunca Almoxarifado) e leva à ficha."""

    def get(self, request):
        return self._tela(request, SetorForm())

    def post(self, request):
        form = SetorForm(request.POST)
        if not form.is_valid():
            return self._tela(request, form)
        try:
            setor = self.executar(criar_setor, request.user, nome=form.cleaned_data["nome"])
        except OperacaoRecusada as recusa:
            return self._tela(request, form, recusa)
        messages.success(request, f"Setor {setor.nome} criado. Ele nasce inativo.")
        return redirect("setor", pk=setor.pk)

    def _tela(self, request, form, recusa=None):
        return render(
            request, "contas/organizacao/setor_form.html", {"form": form, "recusa": recusa}
        )


class SetorEditarView(_OperacaoView):
    """`setor_editar`: renomeia o setor. Sem mudança volta à ficha sem evento."""

    def get(self, request, pk):
        setor = get_object_or_404(Setor, pk=pk)
        return self._tela(request, setor, SetorForm(initial={"nome": setor.nome}))

    def post(self, request, pk):
        setor = get_object_or_404(Setor, pk=pk)
        form = SetorForm(request.POST)
        if not form.is_valid():
            return self._tela(request, setor, form)
        nome = form.cleaned_data["nome"]
        try:
            self.executar(renomear_setor, request.user, setor.pk, nome=nome)
        except OperacaoRecusada as recusa:
            return self._tela(request, setor, form, recusa)
        if nome == setor.nome:
            messages.info(request, "Nenhuma alteração no nome do setor.")
        else:
            messages.success(request, "Nome do setor atualizado.")
        return redirect("setor", pk=setor.pk)

    def _tela(self, request, setor, form, recusa=None):
        return render(
            request,
            "contas/organizacao/setor_form.html",
            {"setor": setor, "form": form, "recusa": recusa},
        )


class _SetorConfirmacaoView(_OperacaoView):
    """Base de `setor_ativar` e `setor_desativar`: GET mostra a confirmação; POST sem `confirmar`
    também; com `confirmar` executa e volta à ficha. Setor que já está no estado pedido volta à
    ficha com um aviso; o que impede a mudança é decisão da operação (FR-048). As subclasses dão
    o template, o estado que dispensa a operação, as mensagens e a chamada da operação."""

    template_name = None
    aviso_ja_no_estado = ""
    mensagem_sucesso = ""

    def ja_no_estado(self, setor):
        raise NotImplementedError

    def executar_operacao(self, request, setor):
        raise NotImplementedError

    def impedimento_de(self, setor):
        """A recusa que a operação daria hoje, só de leitura (ou `None`)."""
        raise NotImplementedError

    def get(self, request, pk):
        setor = get_object_or_404(Setor, pk=pk)
        if self.ja_no_estado(setor):
            return self._aviso(request, setor)
        return self._tela(request, setor, ConfirmacaoForm())

    def post(self, request, pk):
        setor = get_object_or_404(Setor, pk=pk)
        if self.ja_no_estado(setor):
            return self._aviso(request, setor)
        form = ConfirmacaoForm(request.POST)
        if not (form.is_valid() and form.cleaned_data["confirmar"]):
            return self._tela(request, setor, form)
        try:
            self.executar_operacao(request, setor)
        except OperacaoRecusada as recusa:
            return self._tela(request, setor, form, recusa)
        messages.success(request, self.mensagem_sucesso.format(setor=setor.nome))
        return redirect("setor", pk=setor.pk)

    def _aviso(self, request, setor):
        messages.info(request, self.aviso_ja_no_estado.format(setor=setor.nome))
        return redirect("setor", pk=setor.pk)

    def _tela(self, request, setor, form, recusa=None):
        """`impedimento`: a recusa que a operação daria hoje, com o `destino_impedimento` para
        resolvê-la; com ele a tela explica e não oferece o botão de confirmar. O POST segue
        recusado pela operação."""
        chefe = chefes_ativos(setor.pk).filter(is_superuser=False).first()
        impedimento = self.impedimento_de(setor)
        return render(
            request,
            self.template_name,
            {
                "setor": setor,
                "chefe": chefe,
                "form": form,
                "recusa": _recusa_alem_do_impedimento(recusa, impedimento),
                "impedimento": impedimento,
                "destino_impedimento": _destino_do_impedimento(impedimento, setor),
            },
        )


class SetorAtivarView(_SetorConfirmacaoView):
    """`setor_ativar`: a ativação exige um chefe ativo do próprio setor (FR-027)."""

    template_name = "contas/organizacao/setor_ativar.html"
    aviso_ja_no_estado = "O setor {setor} já está ativo."
    mensagem_sucesso = "O setor {setor} foi ativado."

    def ja_no_estado(self, setor):
        return setor.ativo

    def executar_operacao(self, request, setor):
        return self.executar(ativar_setor, request.user, setor.pk)

    def impedimento_de(self, setor):
        return impedimento_de_ativar_setor(setor)


class SetorDesativarView(_SetorConfirmacaoView):
    """`setor_desativar`: só com o chefe como único membro ativo; nunca o Almoxarifado ativado."""

    template_name = "contas/organizacao/setor_desativar.html"
    aviso_ja_no_estado = "O setor {setor} já está inativo."
    mensagem_sucesso = "O setor {setor} foi desativado."

    def ja_no_estado(self, setor):
        return not setor.ativo

    def executar_operacao(self, request, setor):
        return self.executar(desativar_setor, request.user, setor.pk)

    def impedimento_de(self, setor):
        return impedimento_de_desativar_setor(setor)
