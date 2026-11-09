#!/usr/bin/env python3
"""Configure HiveMind's mailserver Nginx route and public TLS certificate.

Run this script *on the mailserver*. It deliberately manages only
``hivemind.ahcomputing.com`` and prompts through sudo for privileged commands.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

HOSTNAME = "hivemind.ahcomputing.com"
MARKER = "# Managed by HiveMind deploy_mailserver.py"
SITE_AVAILABLE = Path("/etc/nginx/sites-available") / f"{HOSTNAME}.conf"
SITE_ENABLED = Path("/etc/nginx/sites-enabled") / f"{HOSTNAME}.conf"
DEFAULT_UPSTREAMS = ("10.1.111.154:80", "10.1.111.155:80")


def render_config(upstreams: tuple[str, ...], *, tls_enabled: bool = False) -> str:
    """Render a temporary HTTP or final HTTPS proxy configuration."""
    upstream_lines = "\n".join(
        f"    server {upstream} max_fails=3 fail_timeout=10s;" for upstream in upstreams
    )
    proxy_location = """        proxy_pass http://hivemind_traefik;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;"""
    if tls_enabled:
        servers = f"""server {{
    listen 80;
    listen [::]:80;
    server_name {HOSTNAME};
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {HOSTNAME};

    ssl_certificate /etc/letsencrypt/live/{HOSTNAME}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{HOSTNAME}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {{
{proxy_location}
    }}
}}
"""
    else:
        servers = f"""server {{
    listen 80;
    listen [::]:80;
    server_name {HOSTNAME};

    location / {{
{proxy_location}
    }}
}}
"""
    return f"""{MARKER}
upstream hivemind_traefik {{
{upstream_lines}
}}

{servers}
"""


def run(command: list[str], *, dry_run: bool) -> None:
    """Run a command or show the exact command during a dry run."""
    print("+", shlex.join(command))
    if not dry_run:
        subprocess.run(command, check=True)


def ensure_managed_or_new(site: Path) -> bool:
    """Reject another service's vhost and return whether ours already exists."""
    if not site.exists():
        return False
    if MARKER not in site.read_text(encoding="utf-8"):
        raise RuntimeError(f"refusing to overwrite unmanaged Nginx file: {site}")
    return True


def enabled_link_is_safe(link: Path, site: Path) -> bool:
    """Return whether the existing enabled path is absent or our expected link."""
    if not os.path.lexists(link):
        return True
    return link.is_symlink() and link.resolve() == site


def restore_site(
    *, existed: bool, backup: Path | None, created_link: bool, dry_run: bool
) -> None:
    """Restore the previous script-managed state when Nginx validation fails."""
    if existed and backup is not None:
        run(["sudo", "cp", "-a", str(backup), str(SITE_AVAILABLE)], dry_run=dry_run)
    elif not existed:
        run(["sudo", "unlink", str(SITE_AVAILABLE)], dry_run=dry_run)
    if created_link:
        run(["sudo", "unlink", str(SITE_ENABLED)], dry_run=dry_run)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upstream",
        action="append",
        dest="upstreams",
        default=None,
        metavar="HOST:PORT",
        help="Traefik endpoint; repeat to replace the two LAN defaults.",
    )
    parser.add_argument(
        "--email",
        help="Use non-interactive Certbot registration with this email address.",
    )
    parser.add_argument(
        "--skip-upstream-check",
        action="store_true",
        help="Do not perform the local proxied /readyz check before Certbot.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print privileged commands only.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    upstreams = tuple(args.upstreams or DEFAULT_UPSTREAMS)
    if not upstreams or any("/" in upstream or not upstream for upstream in upstreams):
        raise ValueError("each upstream must be a host:port value")
    if not enabled_link_is_safe(SITE_ENABLED, SITE_AVAILABLE):
        raise RuntimeError(f"refusing to replace unexpected enabled site: {SITE_ENABLED}")

    existed = ensure_managed_or_new(SITE_AVAILABLE)
    backup: Path | None = None
    if existed:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = SITE_AVAILABLE.with_name(f"{SITE_AVAILABLE.name}.bak-{timestamp}")
        run(["sudo", "cp", "-a", str(SITE_AVAILABLE), str(backup)], dry_run=args.dry_run)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as config_file:
        config_file.write(render_config(upstreams))
        temporary_config = Path(config_file.name)

    created_link = not os.path.lexists(SITE_ENABLED)
    site_installed = False
    try:
        run(["sudo", "install", "-m", "0644", str(temporary_config), str(SITE_AVAILABLE)], dry_run=args.dry_run)
        site_installed = True
        if created_link:
            run(["sudo", "ln", "-s", str(SITE_AVAILABLE), str(SITE_ENABLED)], dry_run=args.dry_run)
        run(["sudo", "nginx", "-t"], dry_run=args.dry_run)
        run(["sudo", "systemctl", "reload", "nginx"], dry_run=args.dry_run)

        if not args.skip_upstream_check:
            run(
                [
                    "curl",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--resolve",
                    f"{HOSTNAME}:80:127.0.0.1",
                    f"http://{HOSTNAME}/readyz",
                ],
                dry_run=args.dry_run,
            )

        # Certbot obtains or retains the existing certificate without modifying
        # the virtual-host file. That makes later reruns deterministic.
        certbot = ["sudo", "certbot", "certonly", "--nginx", "-d", HOSTNAME]
        if args.email:
            certbot.extend(["--non-interactive", "--agree-tos", "--email", args.email])
        run(certbot, dry_run=args.dry_run)
        temporary_config.write_text(
            render_config(upstreams, tls_enabled=True), encoding="utf-8"
        )
        run(["sudo", "install", "-m", "0644", str(temporary_config), str(SITE_AVAILABLE)], dry_run=args.dry_run)
        run(["sudo", "nginx", "-t"], dry_run=args.dry_run)
        run(["sudo", "systemctl", "reload", "nginx"], dry_run=args.dry_run)
    except subprocess.CalledProcessError:
        if site_installed:
            print("Restoring the prior managed Nginx configuration.", file=sys.stderr)
            restore_site(
                existed=existed,
                backup=backup,
                created_link=created_link,
                dry_run=args.dry_run,
            )
            run(["sudo", "nginx", "-t"], dry_run=args.dry_run)
            run(["sudo", "systemctl", "reload", "nginx"], dry_run=args.dry_run)
        raise
    finally:
        temporary_config.unlink(missing_ok=True)

    print(f"HiveMind is routed through Nginx for https://{HOSTNAME}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
