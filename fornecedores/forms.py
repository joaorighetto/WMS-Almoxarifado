"""Formulários do app `fornecedores`.

`ArquivoFornecedoresForm` (US1, T016) valida o upload do CSV de fornecedores
do SCPI antes de qualquer leitura de domínio: só tamanho e presença do
arquivo, no mesmo molde de `catalogo.forms.ArquivoImportacaoForm`. A
validação de estrutura, cabeçalho e registros (`contracts/
arquivo-fornecedores.md`) é responsabilidade de
`fornecedores.leitura_fornecedores.ler_fornecedores`, chamada por
`fornecedores.importacao.guardar_pedido` — o formulário não reprocessa o
arquivo duas vezes; a view trata `catalogo.leitura_scpi.ArquivoRecusado`
propagada por `guardar_pedido` como erro deste campo.

`ConsultaFornecedoresForm` (US2, T022) valida os parâmetros de `GET
/fornecedores/` (`contracts/rotas-e-autorizacao.md` → "Consulta"), no molde
de `catalogo.forms.ConsultaCatalogoForm`.
"""

from django import forms

from catalogo.leitura_scpi import LIMITE_TAMANHO_ARQUIVO
from fornecedores.leitura_fornecedores import PADRAO_CODIF, somente_digitos

# Mensagem compartilhada com `fornecedores.views._HandlerUploadEmMemoria`:
# quando o upload handler de memória já rejeita o corpo da requisição por
# tamanho (nunca chega a `request.FILES`), a view precisa reportar o MESMO
# erro que `clean_arquivo` reportaria se o arquivo tivesse chegado ao campo.
MENSAGEM_ARQUIVO_TAMANHO_EXCEDIDO = "O arquivo excede o limite de 10 MB."


class ArquivoFornecedoresForm(forms.Form):
    """Formulário de envio do arquivo de fornecedores
    (`contracts/rotas-e-autorizacao.md` → "POST /fornecedores/importacao/").

    Em caso de sucesso, o conteúdo já lido fica disponível em
    `self.conteudo_arquivo` (bytes), para a view não precisar reler o
    arquivo enviado.
    """

    arquivo = forms.FileField(
        required=True,
        label="Arquivo de fornecedores (CSV)",
        # `allow_empty_file=True`: um upload de 0 bytes não é recusado aqui
        # — é o caso "zero recebidos, sem erro" do contrato
        # (`contracts/arquivo-fornecedores.md` §1), decidido por
        # `ler_fornecedores`.
        allow_empty_file=True,
        widget=forms.FileInput(
            attrs={
                "class": "file-upload-input",
                "data-file-upload-input": "",
                "accept": ".csv",
            }
        ),
    )

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]

        if arquivo.size > LIMITE_TAMANHO_ARQUIVO:
            raise forms.ValidationError(
                MENSAGEM_ARQUIVO_TAMANHO_EXCEDIDO,
                code="ARQUIVO_TAMANHO_EXCEDIDO",
            )

        self.conteudo_arquivo = arquivo.read()
        return arquivo


class ConsultaFornecedoresForm(forms.Form):
    """Filtros de `GET /fornecedores/` (US2, FR-027–FR-029).

    `codigo`, `nome` e `documento` são opcionais e combinados por E
    (`ConsultaFornecedoresView`). `clean_codigo` só apara as bordas do valor
    digitado — nunca completa, preenche zeros nem trata o valor como prefixo
    (`INV-SUPPLIER-001`): fora do formato `[0-9]+` é erro de validação, não
    uma busca parcial. `clean_documento` devolve só os dígitos do termo
    (`cleaned_data["documento"]` já pronto para `documento_digitos=`); vazio
    não é erro — é ausência de filtro; menos de 3 dígitos é erro.
    """

    codigo = forms.CharField(
        required=False,
        label="Código (CODIF)",
        widget=forms.TextInput(attrs={"inputmode": "numeric"}),
    )
    nome = forms.CharField(required=False, label="Nome")
    documento = forms.CharField(
        required=False,
        label="Documento",
        widget=forms.TextInput(attrs={"inputmode": "numeric"}),
    )

    def clean_codigo(self):
        codigo = self.cleaned_data.get("codigo", "").strip()
        if codigo and not PADRAO_CODIF.fullmatch(codigo):
            raise forms.ValidationError(
                "Informe só os dígitos do código.",
                code="CODIGO_FORMATO_INVALIDO",
            )
        return codigo

    def clean_documento(self):
        documento = self.cleaned_data.get("documento", "")
        if documento.strip() == "":
            return ""
        digitos = somente_digitos(documento)
        if len(digitos) < 3:
            raise forms.ValidationError(
                "Informe o CNPJ ou CPF completo.",
                code="DOCUMENTO_MINIMO_DIGITOS",
            )
        return digitos
