import os


def contido_em(base: str, alvo: str) -> bool:
    """True when `alvo`, with symlinks resolved, lies inside `base` (#19)."""
    base_real = os.path.realpath(base)
    try:
        return os.path.commonpath([base_real, os.path.realpath(alvo)]) == base_real
    except ValueError:
        return False


def remover_links_externos(raiz: str) -> list:
    """Delete symlinks under `raiz` that resolve outside it; returns their relative paths, sorted."""
    removidos = []
    for dirpath, dirnames, filenames in os.walk(raiz):
        for nome in dirnames + filenames:
            caminho = os.path.join(dirpath, nome)
            if os.path.islink(caminho) and not contido_em(raiz, caminho):
                os.unlink(caminho)
                removidos.append(os.path.relpath(caminho, raiz).replace('\\', '/'))
    return sorted(removidos)
