import socket
import webbrowser
import threading
import time
import uvicorn
import os
import sys

from app.network import get_primary_lan_ip, get_all_lan_ips
from app.tunnel import tunnel_manager

def find_free_port(start_port=8088, max_attempts=50):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port

def open_browser_delayed(url, delay=1.2):
    def _open():
        time.sleep(delay)
        print(f"\n🌐 Ouverture automatique de votre navigateur sur {url} ...\n")
        try:
            webbrowser.open(url)
        except Exception:
            print(f"Note : ouvrez manuellement votre navigateur sur {url}")
    threading.Thread(target=_open, daemon=True).start()

def main():
    port = find_free_port(8088)
    lan_ip = get_primary_lan_ip()
    local_url = f"http://localhost:{port}"
    lan_url = f"http://{lan_ip}:{port}" if lan_ip != "127.0.0.1" else local_url

    # Check for optional public internet tunnel flag
    enable_tunnel = "--tunnel" in sys.argv or "--public" in sys.argv
    tunnel_url = None

    # Set environment variables for the FastAPI app
    os.environ["PEDANTIX_PORT"] = str(port)
    os.environ["PEDANTIX_LAN_IP"] = lan_ip

    if enable_tunnel:
        print("\n⏳ Démarrage du tunnel Internet sécurisé (pour inviter des amis hors Wi-Fi)...")
        tunnel_url = tunnel_manager.start(port=port)
        if tunnel_url:
            print(f"✅ Tunnel Internet actif : {tunnel_url}\n")
        else:
            print("⚠️ Impossible de démarrer le tunnel Internet. Accès local maintenu.")

    tunnel_display = f"\n  \033[1;35m►\033[0m \033[1mLien Internet public (amis distants) :\033[0m \033[1;35m\033[4m{tunnel_url}\033[0m" if tunnel_url else "\n  \033[90m► Pour activer un lien Internet (hors Wi-Fi), cliquez sur le bouton dans le jeu ou lancez avec --tunnel\033[0m"

    banner = f"""
\033[1;36m╔═══════════════════════════════════════════════════════════════════╗\033[0m
\033[1;36m║\033[0m            \033[1;32m📖  PÉDANTIX - CONCOURS MULTIJOUEUR EN RÉSEAU  📖\033[0m        \033[1;36m║\033[0m
\033[1;36m║\033[0m         \033[1;37mLe premier qui trouve le titre de la page gagne !\033[0m         \033[1;36m║\033[0m
\033[1;36m╚═══════════════════════════════════════════════════════════════════╝\033[0m

  \033[1;33m►\033[0m \033[1mVotre accès local (Host)             :\033[0m \033[1;34m\033[4m{local_url}\033[0m
  \033[1;33m►\033[0m \033[1mAdresse réseau Wi-Fi pour vos amis   :\033[0m \033[1;32m\033[4m{lan_url}\033[0m{tunnel_display}
  
  \033[1;31m⚠️  ATTENTION :\033[0m \033[93mNe donnez JAMAIS '127.0.0.1' ou 'localhost' à vos amis !\033[0m
  \033[90m(Cette adresse ne fonctionne que sur votre PC. Donnez-leur l'adresse Wi-Fi ou Internet ci-dessus)\033[0m
  \033[90m(Appuyez sur Ctrl+C dans ce terminal pour quitter)\033[0m
"""
    print(banner)

    # Automatically launch user's browser (open LAN URL directly so copy from browser is valid)
    open_url = lan_url if lan_ip != "127.0.0.1" else local_url
    open_browser_delayed(open_url)

    # Run Uvicorn server bound to 0.0.0.0 for LAN access
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        log_level="warning",
        reload="--reload" in sys.argv
    )

if __name__ == "__main__":
    main()
