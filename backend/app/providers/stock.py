"""Stock B-roll from whichever provider has a key: Pexels first, then Pixabay."""
from . import pexels, pixabay

PROVIDERS = {"pexels": pexels, "pixabay": pixabay}


def active():
    return [m for m in PROVIDERS.values() if m.configured()]


def configured():
    return bool(active())


def names():
    return [k for k, m in PROVIDERS.items() if m.configured()]


def search(query, per_page=8):
    """Results from the first configured provider that returns any; raises only if every provider fails."""
    errors = []
    for m in active():
        try:
            res = m.search(query, per_page=per_page)
        except Exception as e:
            errors.append(e)
            continue
        if res:
            return res
    if errors and len(errors) == len(active()):
        raise errors[0]
    return []


def download(item, dest):
    return PROVIDERS[item.get("provider", "pexels")].download(item, dest)
