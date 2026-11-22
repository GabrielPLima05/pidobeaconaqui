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
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            target_cents INTEGER NOT NULL CHECK(target_cents > 0),
            saved_cents INTEGER NOT NULL DEFAULT 0 CHECK(saved_cents >= 0),
            deadline TEXT NOT NULL
        );
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
        suggestions(db, uid)
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
        suggestions(db, uid)
    else:
        print("Transação não localizada.")


def month_rows(db: sqlite3.Connection, uid: int, month: str) -> list[sqlite3.Row]:
    return db.execute("SELECT * FROM transactions WHERE user_id=? AND substr(occurred_on,1,7)=? ORDER BY occurred_on,id", (uid, month)).fetchall()


def totals(rows: list[sqlite3.Row]) -> tuple[int, int, int]:
    income = sum(row["amount_cents"] for row in rows if row["kind"] == "receita")
    expense = sum(row["amount_cents"] for row in rows if row["kind"] == "despesa")
    optional = sum(row["amount_cents"] for row in rows if row["kind"] == "despesa" and row["discretionary"])
    return income, expense, optional


def valid_month(raw: str) -> str:
    try:
        parsed = date.fromisoformat(raw + "-01")
        if len(raw) != 7 or raw[4] != "-":
            raise ValueError()
        return parsed.strftime("%Y-%m")
    except ValueError as exc:
        raise ValueError("Informe o mês como AAAA-MM.") from exc


def dashboard(db: sqlite3.Connection, uid: int, month: str | None = None) -> None:
    month = month or date.today().strftime("%Y-%m")
    rows = month_rows(db, uid, month)
    income, expense, optional = totals(rows)
    print(f"\n=== PAINEL FINANCEIRO | {month} ===")
    print(f"Receitas:        {money(income)}")
    print(f"Despesas:        {money(expense)}")
    print(f"Saldo:           {money(income - expense)}")
    print(f"Gastos obrigatórios: {money(expense - optional)}")
    print(f"Gastos opcionais:{money(optional):>15}")
    if income:
        print(f"Comprometimento: {expense / income * 100:.1f}% da renda lançada")
    if not rows:
        print("Sem transações neste mês.")
    print("Dados lançados manualmente; não existe sincronização bancária.")


def monthly_dashboard(db: sqlite3.Connection, uid: int) -> None:
    try:
        month = valid_month(read("Mês AAAA-MM", date.today().strftime("%Y-%m")))
        dashboard(db, uid, month)
    except ValueError as exc:
        print(f"Erro: {exc}")


def offset_month(value: date, offset: int) -> str:
    year, index = divmod(value.year * 12 + value.month - 1 + offset, 12)
    return f"{year:04d}-{index + 1:02d}"


def bar(amount: int, maximum: int, width: int = 30) -> str:
    filled = 0 if maximum <= 0 else max(0, round(amount / maximum * width))
    if amount > 0:
        filled = max(1, filled)
    return "#" * filled + "." * (width - filled)


def expense_charts(db: sqlite3.Connection, uid: int) -> None:
    try:
        month = valid_month(read("Mês do gráfico AAAA-MM", date.today().strftime("%Y-%m")))
    except ValueError as exc:
        print(f"Erro: {exc}")
        return
    rows = month_rows(db, uid, month)
    by_category: dict[str, int] = {}
    for item in rows:
        if item["kind"] == "despesa":
            by_category[item["category"]] = by_category.get(item["category"], 0) + item["amount_cents"]
    print(f"\n=== GRÁFICO DE GASTOS POR CATEGORIA | {month} ===")
    expense = sum(by_category.values())
    if not by_category:
        print("Sem despesas neste mês. Use 'Carregar dados fictícios' para experimentar.")
    else:
        biggest = max(by_category.values())
        for category, amount in sorted(by_category.items(), key=lambda data: (-data[1], data[0])):
            percent = amount / expense * 100
            print(f"{category[:15]:15} | {bar(amount, biggest)} | {money(amount):>13} | {percent:5.1f}%")
    print("\n=== EVOLUÇÃO DAS DESPESAS | ÚLTIMOS 6 MESES ===")
    anchor = date.fromisoformat(month + "-01")
    values = []
    for offset in range(-5, 1):
        current = offset_month(anchor, offset)
        monthly = month_rows(db, uid, current)
        values.append((current, totals(monthly)[1]))
    highest = max((value for _, value in values), default=0)
    for current, amount in values:
        print(f"{current} | {bar(amount, highest, 24)} | {money(amount):>13}")
    print("Escala relativa em cada gráfico. Barras não são previsões.")


def load_demo(db: sqlite3.Connection, uid: int) -> None:
    print("Serão cadastrados lançamentos FICTÍCIOS para o mês atual e dois anteriores.")
    if read("Confirmar inclusão dos exemplos? (s/n)", "n").lower() != "s":
        return
    examples = [
        ("receita", 190000, "Bolsa", "Bolsa de estágio", 0),
        ("receita", 35000, "Freelance", "Trabalho extra", 0),
        ("despesa", 85000, "Moradia", "Aluguel", 0),
        ("despesa", 28000, "Alimentação", "Mercado", 0),
        ("despesa", 12000, "Transporte", "Ônibus", 0),
        ("despesa", 18000, "Delivery", "Pedidos", 1),
        ("despesa", 12000, "Streaming", "Assinaturas", 1),
        ("despesa", 15000, "Lazer", "Passeios", 1),
        ("despesa", 8500, "Compras", "Itens diversos", 1),
        ("despesa", 7000, "Café", "Cafeteria", 1)
    ]
    counter = 0
    for offset, factor in ((-2, Decimal("0.75")), (-1, Decimal("1.20")), (0, Decimal("1.00"))):
        month = offset_month(date.today(), offset)
        present = db.execute("SELECT COUNT(*) FROM transactions WHERE user_id=? AND substr(occurred_on,1,7)=? AND description LIKE 'DEMO | %'", (uid, month)).fetchone()[0]
        if present:
            continue
        with db:
            for position, (kind, amount, category, description, optional) in enumerate(examples, start=1):
                adjusted = int((Decimal(amount) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if optional else amount
                db.execute("INSERT INTO transactions(user_id,kind,amount_cents,category,description,discretionary,occurred_on) VALUES(?,?,?,?,?,?,?)",
                           (uid, kind, adjusted, category, "DEMO | " + description, optional, f"{month}-{min(position + 2, 27):02d}"))
                counter += 1
    print(f"Foram incluídos {counter} lançamentos fictícios. Repetir não duplica os exemplos dos mesmos meses.")
    expense_charts_current(db, uid)


def expense_charts_current(db: sqlite3.Connection, uid: int) -> None:
    current = date.today().strftime("%Y-%m")
    rows = month_rows(db, uid, current)
    by_category: dict[str, int] = {}
    for item in rows:
        if item["kind"] == "despesa":
            by_category[item["category"]] = by_category.get(item["category"], 0) + item["amount_cents"]
    if by_category:
        peak = max(by_category.values())
        print("\nExemplo | gráfico de despesas do mês atual:")
        for category, amount in sorted(by_category.items(), key=lambda x: (-x[1], x[0])):
            print(f"{category[:15]:15} | {bar(amount, peak, 20)} | {money(amount)}")


def months_until(deadline: str) -> int:
    today = date.today()
    end = date.fromisoformat(deadline)
    if end < today:
        return 0
    return (end.year - today.year) * 12 + end.month - today.month + 1


def show_goals(db: sqlite3.Connection, uid: int) -> list[sqlite3.Row]:
    goals = db.execute("SELECT * FROM goals WHERE user_id=? ORDER BY deadline,id", (uid,)).fetchall()
    print("\n=== METAS FINANCEIRAS ===")
    if not goals:
        print("Nenhuma meta cadastrada.")
    for goal in goals:
        missing = max(0, goal["target_cents"] - goal["saved_cents"])
        months = months_until(goal["deadline"])
        contribution = (missing + months - 1) // months if months else 0
        status = f"Aporte indicativo: {money(contribution)}/mês" if months else "Prazo vencido"
        print(f"#{goal['id']} | {goal['name']} | Meta: {money(goal['target_cents'])} | Reservado: {money(goal['saved_cents'])} | Falta: {money(missing)} | Prazo: {goal['deadline']} | {status}")
    return goals


def add_goal(db: sqlite3.Connection, uid: int) -> None:
    try:
        name = read("Nome da meta")
        if not name:
            raise ValueError("O nome da meta é obrigatório.")
        target = parse_money(read("Valor total da meta"))
        saved = parse_money(read("Quanto já foi reservado", "0"), allow_zero=True)
        deadline_raw = read("Prazo (AAAA-MM-DD)")
        if not deadline_raw:
            raise ValueError("Informe o prazo.")
        deadline = parse_date(deadline_raw)
        if deadline < date.today().isoformat() or saved > target:
            raise ValueError("Confira o prazo e o valor reservado.")
        with db:
            db.execute("INSERT INTO goals(user_id,name,target_cents,saved_cents,deadline) VALUES(?,?,?,?,?)",
                       (uid, name, target, saved, deadline))
        print("Meta registrada.")
        suggestions(db, uid)
    except ValueError as exc:
        print(f"Erro: {exc}")


def update_goal(db: sqlite3.Connection, uid: int) -> None:
    show_goals(db, uid)
    try:
        gid = int(read("Número da meta"))
        goal = db.execute("SELECT * FROM goals WHERE id=? AND user_id=?", (gid, uid)).fetchone()
        if goal is None:
            print("Meta não encontrada.")
            return
        saved = parse_money(read("Novo valor total reservado", "0"), allow_zero=True)
        if saved > goal["target_cents"]:
            raise ValueError("O valor reservado não pode superar a meta.")
        with db:
            db.execute("UPDATE goals SET saved_cents=? WHERE id=? AND user_id=?", (saved, gid, uid))
        print("Meta atualizada.")
        suggestions(db, uid)
    except ValueError as exc:
        print(f"Erro: {exc}")


def suggestions(db: sqlite3.Connection, uid: int) -> None:
    month = date.today().strftime("%Y-%m")
    data = month_rows(db, uid, month)
    income, expense, optional = totals(data)
    goals = db.execute("SELECT * FROM goals WHERE user_id=? ORDER BY deadline,id", (uid,)).fetchall()
    print(f"\n=== PLANEJAMENTO E CORTES | {month} ===")
    if not goals:
        print("Cadastre uma meta para calcular os aportes necessários.")
        return
    contribution_total = 0
    for goal in goals:
        remaining = max(0, goal["target_cents"] - goal["saved_cents"])
        months = months_until(goal["deadline"])
        if not months:
            print(f"Meta '{goal['name']}' com prazo vencido: atualize seu planejamento.")
            continue
        part = (remaining + months - 1) // months
        contribution_total += part
        print(f"{goal['name']}: {money(part)}/mês por {months} mês(es) até {goal['deadline']}.")
    if not data:
        print("Sem lançamentos no mês atual. Cadastre receitas e despesas para projetar cortes.")
        return
    balance = income - expense
    needed = max(0, contribution_total - balance)
    print(f"Saldo do mês: {money(balance)} | Aporte mensal para metas: {money(contribution_total)}")
    if needed == 0:
        print("No cenário informado, o saldo cobre o aporte calculado. Não há corte adicional necessário.")
        return
    print(f"Valor adicional necessário por mês: {money(needed)}")
    if optional == 0:
        print("Nenhum gasto opcional registrado. Não é possível sugerir cortes nessa base.")
        return
    available = min(needed, optional)
    categories: dict[str, int] = {}
    for item in data:
        if item["kind"] == "despesa" and item["discretionary"]:
            categories[item["category"]] = categories.get(item["category"], 0) + item["amount_cents"]
    print("Cortes propostos em gastos opcionais, priorizando maiores categorias:")
    pending = available
    for category, amount in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0])):
        cut = min(amount, pending)
        if cut:
            print(f"  {category}: reduzir {money(cut)} de {money(amount)}")
            pending -= cut
        if pending <= 0:
            break
    print(f"Total de cortes sugeridos: {money(available)}")
    if needed > optional:
        print(f"Mesmo eliminando todos os gastos opcionais, faltariam {money(needed - optional)}.")
    print("Simulação matemática baseada no mês atual, sem IA generativa, juros, sazonalidade ou previsão de renda.")


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        init_db(db)
        print("BEACON MVP | Terminal | Etapa 8 de 10")
        user = authenticate(db)
        if user is None:
            return
        uid = user["id"]
        print(f"\nBem-vindo(a), {user['name']}!")
        dashboard(db, uid)
        actions = {
            "1": ("Meu perfil", lambda: show_profile(db, uid)),
            "2": ("Adicionar receita ou despesa", lambda: add_transaction(db, uid)),
            "3": ("Listar transações", lambda: list_transactions(db, uid)),
            "4": ("Excluir transação", lambda: delete_transaction(db, uid)),
            "5": ("Painel financeiro mensal", lambda: monthly_dashboard(db, uid)),
            "6": ("Gráficos de despesas", lambda: expense_charts(db, uid)),
            "7": ("Carregar dados fictícios", lambda: load_demo(db, uid)),
            "8": ("Cadastrar meta", lambda: add_goal(db, uid)),
            "9": ("Consultar metas", lambda: show_goals(db, uid)),
            "10": ("Atualizar valor reservado", lambda: update_goal(db, uid)),
            "11": ("Planejamento e cortes", lambda: suggestions(db, uid)),
        }
        while True:
            print("\n=== MENU BEACON | ETAPA 08 ===")
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
