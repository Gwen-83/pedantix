import subprocess
import threading
import re
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("pedantix.tunnel")

class TunnelManager:
    """Manages an instant zero-config public internet tunnel via SSH (localhost.run) or localtunnel."""
    def __init__(self):
        self.url: Optional[str] = None
        self.status: str = "inactive"  # "inactive", "starting", "active", "error"
        self.error: Optional[str] = None
        self.port: int = 8088
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def start(self, port: int = 8088, timeout: float = 12.0) -> Optional[str]:
        with self._lock:
            if self._proc and self._proc.poll() is None and self.url:
                return self.url

            self.port = port
            self.status = "starting"
            self.error = None
            self.url = None

            ready_event = threading.Event()

            def _worker():
                try:
                    cmd = [
                        "ssh",
                        "-o", "StrictHostKeyChecking=no",
                        "-o", "ServerAliveInterval=30",
                        "-o", "ServerAliveCountMax=3",
                        "-o", "ExitOnForwardFailure=yes",
                        "-R", f"80:localhost:{port}",
                        "nokey@localhost.run"
                    ]
                    self._proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1
                    )

                    start_time = time.time()
                    for line in self._proc.stdout:
                        line = line.strip()
                        # Match assigned public URL e.g. https://xxx.lhr.life
                        m = re.search(r"https://[a-zA-Z0-9.-]+\.lhr\.life", line)
                        if m:
                            self.url = m.group(0)
                            self.status = "active"
                            ready_event.set()
                            logger.info(f"Tunnel internet actif sur : {self.url}")
                            break
                        if time.time() - start_time > timeout:
                            break

                    # Monitor process while running
                    if self._proc:
                        self._proc.wait()
                        if self.status == "active":
                            self.status = "inactive"
                            self.url = None

                except Exception as e:
                    logger.error(f"Erreur démarrage tunnel: {e}")
                    self.error = str(e)
                    self.status = "error"
                    ready_event.set()

            thread = threading.Thread(target=_worker, daemon=True)
            thread.start()

        # Wait up to timeout seconds for the URL
        ready_event.wait(timeout=timeout)
        return self.url

    def stop(self):
        with self._lock:
            if self._proc:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                self._proc = None
            self.status = "inactive"
            self.url = None

    def get_info(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "url": self.url,
            "error": self.error,
            "port": self.port
        }

# Global singleton
tunnel_manager = TunnelManager()
