from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

DB_PATH = Path(os.environ.get("BEACON_DB", str(Path(__file__).resolve().parent / "beacon.db")))


def money(cents: int) -> str:
    prefix = "-" if cents < 0 else ""
    inteiro, decimal = divmod(abs(cents), 100)
    return f"{prefix}R$ {inteiro:,}".replace(",", ".") + f",{decimal:02d}"


def parse_money(value: str, allow_zero: bool = False) -> int:
    raw = value.strip().replace("R$", "").replace(" ", "")
    if not raw:
        raise ValueError("Informe um valor.")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("Valor monetário inválido.") from exc
    if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero) or amount > 1000000000:
        raise ValueError("Valor fora do intervalo permitido.")
    cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if cents == 0 and not allow_zero:
        raise ValueError("Informe um valor maior que zero.")
    return cents


def read(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    result = input(f"{label}{suffix}: ").strip()
    return result if result else (default or "")


def parse_date(value: str) -> str:
    if not value.strip():
        return date.today().isoformat()
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as exc:
        raise ValueError("Use a data AAAA-MM-DD.") from exc


def read_password(prompt: str = "Senha: ") -> str:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        import getpass
        return getpass.getpass(prompt)
    letters: list[str] = []
    sys.stdout.write(prompt)
    sys.stdout.flush()
    if os.name == "nt":
        import msvcrt
        try:
            while True:
                key = msvcrt.getwch()
                if key in ("\r", "\n"):
                    break
                if key == "\x03":
                    raise KeyboardInterrupt
                if key in ("\x00", "\xe0"):
                    msvcrt.getwch()
                    continue
                if key == "\b":
                    if letters:
                        letters.pop()
                        sys.stdout.write("\b \b")
                elif key.isprintable():
                    letters.append(key)
                    sys.stdout.write("*")
                sys.stdout.flush()
        finally:
            print()
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_mode = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                key = sys.stdin.read(1)
                if key in ("\r", "\n"):
                    break
                if key == "\x03":
                    raise KeyboardInterrupt
                if key in ("\x7f", "\b"):
                    if letters:
                        letters.pop()
                        sys.stdout.write("\b \b")
                elif key.isprintable():
                    letters.append(key)
                    sys.stdout.write("*")
                sys.stdout.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_mode)
            print()
    return "".join(letters)


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260000).hex()


def authenticate(db: sqlite3.Connection) -> sqlite3.Row | None:
    while True:
        print("\n=== BEACON | ACESSO ===")
        print("1 - Entrar\n2 - Criar conta\n0 - Sair")
        action = read("Escolha")
        if action == "0":
            return None
        if action not in ("1", "2"):
            print("Opção inválida.")
            continue
        email = read("E-mail").lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            print("Informe um e-mail válido.")
            continue
        password = read_password()
        if action == "2":
            if len(password) < 8:
                print("A senha precisa ter pelo menos 8 caracteres.")
                continue
            confirmation = read_password("Confirme a senha: ")
            if password != confirmation:
                print("As senhas não coincidem.")
                continue
            name = read("Nome")
            if not name:
                print("Informe seu nome.")
                continue
            salt = secrets.token_bytes(16)
            try:
                with db:
                    db.execute("INSERT INTO users(name,email,salt,password_hash) VALUES(?,?,?,?)",
                               (name, email, salt.hex(), hash_password(password, salt)))
            except sqlite3.IntegrityError:
                print("E-mail já cadastrado.")
                continue
            print("Conta criada. Faça login para continuar.")
            continue
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user is not None and hmac.compare_digest(user["password_hash"], hash_password(password, bytes.fromhex(user["salt"]))):
            return user
        print("Credenciais inválidas.")


def show_profile(db: sqlite3.Connection, uid: int) -> None:
    user = db.execute("SELECT name,email FROM users WHERE id=?", (uid,)).fetchone()
    if user:
        print(f"\nPerfil: {user['name']} | {user['email']}")
        print("Dados armazenados somente no banco SQLite local.")


def init_db(db: sqlite3.Connection) -> None:
    db.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            kind TEXT NOT NULL CHECK(kind IN ('receita','despesa')),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            discretionary INTEGER NOT NULL CHECK(discretionary IN (0,1)),
            occurred_on TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, occurred_on);
    """)
    db.commit()


def add_transaction(db: sqlite3.Connection, uid: int) -> None:
    action = read("Tipo (1=receita, 2=despesa)")
    if action not in ("1", "2"):
        print("Tipo inválido.")
        return
    try:
        amount = parse_money(read("Valor (ex.: 125,50)"))
        category = read("Categoria (ex.: Bolsa, Moradia, Lazer)")
        if not category:
            raise ValueError("Informe uma categoria.")
        description = read("Descrição", "Sem descrição")
        discretionary = 0
        if action == "2":
            flag = read("Gasto não obrigatório? (s/n)", "n").lower()
            if flag not in ("s", "n"):
                raise ValueError("Responda s ou n.")
            discretionary = int(flag == "s")
        occurred_on = parse_date(read("Data AAAA-MM-DD (Enter = hoje)"))
        with db:
            db.execute("INSERT INTO transactions(user_id,kind,amount_cents,category,description,discretionary,occurred_on) VALUES(?,?,?,?,?,?,?)",
                       (uid, "receita" if action == "1" else "despesa", amount, category, description, discretionary, occurred_on))
        print("Transação registrada.")
        pass
    except ValueError as exc:
        print(f"Erro: {exc}")


def list_transactions(db: sqlite3.Connection, uid: int) -> None:
    rows = db.execute("SELECT id,kind,amount_cents,category,description,discretionary,occurred_on FROM transactions WHERE user_id=? ORDER BY occurred_on DESC,id DESC LIMIT 100", (uid,)).fetchall()
    if not rows:
        print("Nenhuma transação encontrada.")
        return
    print("\n=== ÚLTIMAS TRANSAÇÕES ===")
    for entry in rows:
        optional = " | opcional" if entry["kind"] == "despesa" and entry["discretionary"] else ""
        print(f"#{entry['id']} | {entry['occurred_on']} | {entry['kind']:7} | {money(entry['amount_cents'])} | {entry['category']} | {entry['description']}{optional}")


def delete_transaction(db: sqlite3.Connection, uid: int) -> None:
    list_transactions(db, uid)
    text = read("ID para excluir (Enter cancela)")
    if not text:
        return
    try:
        tid = int(text)
    except ValueError:
        print("ID inválido.")
        return
    if read("Confirmar exclusão? (s/n)", "n").lower() != "s":
        return
    with db:
        result = db.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (tid, uid))
    if result.rowcount:
        print("Transação excluída.")
        pass
    else:
        print("Transação não localizada.")


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        init_db(db)
        print("BEACON MVP | Terminal | Etapa 2 de 10")
        user = authenticate(db)
        if user is None:
            return
        uid = user["id"]
        print(f"\nBem-vindo(a), {user['name']}!")
        show_profile(db, uid)
        actions = {
            "1": ("Meu perfil", lambda: show_profile(db, uid)),
            "2": ("Adicionar receita ou despesa", lambda: add_transaction(db, uid)),
            "3": ("Listar transações", lambda: list_transactions(db, uid)),
            "4": ("Excluir transação", lambda: delete_transaction(db, uid)),
        }
        while True:
            print("\n=== MENU BEACON | ETAPA 02 ===")
            for number, (label, _) in actions.items():
                print(f"{number:>2} - {label}")
            print(" 0 - Sair")
            chosen = read("Escolha")
            if chosen == "0":
                print("Até logo!")
                return
            command = actions.get(chosen)
            if command is None:
                print("Opção inválida.")
            else:
                command[1]()
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nExecução encerrada.")
    except sqlite3.Error as exc:
        print(f"Erro no banco de dados: {exc}", file=sys.stderr)
        sys.exit(1)
