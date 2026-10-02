"""Utilitários de texto neutros, compartilhados entre apps.

Ficam fora de qualquer app de domínio para que `contas` possa gravar campos de
busca sem importar `catalogo` (que importa models): FR-051 da 005.
"""

import unicodedata


def normalizar_para_busca(texto: str) -> str:
    """Normaliza texto para comparação de busca (FR-040 da 001, FR-006 da 005).

    Remove acentuação (decomposição NFKD seguida da remoção dos caracteres de
    categoria Unicode `Mn`, marcas combinantes) e aplica `casefold()`. A mesma
    função grava os campos `*_busca` (`Material.descricao_busca`,
    `User.nome_busca`) e normaliza o termo digitado pelo usuário, para que a
    comparação seja simétrica (`research.md` R15 da 001).
    """
    sem_acento = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto)
        if unicodedata.category(caractere) != "Mn"
    )
    return sem_acento.casefold()
