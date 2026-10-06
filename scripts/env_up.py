"""Start a WebArena-Verified site container and wait for health."""
import sys, time
from webarena_verified.environments.container.manager import ContainerManager
from webarena_verified.environments.container.config import DEFAULT_CONTAINER_CONFIGS
from webarena_verified.types.task import WebArenaSite

site = WebArenaSite(sys.argv[1] if len(sys.argv) > 1 else "shopping_admin")
cfg = DEFAULT_CONTAINER_CONFIGS[site]
print(f"site={site.value} img={cfg.docker_img} host_port={cfg.host_port} envctrl={cfg.host_env_ctrl_port}")
cm = ContainerManager(site=site)
t0 = time.time()
res = cm.start(port=cfg.host_port, env_ctrl_port=cfg.host_env_ctrl_port, wait=True, timeout=300)
print(f"started in {time.time()-t0:.0f}s")
print(f"  container : {res.container_name}")
print(f"  url       : {res.url}")
print(f"  env_ctrl  : {res.env_ctrl_url}")
