"""
Serveur de développement du frontend, SANS cache navigateur.

    cd frontend
    python serve.py            # http://localhost:8080
    python serve.py 8090       # autre port

Remplace « python -m http.server 8080 ». Deux protections :
  1. Aucun cache navigateur (plus d'anciennes versions de JavaScript qui « reviennent »).
  2. Refuse de démarrer si le port est déjà utilisé. Sous Windows, « http.server » autorise deux
     serveurs sur le même port : un ANCIEN serveur oublié peut alors répondre à ta place et servir
     d'anciens fichiers sans aucun message d'erreur.
"""
import os
import socket
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class SansCache(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, fmt, *args):  # console plus calme : seulement les erreurs
        if args and str(args[1]).startswith(("4", "5")) and "favicon" not in str(args[0]):
            super().log_message(fmt, *args)


class Serveur(ThreadingHTTPServer):
    allow_reuse_address = False  # jamais de partage de port

    def server_bind(self):
        if os.name == "nt":  # Windows : interdit explicitement le partage du port
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def port_deja_utilise(port: int) -> bool:
    try:
        socket.create_connection(("localhost", port), timeout=1).close()
        return True
    except OSError:
        return False


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    if port_deja_utilise(port):
        print(f"\n❌ Le port {port} est DÉJÀ utilisé par un autre programme (souvent un ancien « python -m http.server »).")
        print("   Il répondrait à ta place avec d'anciens fichiers. Trouve-le et arrête-le :")
        print(f"     netstat -ano | findstr :{port}      (note le dernier nombre = PID)")
        print("     taskkill /PID <PID> /F")
        print(f"   ou lance celui-ci sur un autre port :  python serve.py {port + 10}")
        sys.exit(1)
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    try:
        httpd = Serveur(("", port), SansCache)
    except OSError as e:
        print(f"\n❌ Impossible d'ouvrir le port {port} : {e}")
        sys.exit(1)
    print(f"Frontend GEIF (sans cache) : http://localhost:{port}   — Ctrl+C pour arrêter")
    httpd.serve_forever()
