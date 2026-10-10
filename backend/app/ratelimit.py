"""
Limiteur de débit en mémoire (anti brute-force / anti-spam), sans dépendance.
Clé = nom de la règle + adresse IP (+ référence de réclamation si présente dans l'URL).
Suffisant pour une instance unique ; pour plusieurs instances il faudrait Redis.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def reinitialiser() -> None:
    with _lock:
        _hits.clear()


def limite(nom: str, maximum: int, fenetre_secondes: int):
    """Dépendance FastAPI : au plus `maximum` appels par `fenetre_secondes`."""
    def _dep(request: Request) -> None:
        ip = request.client.host if request.client else "inconnu"
        cible = request.path_params.get("rec_id", "")
        cle = f"{nom}:{ip}:{cible}"
        maintenant = time.monotonic()
        with _lock:
            q = _hits[cle]
            while q and maintenant - q[0] > fenetre_secondes:
                q.popleft()
            if len(q) >= maximum:
                attente = int(fenetre_secondes - (maintenant - q[0])) + 1
                raise HTTPException(429, f"Trop de tentatives. Réessayez dans {attente} s.",
                                    headers={"Retry-After": str(attente)})
            q.append(maintenant)
    return _dep
