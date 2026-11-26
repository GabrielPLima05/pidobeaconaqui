from __future__ import annotations

import csv
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import sys
import unicodedata
from datetime import date, datetime
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


def wait_for_menu() -> None:
    prompt = "\nPressione qualquer tecla para voltar ao menu..."
    if os.name == "nt" and sys.stdin.isatty():
        import msvcrt
        print(prompt, end="", flush=True)
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            msvcrt.getwch()
        elif key == "\x03":
            raise KeyboardInterrupt
        print()
    elif sys.stdin.isatty():
        import termios
        import tty
        print(prompt, end="", flush=True)
        fd = sys.stdin.fileno()
        old_mode = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            key = sys.stdin.read(1)
            if key == "\x03":
                raise KeyboardInterrupt
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_mode)
            print()
    else:
        try:
            input("\nPressione Enter para voltar ao menu...")
        except EOFError:
            pass


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
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
            print("Informe um e-mail válido.")
            continue
        password = read_password()
        if action == "2":
            if not 8 <= len(password) <= 128:
                print("A senha precisa ter entre 8 e 128 caracteres.")
                continue
            confirmation = read_password("Confirme a senha: ")
            if password != confirmation:
                print("As senhas não coincidem.")
                continue
            name = read("Nome")
            if not name or len(name) > 120:
                print("Informe um nome de até 120 caracteres.")
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
    db.execute("""CREATE TABLE IF NOT EXISTS student_profiles (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            income_pattern TEXT NOT NULL,
            conservative_income_cents INTEGER NOT NULL DEFAULT 0,
            protected_categories TEXT NOT NULL
        )""")
    db.commit()


def add_transaction(db: sqlite3.Connection, uid: int) -> None:
    action = read("Tipo (1=receita, 2=despesa)")
    if action not in ("1", "2"):
        print("Tipo inválido.")
        return
    try:
        amount = parse_money(read("Valor (ex.: 125,50)"))
        category = read("Categoria (ex.: Bolsa, Moradia, Lazer)")
        if not category or len(category) > 60:
            raise ValueError("Informe uma categoria de até 60 caracteres.")
        description = read("Descrição", "Sem descrição")
        if len(description) > 160:
            raise ValueError("A descrição deve ter até 160 caracteres.")
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
        if not name or len(name) > 120:
            raise ValueError("O nome da meta deve ter entre 1 e 120 caracteres.")
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
    effective_income, conservative = reference_income(db, uid, income)
    balance = effective_income - expense
    if conservative:
        print(f"Renda conservadora utilizada: {money(effective_income)} (receita registrada: {money(income)}).")
    needed = max(0, contribution_total - balance)
    print(f"Saldo do mês: {money(balance)} | Aporte mensal para metas: {money(contribution_total)}")
    if needed == 0:
        print("No cenário informado, o saldo cobre o aporte calculado. Não há corte adicional necessário.")
        return
    print(f"Valor adicional necessário por mês: {money(needed)}")
    if optional == 0:
        print("Nenhum gasto opcional registrado. Não é possível sugerir cortes nessa base.")
        return
    profile = get_student_profile(db, uid)
    protected = protected_names(profile)
    categories: dict[str, int] = {}
    for item in data:
        if item["kind"] == "despesa" and item["discretionary"] and normalized_name(item["category"]) not in protected:
            categories[item["category"]] = categories.get(item["category"], 0) + item["amount_cents"]
    available = min(needed, sum(categories.values()))
    if protected:
        print("Categorias protegidas: " + profile["protected_categories"])
    if available == 0:
        print("Sem gastos opcionais elegíveis a cortes. Não é possível atender a diferença por esta estratégia.")
        return
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
    if needed > available:
        print(f"Mesmo com todos os cortes elegíveis, ainda faltariam {money(needed - available)}.")
    print("Simulação matemática baseada no mês atual, sem IA generativa, juros, sazonalidade ou previsão de renda.")


def learn() -> None:
    root = Path(__file__).resolve().parent / "materiais"
    chapters = [
        ("1", "Organização do orçamento", "01_orcamento.md"),
        ("2", "Metas e reserva de emergência", "02_metas.md"),
        ("3", "Selic, CDI e Tesouro Direto", "03_investimentos.md"),
        ("4", "Estudo de caso do Beacon", "04_estudo_de_caso.md"),
        ("5", "Planejamento com renda variável", "06_renda_variavel.md"),
        ("6", "Crédito e custo das parcelas", "07_credito_juros.md"),
        ("7", "Finanças do estudante e estagiário", "08_vida_academica.md")
    ]
    while True:
        print("\n=== TRILHA DE EDUCAÇÃO FINANCEIRA ===")
        for code, title, _ in chapters:
            print(f"{code} - {title}")
        print("8 - Quiz de aprendizagem\n0 - Voltar")
        choice = read("Escolha")
        if choice == "0":
            return
        if choice == "8":
            quiz()
            wait_for_menu()
            continue
        found = next((file for code, _, file in chapters if code == choice), None)
        if found is None:
            print("Opção inválida.")
            wait_for_menu()
            continue
        try:
            print("\n" + (root / found).read_text(encoding="utf-8"))
        except OSError:
            print("Arquivo didático não encontrado. Confira a pasta materiais.")
        wait_for_menu()


def quiz() -> None:
    items = [
        ("Um gasto discricionário é:", "b", "a) aluguel obrigatório | b) lazer opcional | c) tarifa de luz"),
        ("Qual é a definição mais adequada de saldo financeiro?", "a", "a) receitas menos despesas | b) despesas menos receitas | c) apenas salário"),
        ("Uma meta de R$ 1.200 para 6 meses, sem valor reservado, exige aproximadamente:", "c", "a) R$ 100/mês | b) R$ 120/mês | c) R$ 200/mês"),
        ("Qual afirmação sobre a Selic é adequada?", "a", "a) taxa básica de juros | b) rentabilidade garantida de qualquer ativo | c) inflação acumulada"),
        ("O Beacon neste MVP prevê rendimentos reais de investimentos?", "b", "a) sim, com garantia | b) não, usa cálculos simples | c) sim, via API bancária")
    ]
    score = 0
    for number, (question, answer, alternatives) in enumerate(items, start=1):
        print(f"\n{number}. {question}\n{alternatives}")
        if read("Resposta (a/b/c)").lower() == answer:
            score += 1
            print("Correto!")
        else:
            print(f"Resposta esperada: {answer}.")
        wait_for_menu()
    print(f"\nResultado: {score}/{len(items)}. A trilha é educativa, não aconselhamento de investimento.")


DEFAULT_PROTECTED = "Moradia,Alimentação,Transporte,Saúde,Estudos"


def normalized_name(value: str) -> str:
    return "".join(character for character in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(character)).strip()


def get_student_profile(db: sqlite3.Connection, uid: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM student_profiles WHERE user_id=?", (uid,)).fetchone()


def protected_names(profile: sqlite3.Row | None) -> set[str]:
    if profile is None:
        return set()
    return {normalized_name(piece) for piece in profile["protected_categories"].split(",") if piece.strip()}


def reference_income(db: sqlite3.Connection, uid: int, reported_income: int) -> tuple[int, bool]:
    profile = get_student_profile(db, uid)
    if profile is None or profile["income_pattern"] == "fixa" or not profile["conservative_income_cents"] or not reported_income:
        return reported_income, False
    adjusted = min(reported_income, profile["conservative_income_cents"])
    return adjusted, adjusted < reported_income


def student_mode(db: sqlite3.Connection, uid: int) -> None:
    print("\n=== MODO UNIVERSITÁRIO / ESTAGIÁRIO ===")
    profile = get_student_profile(db, uid)
    if profile:
        print(f"Perfil: {profile['role']} | Renda: {profile['income_pattern']}")
        print(f"Referência conservadora: {money(profile['conservative_income_cents']) if profile['conservative_income_cents'] else 'não configurada'}")
        print(f"Categorias protegidas: {profile['protected_categories']}")
    else:
        print("Nenhum perfil específico configurado. O orçamento padrão continua disponível.")
    if read("Configurar ou alterar o perfil? (s/n)", "n").lower() != "s":
        return
    print("1 - Universitário | 2 - Estagiário | 3 - Universitário e estagiário | 4 - Outro")
    role = {"1": "universitario", "2": "estagiario", "3": "ambos", "4": "outro"}.get(read("Situação"))
    if role is None:
        print("Situação inválida. Nenhuma alteração foi feita.")
        return
    print("1 - Fixa | 2 - Variável | 3 - Mista")
    pattern = {"1": "fixa", "2": "variavel", "3": "mista"}.get(read("Tipo de renda"))
    if pattern is None:
        print("Tipo de renda inválido. Nenhuma alteração foi feita.")
        return
    try:
        income = 0
        if pattern != "fixa":
            income = parse_money(read("Renda conservadora mensal (0 = sem referência)", "0"), allow_zero=True)
        current = profile["protected_categories"] if profile else DEFAULT_PROTECTED
        categories = read("Categorias essenciais protegidas, separadas por vírgulas", current)
        categories = ",".join(dict.fromkeys(part.strip() for part in categories.split(",") if part.strip()))
        if not categories:
            raise ValueError("Informe ao menos uma categoria protegida.")
        with db:
            db.execute("INSERT INTO student_profiles(user_id,role,income_pattern,conservative_income_cents,protected_categories) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET role=excluded.role,income_pattern=excluded.income_pattern,conservative_income_cents=excluded.conservative_income_cents,protected_categories=excluded.protected_categories", (uid, role, pattern, income, categories))
        print("Perfil salvo. O sistema passa a proteger essas categorias nas sugestões de cortes.")
        print("A referência de renda não altera lançamentos nem garante renda futura.")
    except ValueError as exc:
        print(f"Erro: {exc}")


def education_recommendations(db: sqlite3.Connection, uid: int) -> list[tuple[str, str, str]]:
    rows = month_rows(db, uid, date.today().strftime("%Y-%m"))
    income, expense, optional = totals(rows)
    categories = {normalized_name(row["category"]) for row in rows if row["kind"] == "despesa"}
    profile = get_student_profile(db, uid)
    goals = db.execute("SELECT * FROM goals WHERE user_id=?", (uid,)).fetchall()
    recommended: list[tuple[str, str, str]] = []
    if not rows:
        recommended.append(("01_orcamento.md", "Orçamento pessoal", "Você ainda não lançou movimentações neste mês."))
    elif income == 0 or expense >= income or expense * 100 >= income * 85:
        recommended.append(("01_orcamento.md", "Revisão do orçamento", "Suas despesas estão próximas ou acima da receita registrada."))
    if expense and optional * 100 >= expense * 25:
        recommended.append(("05_atividade_pratica.md", "Consumo consciente", "Os gastos opcionais representam pelo menos 25% das despesas do mês."))
    if any(any(key in category for key in ("cartao", "credito", "juros", "parcela", "emprestimo")) for category in categories):
        recommended.append(("07_credito_juros.md", "Crédito e juros", "Você possui uma categoria associada a crédito ou parcelamentos."))
    if not goals:
        recommended.append(("02_metas.md", "Metas financeiras", "Você ainda não cadastrou objetivos financeiros."))
    elif any(goal["saved_cents"] < goal["target_cents"] for goal in goals):
        recommended.append(("04_estudo_de_caso.md", "Plano para uma meta", "Há pelo menos uma meta ainda em andamento."))
    if profile and profile["income_pattern"] in ("variavel", "mista"):
        recommended.append(("06_renda_variavel.md", "Planejamento com renda variável", "Seu perfil registra renda variável ou mista."))
    if profile and profile["role"] in ("universitario", "estagiario", "ambos"):
        recommended.append(("08_vida_academica.md", "Orçamento acadêmico", "Seu perfil é universitário e/ou estagiário."))
    if not recommended:
        recommended.append(("03_investimentos.md", "Conceitos financeiros básicos", "Seus lançamentos não acionaram regras de atenção prioritária."))
    return recommended[:5]


def adaptive_education(db: sqlite3.Connection, uid: int) -> None:
    print("\n=== RECOMENDAÇÕES EDUCATIVAS PERSONALIZADAS ===")
    print("Regras fixas com base nas transações e metas cadastradas. Sem IA generativa.")
    options = education_recommendations(db, uid)
    for index, (filename, title, reason) in enumerate(options, 1):
        print(f"{index} - {title}\n    Motivo: {reason}")
    value = read("Número para ler (Enter retorna)")
    if not value:
        return
    if not value.isdigit() or not 1 <= int(value) <= len(options):
        print("Opção inválida.")
        return
    filename, _, _ = options[int(value) - 1]
    try:
        print("\n" + (Path(__file__).resolve().parent / "materiais" / filename).read_text(encoding="utf-8"))
    except OSError:
        print("Arquivo didático não encontrado.")


FAQ_ITEMS = [
    ("Como cadastro uma despesa?", "No menu, use 'Adicionar receita ou despesa', escolha despesa, informe valor, categoria e data."),
    ("O que são gastos opcionais?", "São despesas que você marcou como não obrigatórias. O Beacon só sugere cortes nelas, exceto categorias protegidas."),
    ("O Beacon acessa meu banco?", "Não. O MVP não possui acesso bancário. Os lançamentos são manuais e salvos localmente em SQLite."),
    ("Como funciona o simulador de compras?", "Ele usa o orçamento de um mês de referência, soma a compra e compara o saldo disponível para metas e despesas."),
    ("O simulador registra uma compra real?", "Não. A simulação não altera suas transações, metas ou saldo."),
    ("Posso simular uma compra parcelada?", "Sim. É possível avaliar parcelas sem juros ou com uma taxa mensal hipotética informada por você."),
    ("Como as metas são calculadas?", "O valor ainda necessário é distribuído pelo número de meses restantes, sem considerar juros ou rentabilidade."),
    ("O sistema tem inteligência artificial?", "Não neste MVP. Ele usa fórmulas e regras predefinidas, sem conectar APIs externas."),
    ("Como encontro materiais de estudo?", "Abra a Trilha de educação financeira ou as Recomendações educativas para acessar textos e exercícios locais."),
    ("Posso exportar os dados?", "Sim. A opção Exportar transações CSV gera um arquivo compatível com planilhas na pasta exportacoes."),
    ("O que é renda conservadora?", "É um valor mensal escolhido por você para cenários prudentes quando sua renda varia. Não é previsão de recebimento."),
    ("Como protejo transporte e alimentação?", "Configure o Modo universitário/estagiário e informe essas categorias como protegidas. O motor de cortes não as sugerirá."),
    ("Onde ficam minhas informações?", "No arquivo local beacon.db, que não possui criptografia integral. Evite inserir dados reais sensíveis em demonstrações."),
]


def frequently_asked() -> None:
    while True:
        print("\n=== PERGUNTAS FREQUENTES ===")
        for index, (question, _) in enumerate(FAQ_ITEMS, 1):
            print(f"{index:2} - {question}")
        print(" 0 - Voltar")
        question = read("Escolha o número ou digite um termo")
        if not question or question == "0":
            return
        if question.isdigit() and 1 <= int(question) <= len(FAQ_ITEMS):
            selected = [FAQ_ITEMS[int(question) - 1]]
        else:
            query = normalized_name(question)
            selected = [(q, a) for q, a in FAQ_ITEMS if query in normalized_name(q) or query in normalized_name(a)]
        if not selected:
            print("Nenhuma pergunta cadastrada com esse termo. Tente outra palavra.")
        for title, answer in selected:
            print(f"\n{title}\n{answer}")
        wait_for_menu()


def create_payment_schedule(amount_cents: int, months: int, monthly_percent: Decimal = Decimal("0")) -> list[int]:
    if amount_cents <= 0 or not 1 <= months <= 60 or not monthly_percent.is_finite() or monthly_percent < 0 or monthly_percent > 30:
        raise ValueError("Confira valor, quantidade de parcelas (1 a 60) e juros mensais (0 a 30%).")
    if monthly_percent == 0:
        base, remaining = divmod(amount_cents, months)
        return [base + (1 if i < remaining else 0) for i in range(months)]
    if months == 1:
        return [int((Decimal(amount_cents) * (Decimal("1") + monthly_percent / 100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))]
    factor = Decimal("1") + monthly_percent / Decimal("100")
    rate = monthly_percent / Decimal("100")
    payment = Decimal(amount_cents) * rate * factor ** months / (factor ** months - 1)
    cents = int(payment.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return [cents] * months


def goal_contribution_at_month(goals: list[sqlite3.Row], target_month: str) -> int:
    total = 0
    for goal in goals:
        if goal["deadline"][:7] < target_month:
            continue
        months = months_until(goal["deadline"])
        if months <= 0:
            continue
        pending = max(0, goal["target_cents"] - goal["saved_cents"])
        total += (pending + months - 1) // months
    return total


def purchase_analysis(db: sqlite3.Connection, uid: int, amount_cents: int, payments: list[int], month: str) -> list[dict[str, int | str | bool]]:
    reported_income, expense, _ = totals(month_rows(db, uid, month))
    income, _ = reference_income(db, uid, reported_income)
    goals = db.execute("SELECT * FROM goals WHERE user_id=?", (uid,)).fetchall()
    anchor = date.today().replace(day=1)
    projection = []
    for index in range(max(6, len(payments))):
        target_month = offset_month(anchor, index)
        planned_goal = goal_contribution_at_month(goals, target_month)
        payment = payments[index] if index < len(payments) else 0
        before = income - expense - planned_goal
        after = before - payment
        projection.append({"month": target_month, "income": income, "expense": expense, "goal": planned_goal, "payment": payment, "before": before, "after": after, "new_shortfall": before >= 0 and after < 0})
    return projection


def purchase_simulator(db: sqlite3.Connection, uid: int) -> None:
    print("\n=== SIMULADOR DE COMPRAS ===")
    print("Simulação ilustrativa; nenhuma transação será cadastrada.")
    try:
        current_month = date.today().strftime("%Y-%m")
        month = valid_month(read("Mês-base com receitas e despesas (AAAA-MM)", current_month))
        base = month_rows(db, uid, month)
        if not base:
            print("Sem lançamentos no mês-base. Insira dados ou utilize os exemplos antes de simular.")
            return
        amount = parse_money(read("Preço da compra à vista (R$)"))
        print("1 - À vista | 2 - Parcelado sem juros | 3 - Parcelado com juros hipotéticos")
        kind = read("Condição")
        if kind not in ("1", "2", "3"):
            print("Condição inválida.")
            return
        months = 1
        rate = Decimal("0")
        if kind != "1":
            months = int(read("Número de parcelas (1 a 60)"))
            if kind == "3":
                raw = read("Taxa de juros efetiva ao mês (%), ex.: 2,5").replace(",", ".")
                rate = Decimal(raw)
        payments = create_payment_schedule(amount, months, rate)
        projection = purchase_analysis(db, uid, amount, payments, month)
        print(f"\nCompra: {money(amount)} | Parcela-base: {money(payments[0])} | Total aproximado: {money(sum(payments))}")
        print(f"Custo adicional aproximado: {money(max(0, sum(payments) - amount))}")
        print("Mês      | Parcela        | Metas/mês       | Folga sem compra | Folga com compra")
        for item in projection:
            print(f"{item['month']} | {money(item['payment']):>14} | {money(item['goal']):>15} | {money(item['before']):>16} | {money(item['after']):>15}")
        if any(item["before"] < 0 for item in projection):
            print("ATENÇÃO: seu orçamento-base já apresenta insuficiência em pelo menos um mês, sem essa compra.")
        elif any(item["new_shortfall"] for item in projection):
            print("ALERTA: a compra cria insuficiência para despesas e aportes às metas em pelo menos um mês.")
        elif min(int(item["after"]) for item in projection) < max(1, int(projection[0]["income"]) // 10):
            print("ATENÇÃO: a compra mantém o orçamento não negativo, mas deixa margem financeira reduzida.")
        else:
            print("Neste cenário, as despesas e aportes às metas cabem no orçamento informado.")
        print("Premissas: receitas e despesas do mês-base se repetem; metas seguem valores informados.")
        print("Não considera novas dívidas, impostos, encargos de cartão, sazonalidade ou variação de preços.")
        print("Juros são estimados por parcela fixa; confira sempre CET e condições do contrato real.")
    except (ValueError, InvalidOperation, OverflowError) as exc:
        print(f"Entrada inválida: {exc}")

def csv_safe(value: str) -> str:
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(db: sqlite3.Connection, uid: int) -> None:
    try:
        folder = Path(__file__).resolve().parent / "exportacoes"
        folder.mkdir(exist_ok=True)
        destination = folder / f"transacoes_usuario_{uid}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.csv"
        rows = db.execute("SELECT occurred_on,kind,amount_cents,category,description,discretionary FROM transactions WHERE user_id=? ORDER BY occurred_on,id", (uid,)).fetchall()
        with destination.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["Data", "Tipo", "Valor_R$", "Categoria", "Descrição", "Gasto_opcional"])
            for item in rows:
                writer.writerow([item["occurred_on"], item["kind"], f"{Decimal(item['amount_cents'])/100:.2f}".replace(".", ","), csv_safe(item["category"]), csv_safe(item["description"]), "Sim" if item["discretionary"] else "Não"])
        print(f"Arquivo exportado: {destination}")
    except OSError as exc:
        print(f"Não foi possível exportar o CSV: {exc}")


def pdf_text(value: str) -> bytes:
    value = value.replace("\r", " ").replace("\n", " ")
    raw = value.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def make_pdf(pages: list[list[str]]) -> bytes:
    objects: list[bytes] = []

    def register(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    font_id = register(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    page_collection_id = register(b"")
    catalog_id = register(f"<< /Type /Catalog /Pages {page_collection_id} 0 R >>".encode("ascii"))
    page_ids: list[int] = []
    for lines in pages:
        commands = [b"BT", b"/F1 9 Tf", b"13 TL", b"42 798 Td"]
        for line in lines:
            commands.append(b"(" + pdf_text(line) + b") Tj")
            commands.append(b"T*")
        commands.append(b"ET")
        stream = b"\n".join(commands) + b"\n"
        stream_id = register(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream")
        page_id = register(f"<< /Type /Page /Parent {page_collection_id} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {stream_id} 0 R >>".encode("ascii"))
        page_ids.append(page_id)
    pages_expr = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[page_collection_id - 1] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{pages_expr}] >>".encode("ascii")
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    positions = [0]
    for number, payload in enumerate(objects, start=1):
        positions.append(len(result))
        result.extend(f"{number} 0 obj\n".encode("ascii") + payload + b"\nendobj\n")
    start_xref = len(result)
    result.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode("ascii"))
    for position in positions[1:]:
        result.extend(f"{position:010d} 00000 n \n".encode("ascii"))
    result.extend(f"trailer\n<< /Size {len(objects)+1} /Root {catalog_id} 0 R >>\nstartxref\n{start_xref}\n%%EOF\n".encode("ascii"))
    return bytes(result)


def financial_pdf(db: sqlite3.Connection, uid: int, month: str) -> bytes:
    rows = month_rows(db, uid, month)
    income, expense, optional = totals(rows)
    user = db.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()
    name = user["name"] if user else "Usuário"
    header = [
        "BEACON | RELATORIO FINANCEIRO",
        "=" * 69,
        f"Usuário: {name[:48]}  |  Mês: {month}",
        f"Receitas: {money(income)}   Despesas: {money(expense)}",
        f"Saldo: {money(income-expense)}   Despesas opcionais: {money(optional)}",
        "-" * 69,
        "Data        Tipo     Valor             Categoria / Descrição",
        "-" * 69,
    ]
    entries = []
    for item in rows:
        title = f"{item['category'][:16]} / {item['description'][:29]}"
        entries.append(f"{item['occurred_on']}  {item['kind'][:7]:7}  {money(item['amount_cents']):>15}  {title}"[:73])
    if not entries:
        entries.append("Nenhuma transação registrada neste mês.")
    pages: list[list[str]] = []
    for pos in range(0, len(entries), 47):
        page = header + entries[pos:pos + 47]
        page += ["", "Relatório local. Dados informados pelo usuário; sem integração bancária."]
        pages.append(page)
    return make_pdf(pages)


def export_pdf(db: sqlite3.Connection, uid: int) -> None:
    try:
        month = valid_month(read("Mês do relatório PDF (AAAA-MM)", date.today().strftime("%Y-%m")))
        folder = Path(__file__).resolve().parent / "exportacoes"
        folder.mkdir(exist_ok=True)
        destination = folder / f"relatorio_usuario_{uid}_{month}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.pdf"
        destination.write_bytes(financial_pdf(db, uid, month))
        print(f"Relatório PDF exportado: {destination}")
    except ValueError as exc:
        print(f"Erro: {exc}")
    except OSError as exc:
        print(f"Não foi possível exportar o PDF: {exc}")


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        init_db(db)
        print("BEACON MVP | Terminal | Perfil Jovem + Simulações")
        user = authenticate(db)
        if user is None:
            return
        uid = user["id"]
        print(f"\nBem-vindo(a), {user['name']}!")
        dashboard(db, uid)
        wait_for_menu()
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
            "12": ("Trilha de educação financeira", lambda: learn()),
            "13": ("Perguntas frequentes", frequently_asked),
            "14": ("Exportar transações CSV", lambda: export_csv(db, uid)),
            "15": ("Modo universitário e estagiário", lambda: student_mode(db, uid)),
            "16": ("Educação financeira personalizada", lambda: adaptive_education(db, uid)),
            "17": ("Simular compra", lambda: purchase_simulator(db, uid)),
            "18": ("Exportar relatório PDF", lambda: export_pdf(db, uid)),
        }
        while True:
            print("\n=== MENU BEACON ===")
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
            wait_for_menu()
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
    except OSError as exc:
        print(f"Erro ao acessar arquivos locais: {exc}", file=sys.stderr)
        sys.exit(1)
