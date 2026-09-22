"""Formulários do catálogo.

`ArquivoImportacaoForm` (US1, T025) valida o upload do arquivo de carga do
SCPI antes de qualquer leitura de domínio: tamanho e estrutura do cabeçalho.
A extensão do arquivo não é critério (o conteúdo é validado pelo parser).

`ConsultaCatalogoForm` (US2, T032) valida os parâmetros de `GET
/catalogo/` (`contracts/rotas-e-autorizacao.md`).
"""

from django import forms

from catalogo import leitura_scpi


class ArquivoImportacaoForm(forms.Form):
    """Formulário de envio do arquivo de carga do catálogo
    (`contracts/rotas-e-autorizacao.md` → "GET/POST /catalogo/importacao/").

    Em caso de sucesso, o conteúdo já lido fica disponível em
    `self.conteudo_arquivo` (bytes), para a view não precisar reler o
    arquivo enviado.
    """

    arquivo = forms.FileField(
        required=True,
        label="Arquivo do catálogo (CSV)",
        # `allow_empty_file=True`: um upload de 0 bytes não é recusado aqui
        # com uma mensagem genérica — é o caso "zero recebidos, sem erro"
        # do contrato (`contracts/arquivo-scpi.md` §1, I-2/`research.md`
        # R4), decidido por `verificar_arquivo`/`ler_registros`.
        allow_empty_file=True,
        # Atributos do primitivo File Upload (DESIGN.md → Components → File
        # Upload; `static/css/components.css`, T028/T029): `accept` é só uma
        # dica de navegador (a extensão não é critério de validação, ver
        # docstring da classe); `data-file-upload-input` liga o campo ao
        # comportamento opcional de `catalogo/static/catalogo/js/envio.js`.
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

        if arquivo.size > leitura_scpi.LIMITE_TAMANHO_ARQUIVO:
            raise forms.ValidationError(
                "O arquivo excede o limite de 10 MB.",
                code="ARQUIVO_TAMANHO_EXCEDIDO",
            )

        conteudo = arquivo.read()
        try:
            leitura_scpi.verificar_arquivo(conteudo)
        except leitura_scpi.ArquivoRecusado as exc:
            raise forms.ValidationError(exc.mensagem, code=exc.codigo) from exc

        self.conteudo_arquivo = conteudo
        return arquivo


class ConsultaCatalogoForm(forms.Form):
    """Filtros de `GET /catalogo/` (US2, FR-039).

    `codigo` e `descricao` são opcionais. `clean_codigo` só apara as bordas
    do valor digitado — nunca completa, preenche zeros nem trata o valor
    como prefixo (`INV-CATALOG-001`): fora do formato `XXX.YYY.ZZZ` é erro
    de validação, não uma busca parcial.
    """

    codigo = forms.CharField(required=False, label="Código (CADPRO)")
    descricao = forms.CharField(required=False, label="Descrição")

    def clean_codigo(self):
        codigo = self.cleaned_data.get("codigo", "").strip()
        if codigo and not leitura_scpi.PADRAO_CADPRO.fullmatch(codigo):
            raise forms.ValidationError(
                "Informe o código completo no formato XXX.YYY.ZZZ.",
                code="CODIGO_FORMATO_INVALIDO",
            )
        return codigo
