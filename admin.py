"""Administração exclusivamente pelo terminal do servidor; sem endpoint administrativo."""
import argparse
import json
import getpass
import re
from urllib.parse import urlsplit
from dataclasses import replace

from .settings import Settings
from .store import Store


def normalize_database_input(value):
    value = value.strip().lstrip("\ufeff")
    if not value:
        raise ValueError("O campo chegou vazio. Cole a conexão completa antes de confirmar.")
    if "\\" in value:
        raise ValueError("A conexão contém barras invertidas. Copie diretamente do Neon, não do texto formatado do chat.")
    if value.startswith("psql ") or value.startswith("psql\t"):
        value = value[4:].strip()
    elif value.startswith("DATABASE_URL="):
        value = value[len("DATABASE_URL="):].strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        value = value[1:-1]
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {"postgres", "postgresql"} and parsed.hostname
                 and parsed.username and parsed.password and parsed.path.strip("/")
                 and not parsed.fragment and not re.search(r"\s", value)
                 and "*" not in parsed.password)
        if not valid:
            raise ValueError()
    except ValueError:
        raise ValueError("Copie a Connection string completa do Neon, com a senha real. Ela começa com postgresql://. O endereço do Render não serve aqui.") from None
    return value


def ask_database_window():
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        while True:
            value = simpledialog.askstring(
                "Conectar ao banco da NEXORA",
                "Cole com Ctrl+V a conexão completa copiada do Neon.\n"
                "Ela começa com postgresql:// e contém a senha atual.\n"
                "O campo mostra asteriscos para proteger a senha.",
                parent=root, show="*",
            )
            if value is None:
                return None
            try:
                return normalize_database_input(value)
            except ValueError as exc:
                messagebox.showerror("Confira a conexão", str(exc), parent=root)
    finally:
        root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Administração NEXORA")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--database-prompt", action="store_true", help="Solicita conexão PostgreSQL sem exibir ou salvar")
    source.add_argument("--database-window", action="store_true", help="Abre campo de senha local para colar a conexão")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="Cria código individual, válido por 7 dias para resgate")
    create.add_argument("--label", required=True, help="Identificação interna; evite dados pessoais")
    create.add_argument("--days", type=int, default=7, help="Dias de acesso após a primeira ativação")
    for name in ("revoke", "reissue", "extend"):
        item = sub.add_parser(name)
        item.add_argument("user_id")
        if name == "extend":
            item.add_argument("--days", type=int, required=True)
    sub.add_parser("list")
    backup = sub.add_parser("backup")
    backup.add_argument("destination")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.database_window:
        database = ask_database_window()
        if database is None:
            print("Cancelado. Nenhum acesso foi criado.")
            return
        settings = replace(settings, database=database)
    if args.database_prompt:
        while True:
            try:
                database = normalize_database_input(getpass.getpass("Conexão PostgreSQL (oculta): "))
                break
            except ValueError as exc:
                print(str(exc))
        settings = replace(settings, database=database)
    print("Conectando ao banco...")
    store = Store(settings)
    if args.command == "create":
        user_id, code = store.provision(args.label, args.days)
        print(json.dumps({"user_id": user_id, "activation_code": code}))
    elif args.command == "reissue":
        print(json.dumps({"activation_code": store.reissue(args.user_id)}))
    elif args.command == "revoke":
        store.revoke(args.user_id)
        print("Acesso revogado.")
    elif args.command == "extend":
        store.extend(args.user_id, args.days)
        print("Acesso prorrogado; use reissue se a sessão foi perdida ou revogada.")
    elif args.command == "list":
        print(json.dumps(store.users(), ensure_ascii=False, indent=2))
    elif args.command == "backup":
        store.backup(args.destination)
        print("Backup concluído. Armazene também uma cópia fora do servidor.")


if __name__ == "__main__":
    main()
