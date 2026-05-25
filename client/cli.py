#!/usr/bin/env python3
"""CLI del cliente DFS"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from client.config import NAMENODE_URL
from client.file_ops import DfsAuthError, DfsClient, DfsError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dfs",
        description="Cliente CLI para el sistema de archivos distribuido por bloques",
    )
    parser.add_argument(
        "--namenode",
        default=NAMENODE_URL,
        help=f"URL del NameNode (default: {NAMENODE_URL})",
    )
    parser.add_argument("--token", help="JWT token (omite login si ya tienes uno)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Logs detallados")
    parser.add_argument("-q", "--quiet", action="store_true", help="Solo errores")

    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("register", help="Registrar usuario")
    reg.add_argument("username")
    reg.add_argument("password")

    login = sub.add_parser("login", help="Iniciar sesión y guardar token")
    login.add_argument("username")
    login.add_argument("password")
    login.add_argument("--no-save", action="store_true", help="No guardar sesión en disco")

    sub.add_parser("whoami", help="Usuario autenticado actual")

    put = sub.add_parser("put", help="Subir archivo al DFS")
    put.add_argument("local_path", type=Path)
    put.add_argument("remote_name", nargs="?", help="Nombre remoto (default: nombre local)")

    get = sub.add_parser("get", help="Descargar archivo del DFS")
    get.add_argument("remote_name")
    get.add_argument("local_path", type=Path)

    sub.add_parser("ls", help="Listar archivos del usuario")

    rm = sub.add_parser("rm", help="Eliminar archivo remoto")
    rm.add_argument("filename")

    mkdir = sub.add_parser("mkdir", help="Crear directorio remoto")
    mkdir.add_argument("dirname")

    rmdir = sub.add_parser("rmdir", help="Eliminar directorio remoto")
    rmdir.add_argument("dirname")

    sub.add_parser("health", help="Estado del NameNode")

    return parser


def _resolve_client(args: argparse.Namespace) -> DfsClient:
    if args.token:
        return DfsClient(namenode_url=args.namenode, token=args.token)
    loaded = DfsClient.load_session()
    if loaded and (not args.namenode or loaded.namenode_url == args.namenode.rstrip("/")):
        if args.namenode:
            loaded.namenode_url = args.namenode.rstrip("/")
        return loaded
    if args.command in ("register", "login", "health"):
        return DfsClient(namenode_url=args.namenode)
    raise DfsAuthError("No session found. Run: dfs login <user> <password>")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)

    try:
        with _resolve_client(args) as client:
            return _dispatch(client, args)
    except DfsAuthError as exc:
        print(f"Auth error: {exc}", file=sys.stderr)
        return 2
    except DfsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _dispatch(client: DfsClient, args: argparse.Namespace) -> int:
    cmd = args.command

    if cmd == "register":
        result = client.register(args.username, args.password)
        print(json.dumps(result, indent=2))
        return 0

    if cmd == "login":
        client.login(args.username, args.password)
        if not args.no_save:
            client.save_session(args.username)
        print(f"Logged in as {args.username}")
        return 0

    if cmd == "whoami":
        resp = client._namenode_request("GET", "/auth/me")
        print(json.dumps(resp.json(), indent=2))
        return 0

    if cmd == "health":
        print(json.dumps(client.health(), indent=2))
        return 0

    if cmd == "put":
        result = client.put_file(args.local_path, args.remote_name)
        print(json.dumps(result, indent=2))
        return 0

    if cmd == "get":
        out = client.get_file(args.remote_name, args.local_path)
        print(f"Downloaded to {out}")
        return 0

    if cmd == "ls":
        files = client.list_files()
        if not files:
            print("(empty)")
            return 0
        for entry in files:
            kind = "DIR " if entry.get("is_directory") else "FILE"
            print(
                f"{kind}  {entry['filename']:30}  "
                f"{entry.get('size', 0):>10} B  "
                f"blocks={entry.get('block_count', 0)}  "
                f"status={entry.get('status', '?')}"
            )
        return 0

    if cmd == "rm":
        print(json.dumps(client.remove_file(args.filename), indent=2))
        return 0

    if cmd == "mkdir":
        print(json.dumps(client.mkdir(args.dirname), indent=2))
        return 0

    if cmd == "rmdir":
        print(json.dumps(client.rmdir(args.dirname), indent=2))
        return 0

    raise DfsError(f"Unknown command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
