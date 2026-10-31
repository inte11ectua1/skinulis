"""Disposable Docker/TLS delivery smoke. No VPS, registry push or Telegram polling."""

import http.client
import json
import os
import re
import secrets
import ssl
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/compose.production.yaml"


def docker(
    *args: str, data: str | None = None, env: dict[str, str] | None = None
) -> str:
    result = subprocess.run(
        ["docker", *args],
        input=data,
        env=env,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Docker delivery test command failed (output withheld)")
    return result.stdout.strip()


def wait[T](action: Callable[[], T]) -> T:
    deadline = time.monotonic() + 90
    while True:
        try:
            return action()
        except Exception:
            if time.monotonic() > deadline:
                raise RuntimeError("Delivery test readiness timeout") from None
            time.sleep(0.5)


def main() -> int:
    names: list[str] = []
    networks: list[str] = []
    stage = "configuration"
    try:
        image = os.environ["T09_TEST_IMAGE"]
        if not (
            image == "skinulis-t09-test:local"
            or re.fullmatch(r"skinulis-ci:[0-9a-f]{40}", image)
        ):
            raise ValueError("Use an explicitly built disposable CI image")
        project = "skinulis-t09-test-" + uuid4().hex[:12]
        values = dict(
            APP_IMAGE="ghcr.io/inte11ectua1/skinulis@sha256:" + "0" * 64,
            COMPOSE_PROJECT_NAME=project,
            PUBLIC_DOMAIN="localhost",
            POSTGRES_DB="skinulis_delivery_test",
            POSTGRES_USER="skinulis_test",
            POSTGRES_PASSWORD=secrets.token_urlsafe(48),
            POSTGRES_VOLUME=project,
            JWT_SECRET_KEY=secrets.token_urlsafe(48),
            BOT_SERVICE_TOKEN=secrets.token_urlsafe(48),
            APP_ENV="test",
            POSTGRES_HOST="db",
            POSTGRES_PORT="5432",
        )
        env = dict(os.environ, **values)
        with tempfile.TemporaryDirectory() as temporary:
            empty_env = Path(temporary) / "empty.env"
            empty_env.touch()
            base = [
                "compose",
                "--env-file",
                str(empty_env),
                "-f",
                str(COMPOSE),
                "--profile",
                "polling",
            ]
            docker(*base, "config", "--quiet", env=env)
            config = json.loads(docker(*base, "config", "--format", "json", env=env))
            services = config["services"]
            assert all(
                not services[s].get("ports") for s in ("api", "db", "bot", "migrate")
            )
            assert {int(p["published"]) for p in services["caddy"]["ports"]} == {
                80,
                443,
            }
            assert config["volumes"]["postgres_data"]["external"] is True
            assert config["volumes"]["postgres_data"]["name"] == project
            assert services["bot"]["container_name"] == project + "-bot"
            assert services["bot"]["deploy"]["replicas"] == 1
            assert "database" not in services["bot"]["networks"]
            assert services["migrate"]["restart"] == "no"
            assert services["migrate"]["command"] == [
                "python",
                "-m",
                "app.core.migrate",
            ]
            assert all(
                services[s]["image"] == values["APP_IMAGE"]
                for s in ("api", "bot", "migrate")
            )
            assert all(
                key not in services["migrate"]["environment"]
                for key in ("JWT_SECRET_KEY", "BOT_SERVICE_TOKEN", "TELEGRAM_BOT_TOKEN")
            )

            stage = "networks and image"
            print(
                "Delivery smoke: config, digest selection, private ports and migration topology validated"
            )
            for suffix in ("application", "database", "edge"):
                name = project + "-" + suffix
                docker(
                    "network",
                    "create",
                    *(["--internal"] if suffix != "edge" else []),
                    name,
                )
                networks.append(name)
            app_net, db_net, edge_net = networks
            metadata = json.loads(docker("image", "inspect", image))[0]
            assert metadata["Config"]["User"] == "skinulis"
            baked = dict(v.split("=", 1) for v in metadata["Config"]["Env"])
            target = baked["APP_COMMIT_SHA"]
            assert re.fullmatch(r"[0-9a-f]{40}", target)
            assert target == os.environ.get("T09_EXPECTED_SHA", target)
            secured = [
                "--init",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
            ]
            docker(
                "run",
                "--rm",
                *secured,
                "--entrypoint",
                "python",
                image,
                "-c",
                "import app.main,bot.main,os; assert os.getuid()==10001",
            )

            def create(name: str, *args: str) -> None:
                docker("create", "--name", name, *args, env=env)
                names.append(name)

            db, api, caddy = (
                project + "-" + service for service in ("db", "api", "caddy")
            )
            test_volume = project + "-postgres"
            docker("volume", "create", "--label", "skinulis.test=T09", test_volume)
            db_args = [
                arg
                for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
                for arg in ("-e", key)
            ]
            create(
                db,
                "--network",
                db_net,
                "--network-alias",
                "db",
                "--mount",
                f"type=volume,source={test_volume},target=/var/lib/postgresql/data",
                *db_args,
                services["db"]["image"],
            )
            docker("start", db)
            wait(
                lambda: docker(
                    "exec",
                    db,
                    "pg_isready",
                    "-U",
                    values["POSTGRES_USER"],
                    "-d",
                    values["POSTGRES_DB"],
                )
            )
            stage = "cold migration"
            backend_args = [
                arg
                for key in (
                    "APP_ENV",
                    "POSTGRES_DB",
                    "POSTGRES_USER",
                    "POSTGRES_PASSWORD",
                    "POSTGRES_HOST",
                    "POSTGRES_PORT",
                )
                for arg in ("-e", key)
            ]
            docker(
                "run",
                "--rm",
                *secured,
                "--network",
                db_net,
                *backend_args,
                image,
                "python",
                "-m",
                "app.core.migrate",
                env=env,
            )
            create(
                api,
                *secured,
                "--network",
                app_net,
                "--network-alias",
                "api",
                *backend_args,
                "-e",
                "JWT_SECRET_KEY",
                "-e",
                "BOT_SERVICE_TOKEN",
                image,
            )
            docker("network", "connect", db_net, api)
            docker("start", api)

            def private(
                path: str, method: str = "GET", body: dict[str, Any] | None = None
            ) -> dict[str, Any]:
                code = (
                    "import json,os,sys; from urllib.request import Request,urlopen; "
                    "v=json.load(sys.stdin); h={'Content-Type':'application/json',"
                    "'X-Bot-Service-Token':os.environ['BOT_SERVICE_TOKEN'],'X-Telegram-ID':'123456'}; "
                    "r=Request('http://api:8000'+v['path'],method=v['method'],headers=h,"
                    "data=json.dumps(v['body']).encode() if v['body'] is not None else None); "
                    "print(json.dumps(json.load(urlopen(r,timeout=5))))"
                )
                return cast(
                    dict[str, Any],
                    json.loads(
                        docker(
                            "run",
                            "--rm",
                            *secured,
                            "--network",
                            app_net,
                            "--entrypoint",
                            "python",
                            "-e",
                            "BOT_SERVICE_TOKEN",
                            "-i",
                            image,
                            "-c",
                            code,
                            data=json.dumps(dict(path=path, method=method, body=body)),
                            env=env,
                        )
                    ),
                )

            wait(lambda: private("/health"))
            assert private("/version")["commit_sha"] == target
            profile = private("/internal/users/bootstrap", "POST", {})
            assert private("/internal/users/me")["id"] == profile["id"]
            docker("restart", db)
            wait(lambda: private("/health"))
            assert private("/internal/users/me")["id"] == profile["id"]
            assert (
                json.loads(docker("volume", "inspect", test_volume))[0]["Name"]
                == test_volume
            )
            print(
                f"Delivery smoke: DB restart preserves profile; disposable volume retained: {test_volume}"
            )
            assert (
                json.loads(docker("inspect", api))[0]["HostConfig"]["PortBindings"]
                == {}
            )
            assert (
                json.loads(docker("inspect", db))[0]["HostConfig"]["PortBindings"] == {}
            )

            stage = "Caddy TLS and routing"
            create(
                caddy,
                "--network",
                app_net,
                "--user",
                "10001:10001",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "NET_BIND_SERVICE",
                "--security-opt",
                "no-new-privileges:true",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--tmpfs",
                "/data:uid=10001,gid=10001,mode=0700",
                "--tmpfs",
                "/config:uid=10001,gid=10001,mode=0700",
                "-e",
                "PUBLIC_DOMAIN=localhost",
                "-p",
                "127.0.0.1::443",
                "-v",
                f"{ROOT / 'deploy/Caddyfile'}:/etc/caddy/Caddyfile:ro",
                services["caddy"]["image"],
            )
            docker("network", "connect", edge_net, caddy)
            docker("start", caddy)
            ca = Path(temporary) / "root.crt"
            # Older Docker engines cannot docker-cp this tmpfs. Read PUBLIC CA only.
            ca.write_text(
                wait(
                    lambda: docker(
                        "exec",
                        caddy,
                        "cat",
                        "/data/caddy/pki/authorities/local/root.crt",
                    )
                )
            )
            context = ssl.create_default_context(cafile=str(ca))
            port = int(
                json.loads(docker("inspect", caddy))[0]["NetworkSettings"]["Ports"][
                    "443/tcp"
                ][0]["HostPort"]
            )

            def request(
                path: str, *, method: str = "GET", headers: dict[str, str] | None = None
            ) -> tuple[int, bytes]:
                connection = http.client.HTTPSConnection(
                    "localhost", port, context=context, timeout=5
                )
                try:
                    connection.request(method, path, headers=headers or {})
                    response = connection.getresponse()
                    return response.status, response.read()
                finally:
                    connection.close()

            def ready() -> None:
                assert request("/health")[0] == 200

            wait(ready)
            for path in (
                "/",
                "/health",
                "/version",
                "/docs",
                "/redoc",
                "/openapi.json",
                "/health?q=%2Finternal",
            ):
                assert request(path)[0] == 200
            assert json.loads(request("/version")[1])["commit_sha"] == target
            assert request("/groups")[0] == 401
            variants = (
                "/internal",
                "/internal/",
                "/internal/users/me",
                "//internal/users/me",
                "///internal/users/me",
                "/%69nternal/users/me",
                "/%49nternal/users/me",
                "/internal%2fusers%2fme",
                "/internal%252fusers%252fme",
                "/%2569nternal/users/me",
                "/internal%5cusers/me",
                "/internal\\users/me",
                "/groups/../internal/users/me",
                "/groups/%2e%2e/internal/users/me",
                "/groups/%252e%252e/internal/users/me",
                "/./internal/users/me",
                "/internal;ignored/users/me",
                "/INTERNAL/users/me",
                "/internal%00/users/me",
                "https://localhost/internal/users/me",
                "//localhost/internal/users/me",
            )
            service = {
                "X-Bot-Service-Token": values["BOT_SERVICE_TOKEN"],
                "X-Telegram-ID": "123456",
            }
            for path in variants:
                assert request(path, headers=service)[0] in {400, 404}
            for method in ("POST", "HEAD", "OPTIONS", "TRACE", "CONNECT"):
                assert request("/internal/users/me", method=method, headers=service)[
                    0
                ] in {400, 404, 405}
            assert json.loads(
                request(
                    "/health",
                    headers={
                        "X-Original-URL": "/internal/users/me",
                        "X-Rewrite-URL": "/internal/users/me",
                    },
                )[1]
            ) == {"status": "ok", "database": "ok"}
            print(
                f"Delivery smoke: real TLS, DB health, exact SHA and {len(variants) + 5} negative routing cases passed; private service actor works"
            )
    except Exception as error:
        print(
            f"Delivery smoke failed at {stage}: {type(error).__name__}; raw diagnostics withheld"
        )
        return 1
    finally:
        # Only exact UUID-named resources created above. No volumes/prune/down -v.
        for name in reversed(names):
            docker("rm", "--force", name)
        for name in reversed(networks):
            docker("network", "rm", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
