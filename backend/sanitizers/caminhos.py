import os


def contido_em(base: str, alvo: str) -> bool:
    """True when `alvo`, with symlinks resolved, lies inside `base` (#19)."""
    base_real = os.path.realpath(base)
    try:
        return os.path.commonpath([base_real, os.path.realpath(alvo)]) == base_real
    except ValueError:
        return False
