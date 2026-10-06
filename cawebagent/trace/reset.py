"""True state reset: destroy the container and recreate it from the image."""
import time, urllib.request
from webarena_verified.environments.container.manager import ContainerManager
from webarena_verified.environments.container.config import DEFAULT_CONTAINER_CONFIGS
from webarena_verified.types.task import WebArenaSite

def hard_reset(site_name: str = "shopping_admin", timeout: int = 300) -> str:
    """docker restart does NOT restore the DB. ContainerManager.start() removes
    the container first, so state returns to the image baseline."""
    site = WebArenaSite(site_name)
    cfg = DEFAULT_CONTAINER_CONFIGS[site]
    cm = ContainerManager(site=site)
    res = cm.start(port=cfg.host_port, env_ctrl_port=cfg.host_env_ctrl_port,
                   wait=True, timeout=timeout)
    for _ in range(timeout // 3):
        try:
            urllib.request.urlopen(res.url, timeout=3); return res.url
        except Exception: time.sleep(3)
    raise RuntimeError("site did not come up")
