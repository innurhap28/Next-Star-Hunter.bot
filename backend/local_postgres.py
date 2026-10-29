"""Prepare this PC's isolated PostgreSQL development cluster.

The official PostgreSQL Windows binaries must already exist under
backend/tmp/postgresql-runtime/pgsql/bin (or be placed there by the developer).
No Windows service, cloud deployment, production DB or system PATH is changed.

Setup: .\\.venv\\Scripts\\python.exe backend/local_postgres.py
Swagger: add --serve (defaults to http://127.0.0.1:8001/docs).
Stop DB: add --stop.
All passwords, local data and logs stay in ignored backend/.env or backend/tmp/.
"""
import argparse
import json
import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import URL

BACKEND = Path(__file__).resolve().parent
LOCAL = BACKEND / "tmp"
BIN = LOCAL / "postgresql-runtime" / "pgsql" / "bin"
DATA = LOCAL / "local-postgres-data"
STATE = LOCAL / "local-postgres-private.json"
INIT_MARKER = LOCAL / "local-postgres-initialized.json"
ENV_FILE = BACKEND / ".env"
LOG = LOCAL / "local-postgres.log"


class SetupError(Exception):
    pass


def run_command(args, output):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with output.open("ab") as log:
        result = subprocess.run([str(x) for x in args], stdout=log, stderr=subprocess.STDOUT,
                                creationflags=flags)
    if result.returncode:
        raise SetupError("PostgreSQL command failed. See backend/tmp/ local log files.")


def state_for_local_cluster():
    LOCAL.mkdir(exist_ok=True)
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    state = {"port": 55432, "admin": "nsh_local_admin", "admin_password": secrets.token_urlsafe(32),
             "user": "nsh_local", "password": secrets.token_urlsafe(32),
             "signing_key": secrets.token_hex(32)}
    with STATE.open("x", encoding="utf-8") as out:
        json.dump(state, out)
    return state


def write_local_env(state):
    url = URL.create("postgresql+psycopg", username=state["user"], password=state["password"],
                     host="127.0.0.1", port=state["port"], database="next_star_hunter_local")
    value = url.render_as_string(hide_password=False)
    if ENV_FILE.exists():
        existing = dotenv_values(ENV_FILE)
        if existing.get("DATABASE_URL") != value:
            raise SetupError("backend/.env already points elsewhere; it was not changed.")
        if len(existing.get("SECRET_KEY") or "") < 32:
            raise SetupError("SECRET_KEY in backend/.env must contain at least 32 characters.")
        return
    # Do not overwrite any existing developer configuration.
    with ENV_FILE.open("x", encoding="utf-8") as out:
        out.write("SECRET_KEY=" + state["signing_key"] + "\n")
        out.write("DATABASE_URL=" + value + "\nENABLE_API_DOCS=true\nSESSION_HTTPS_ONLY=false\n")


def setup_database():
    if not (BIN / "initdb.exe").is_file():
        raise SetupError("PostgreSQL Windows binaries are missing from "
                         "backend/tmp/postgresql-runtime/pgsql/bin.")
    state = state_for_local_cluster()
    if not INIT_MARKER.exists():
        if DATA.exists():
            raise SetupError("An incomplete local cluster exists. "
                             "Preserve it and inspect the init log before retrying.")
        password_file = LOCAL / "local-postgres-init-password.txt"
        password_file.write_text(state["admin_password"] + "\n", encoding="utf-8")
        run_command([BIN / "initdb.exe", "-D", DATA, "-U", state["admin"],
                     "--pwfile=" + str(password_file), "--auth=scram-sha-256",
                     "--encoding=UTF8", "--no-locale"],
                    LOCAL / "local-postgres-init.log")
        INIT_MARKER.write_text(json.dumps({"initialized": True}), encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    status = subprocess.run([str(BIN / "pg_ctl.exe"), "status", "-D", str(DATA)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=flags)
    if status.returncode:
        run_command([BIN / "pg_ctl.exe", "start", "-D", DATA, "-l", LOG, "-w", "-t", "30",
                     "-o", "-h 127.0.0.1 -p " + str(state["port"])],
                    LOCAL / "local-postgres-control.log")
    import psycopg
    from psycopg import sql
    with psycopg.connect(host="127.0.0.1", port=state["port"], user=state["admin"],
                         password=state["admin_password"], dbname="postgres",
                         autocommit=True, connect_timeout=5) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (state["user"],)).fetchone():
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(state["user"]), sql.Literal(state["password"])))
        for name in ["next_star_hunter_local", "next_star_hunter_test"]:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(name), sql.Identifier(state["user"])))
    write_local_env(state)
    # Credentials here belong only to this tool's local DB. Schema creation does
    # not consult a potentially unrelated root .env or operating-system DSN.
    from app import models  # noqa: F401  # register metadata
    from app.database import Base, build_engine
    local_url = dotenv_values(ENV_FILE)["DATABASE_URL"]
    engine = build_engine(local_url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    return state


def stop_database():
    if not INIT_MARKER.exists():
        return
    run_command([BIN / "pg_ctl.exe", "stop", "-D", DATA, "-m", "fast", "-w"],
                LOCAL / "local-postgres-control.log")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true",
                        help="Start local Swagger after DB preparation")
    parser.add_argument("--web-port", type=int, default=8001)
    parser.add_argument("--stop", action="store_true", help="Stop only this development DB cluster")
    args = parser.parse_args(argv)
    try:
        if args.stop:
            stop_database()
            print("Local development PostgreSQL stopped.")
            return 0
        state = setup_database()
        print("Local PostgreSQL ready on 127.0.0.1:" + str(state["port"])
              + ". users/chat_logs tables ready.", flush=True)
        if args.serve:
            # Explicitly use this development configuration for this process only.
            from dotenv import load_dotenv
            load_dotenv(ENV_FILE, override=True)
            import uvicorn
            print("Swagger: http://127.0.0.1:" + str(args.web_port) + "/docs", flush=True)
            uvicorn.run("app.main:app", host="127.0.0.1", port=args.web_port)
        return 0
    except SetupError as error:
        print(str(error), file=sys.stderr)
    except Exception as error:
        print("Local PostgreSQL setup failed (" + type(error).__name__
              + "). Check backend/tmp/ logs; do not publish credentials.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
