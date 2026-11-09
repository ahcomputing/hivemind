from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "deploy_mailserver.py"
SPEC = spec_from_file_location("deploy_mailserver", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_rendered_mailserver_config_proxies_to_both_traefik_nodes() -> None:
    config = MODULE.render_config(("10.1.111.154:80", "10.1.111.155:80"))

    assert "server_name hivemind.ahcomputing.com;" in config
    assert "server 10.1.111.154:80" in config
    assert "server 10.1.111.155:80" in config
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in config


def test_tls_config_redirects_http_and_keeps_the_proxy_at_https() -> None:
    config = MODULE.render_config(("10.1.111.154:80",), tls_enabled=True)

    assert "return 301 https://$host$request_uri;" in config
    assert "listen 443 ssl;" in config
    assert "ssl_certificate /etc/letsencrypt/live/hivemind.ahcomputing.com/fullchain.pem;" in config
