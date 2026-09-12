"""Administração exclusivamente pelo terminal do servidor; sem endpoint administrativo."""
import argparse
import json

from .settings import Settings
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="Administração NEXORA")
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
    store = Store(Settings.from_env())
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
