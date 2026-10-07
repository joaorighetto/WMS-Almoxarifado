"""Leitura estrutural de HTML para testes de markup (só `html.parser` da biblioteca padrão).

Os testes de shell, navegação e Home precisam responder perguntas como "quais `href` há dentro
desta `<nav>`?" ou "este `<script>` está no `<head>`?". Regex sobre atributos quebra com ordem de
atributos, aspas e quebras de linha; aqui o HTML vira uma árvore pequena e as consultas são
sobre tags, atributos e posição no documento.

Não é um parser conforme à especificação HTML5 (não corrige marcação inválida como um navegador):
é suficiente para os templates do projeto, que são bem formados. Tags void e `<x ... />` não
abrem nível.
"""

from html.parser import HTMLParser

_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


class No:
    """Elemento da árvore. `filhos` guarda só elementos, na ordem do documento."""

    def __init__(self, tag, attrs, pai=None):
        self.tag = tag
        self.attrs = {nome: (valor if valor is not None else "") for nome, valor in attrs}
        self.pai = pai
        self.filhos = []
        self._dados = []
        # Texto e elementos filhos intercalados na ordem do documento (para `texto_corrido`).
        self._conteudo = []

    def get(self, nome, padrao=None):
        return self.attrs.get(nome, padrao)

    def tem_classe(self, classe):
        return classe in self.attrs.get("class", "").split()

    @property
    def texto(self):
        """Texto de todos os descendentes, espaços colapsados."""
        pedacos = list(self._dados)
        pedacos.extend(filho.texto for filho in self.filhos)
        return " ".join(" ".join(pedacos).split())

    def _texto_cru(self):
        return "".join(
            item if isinstance(item, str) else item._texto_cru() for item in self._conteudo
        )

    @property
    def texto_cru(self):
        """O `textContent` sem nenhuma normalização (nem `\\xa0` vira espaço, nem `\\n` some).

        `texto` e `texto_corrido` usam `str.split()`, que trata o espaço não separável como
        espaço comum; use este quando a diferença for o que se quer verificar.
        """
        return self._texto_cru()

    @property
    def texto_corrido(self):
        """O `textContent` do elemento, na ordem do documento, espaços colapsados.

        Diferente de `texto` (texto próprio primeiro, depois o dos filhos, separados por espaço):
        aqui `Confirmar<small>: 9</small>` vira "Confirmar: 9", como o navegador o lê.
        """
        return " ".join(self._texto_cru().split())

    def descendentes(self):
        """Todos os elementos abaixo deste, em ordem de documento (pré-ordem)."""
        for filho in self.filhos:
            yield filho
            yield from filho.descendentes()

    def buscar(self, tag=None, *, classe=None, **attrs):
        """Descendentes que casam com `tag`, `classe` e igualdade de atributos.

        Um valor `True` em `attrs` exige só a presença do atributo; underscores no nome viram
        hífens (`aria_current="page"` -> `aria-current`).
        """
        achados = []
        for no in self.descendentes():
            if tag is not None and no.tag != tag:
                continue
            if classe is not None and not no.tem_classe(classe):
                continue
            casou = True
            for nome, esperado in attrs.items():
                nome = nome.replace("_", "-")
                if nome not in no.attrs or (esperado is not True and no.attrs[nome] != esperado):
                    casou = False
                    break
            if casou:
                achados.append(no)
        return achados

    def unico(self, tag=None, **criterios):
        """O único descendente que casa; falha se houver zero ou mais de um."""
        achados = self.buscar(tag, **criterios)
        assert len(achados) == 1, (
            f"esperava exatamente 1 elemento {tag or '*'} {criterios}, achou {len(achados)}"
        )
        return achados[0]

    def ancestrais(self):
        no = self.pai
        while no is not None:
            yield no
            no = no.pai

    def esta_dentro_de(self, tag):
        return any(ancestral.tag == tag for ancestral in self.ancestrais())


class _Construtor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = No("[documento]", [])
        self._pilha = [self.raiz]

    def handle_starttag(self, tag, attrs):
        no = No(tag, attrs, self._pilha[-1])
        self._pilha[-1].filhos.append(no)
        self._pilha[-1]._conteudo.append(no)
        if tag not in _VOID:
            self._pilha.append(no)

    def handle_startendtag(self, tag, attrs):
        no = No(tag, attrs, self._pilha[-1])
        self._pilha[-1].filhos.append(no)
        self._pilha[-1]._conteudo.append(no)

    def handle_endtag(self, tag):
        # Fecha até o último elemento aberto de mesma tag; um fechamento sem abertura é ignorado.
        for posicao in range(len(self._pilha) - 1, 0, -1):
            if self._pilha[posicao].tag == tag:
                del self._pilha[posicao:]
                return

    def handle_data(self, dados):
        self._pilha[-1]._dados.append(dados)
        self._pilha[-1]._conteudo.append(dados)


def analisar(conteudo):
    """Árvore do HTML (`str` ou `bytes` de uma resposta)."""
    if isinstance(conteudo, bytes):
        conteudo = conteudo.decode()
    construtor = _Construtor()
    construtor.feed(conteudo)
    construtor.close()
    return construtor.raiz


def secao_por_rotulo(documento, id_rotulo):
    """O elemento com `aria-labelledby="<id_rotulo>"` (único)."""
    return documento.unico(aria_labelledby=id_rotulo)


def totais_do_resumo(documento):
    """`{rótulo: valor}` dos tiles do resumo de uma execução (`dt.k` / `dd.v` dentro de `.tiles`).

    Responde "qual total está ao lado de qual rótulo" sem depender de espaçamento do markup. Os
    valores saem como o usuário os lê (com separador de milhar); falha se o rótulo se repetir.
    """
    totais = {}
    for tile in documento.unico(classe="tiles").buscar(classe="tile"):
        rotulo = tile.unico("dt", classe="k").texto
        assert rotulo not in totais, f"rótulo duplicado no resumo: {rotulo!r}"
        totais[rotulo] = tile.unico("dd", classe="v").texto
    return totais


def hrefs_de(no):
    """Conjunto dos `href` dos `<a>` dentro de `no`."""
    return {link.attrs["href"] for link in no.buscar("a", href=True)}
