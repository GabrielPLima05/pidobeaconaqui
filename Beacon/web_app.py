from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
import webbrowser
from datetime import date, datetime
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import beacon

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MAX_BODY = 16384
SESSIONS = {}
SESSION_LOCK = threading.Lock()
SESSION_TTL = 60 * 60 * 8
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
MATERIALS = [
    ("01_orcamento.md", "Orçamento pessoal", "Organização do orçamento e hábitos de consumo"),
    ("02_metas.md", "Metas e reserva de emergência", "Como planejar objetivos de forma realista"),
    ("03_investimentos.md", "Selic, CDI e Tesouro Direto", "Conceitos introdutórios de investimentos"),
    ("04_estudo_de_caso.md", "Estudo de caso", "Exemplo completo de planejamento financeiro"),
    ("05_atividade_pratica.md", "Atividade prática", "Exercício de organização do orçamento"),
    ("06_renda_variavel.md", "Renda variável", "Como lidar com meses de receita instável"),
    ("07_credito_juros.md", "Crédito e juros", "Impacto do parcelamento e do custo do crédito"),
    ("08_vida_academica.md", "Vida acadêmica", "Finanças de universitários e estagiários"),
    ("FONTES.md", "Fontes educativas", "Referências dos materiais"),
    ("GABARITO.md", "Gabarito", "Respostas das atividades"),
]


def open_db():
    beacon.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(beacon.DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    beacon.init_db(connection)
    return connection


@contextmanager
def db_session():
    connection = open_db()
    try:
        yield connection
    finally:
        connection.close()


def validate_month(value):
    return beacon.valid_month(value or date.today().strftime("%Y-%m"))


def required_text(value, label, limit):
    if not isinstance(value, str):
        raise ValueError(f"{label}: informe um texto válido.")
    result = value.strip()
    if not result or len(result) > limit:
        raise ValueError(f"{label}: informe de 1 a {limit} caracteres.")
    return result


def cents_to_number(value):
    return round(value / 100, 2)


def serialize_transaction(row):
    return {"id": row["id"], "kind": row["kind"], "amount": cents_to_number(row["amount_cents"]),
            "category": row["category"], "description": row["description"], "optional": bool(row["discretionary"]),
            "date": row["occurred_on"]}


def serialize_goal(goal):
    months = beacon.months_until(goal["deadline"])
    pending = max(0, goal["target_cents"] - goal["saved_cents"])
    return {"id": goal["id"], "name": goal["name"], "target": cents_to_number(goal["target_cents"]),
            "saved": cents_to_number(goal["saved_cents"]), "pending": cents_to_number(pending),
            "deadline": goal["deadline"], "months": months,
            "monthly": cents_to_number((pending + months - 1) // months) if months else 0}


def dashboard_data(db, uid, month):
    rows = beacon.month_rows(db, uid, month)
    income, expense, optional = beacon.totals(rows)
    categories = {}
    days = {}
    for row in rows:
        if row["kind"] == "despesa":
            categories[row["category"]] = categories.get(row["category"], 0) + row["amount_cents"]
            days[row["occurred_on"]] = days.get(row["occurred_on"], 0) + row["amount_cents"]
    anchor = date.fromisoformat(month + "-01")
    trend = []
    for offset in range(-5, 1):
        selected_month = beacon.offset_month(anchor, offset)
        old = beacon.month_rows(db, uid, selected_month)
        current_income, current_expense, _ = beacon.totals(old)
        trend.append({"month": selected_month, "income": cents_to_number(current_income), "expense": cents_to_number(current_expense)})
    total_daily = 0
    daily = []
    for day, value in sorted(days.items()):
        total_daily += value
        daily.append({"date": day, "total": cents_to_number(total_daily)})
    return {"month": month, "income": cents_to_number(income), "expense": cents_to_number(expense),
            "balance": cents_to_number(income-expense), "optional": cents_to_number(optional),
            "essential": cents_to_number(expense-optional), "categories": [
                {"name": category, "amount": cents_to_number(amount)} for category, amount in
                sorted(categories.items(), key=lambda pair: (-pair[1], pair[0]))],
            "trend": trend, "daily": daily, "transactionCount": len(rows),
            "expensePercent": round((expense/income)*100, 1) if income else None}


def plan_data(db, uid):
    month = date.today().strftime("%Y-%m")
    rows = beacon.month_rows(db, uid, month)
    registered_income, expense, optional = beacon.totals(rows)
    income, conservative = beacon.reference_income(db, uid, registered_income)
    raw_goals = db.execute("SELECT * FROM goals WHERE user_id=? ORDER BY deadline,id", (uid,)).fetchall()
    goal_data = [serialize_goal(g) for g in raw_goals]
    monthly = sum(round(g["monthly"]*100) for g in goal_data)
    balance = income-expense
    needed = max(0, monthly-balance)
    profile = beacon.get_student_profile(db, uid)
    protected = beacon.protected_names(profile)
    categories = {}
    for row in rows:
        if row["kind"] == "despesa" and row["discretionary"] and beacon.normalized_name(row["category"]) not in protected:
            categories[row["category"]] = categories.get(row["category"], 0) + row["amount_cents"]
    available = min(needed, sum(categories.values()))
    cuts = []
    rest = available
    for category, amount in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0])):
        cut = min(rest, amount)
        if cut > 0:
            cuts.append({"category": category, "amount": cents_to_number(amount), "cut": cents_to_number(cut)})
            rest -= cut
        if rest <= 0:
            break
    return {"month": month, "income": cents_to_number(income), "reportedIncome": cents_to_number(registered_income),
            "conservative": conservative, "balance": cents_to_number(balance), "goalMonthly": cents_to_number(monthly),
            "needed": cents_to_number(needed), "possibleCuts": cents_to_number(available),
            "unmet": cents_to_number(max(0, needed-available)), "cuts": cuts,
            "protected": sorted(protected), "goals": goal_data, "hasTransactions": bool(rows),
            "optional": cents_to_number(optional)}


def profile_data(db, uid):
    row = beacon.get_student_profile(db, uid)
    return {"role": row["role"] if row else "outro",
            "incomePattern": row["income_pattern"] if row else "fixa",
            "conservativeIncome": cents_to_number(row["conservative_income_cents"]) if row else 0,
            "protectedCategories": row["protected_categories"] if row else beacon.DEFAULT_PROTECTED,
            "configured": bool(row)}


def save_profile(db, uid, body):
    role = body.get("role")
    pattern = body.get("incomePattern")
    if role not in ("universitario", "estagiario", "ambos", "outro"):
        raise ValueError("Selecione um perfil válido.")
    if pattern not in ("fixa", "variavel", "mista"):
        raise ValueError("Selecione o tipo de renda.")
    income = beacon.parse_money(str(body.get("conservativeIncome", "0")), allow_zero=True)
    protected = body.get("protectedCategories", "")
    if not isinstance(protected, str) or len(protected) > 500:
        raise ValueError("Categorias protegidas inválidas.")
    categories = ",".join(dict.fromkeys(x.strip() for x in protected.split(",") if x.strip()))
    if not categories:
        raise ValueError("Informe categorias essenciais protegidas.")
    with db:
        db.execute("INSERT INTO student_profiles(user_id,role,income_pattern,conservative_income_cents,protected_categories) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET role=excluded.role,income_pattern=excluded.income_pattern,conservative_income_cents=excluded.conservative_income_cents,protected_categories=excluded.protected_categories",
                   (uid, role, pattern, income, categories))
    return profile_data(db, uid)


def demo_data(db, uid):
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
        ("despesa", 7000, "Café", "Cafeteria", 1),
    ]
    total = 0
    for offset, factor in ((-2, Decimal("0.75")), (-1, Decimal("1.20")), (0, Decimal("1.00"))):
        month = beacon.offset_month(date.today(), offset)
        present = db.execute("SELECT COUNT(*) FROM transactions WHERE user_id=? AND substr(occurred_on,1,7)=? AND description LIKE 'DEMO | %'", (uid, month)).fetchone()[0]
        if present:
            continue
        with db:
            for pos, (kind, amount, category, description, optional) in enumerate(examples, 1):
                adjusted = int((Decimal(amount)*factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if optional else amount
                db.execute("INSERT INTO transactions(user_id,kind,amount_cents,category,description,discretionary,occurred_on) VALUES(?,?,?,?,?,?,?)",
                           (uid, kind, adjusted, category, "DEMO | " + description, optional, f"{month}-{min(pos+2,27):02d}"))
                total += 1
    return {"created": total}


def csv_document(db, uid):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Data", "Tipo", "Valor_R$", "Categoria", "Descrição", "Gasto_opcional"])
    for row in db.execute("SELECT occurred_on,kind,amount_cents,category,description,discretionary FROM transactions WHERE user_id=? ORDER BY occurred_on,id", (uid,)):
        writer.writerow([row["occurred_on"], row["kind"], f"{Decimal(row['amount_cents'])/100:.2f}".replace(".", ","),
                         beacon.csv_safe(row["category"]), beacon.csv_safe(row["description"]), "Sim" if row["discretionary"] else "Não"])
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Handler(BaseHTTPRequestHandler):
    server_version = "BeaconLocal/1.0"

    def log_message(self, fmt, *args):
        logging.info("%s - %s", self.address_string(), fmt % args)

    def _headers(self, status, content_type, length, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def output(self, status, content, mime="application/json; charset=utf-8", extra=None):
        data = json.dumps(content, ensure_ascii=False).encode("utf-8") if mime.startswith("application/json") else content
        self._headers(status, mime, len(data), extra)
        self.wfile.write(data)

    def body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError("Tamanho da requisição inválido.", 400)
        if not 0 < length <= MAX_BODY:
            raise ApiError("Dados enviados excedem o tamanho permitido.", 413)
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ApiError("Envie os dados em JSON.", 415)
        try:
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError()
            return body
        except (ValueError, UnicodeDecodeError):
            raise ApiError("JSON inválido.")

    def session(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except Exception:
            return None
        item = cookies.get("beacon_session")
        if not item:
            return None
        with SESSION_LOCK:
            stored = SESSIONS.get(item.value)
            if not stored or stored["expires"] < time.time():
                SESSIONS.pop(item.value, None)
                return None
            stored["expires"] = time.time() + SESSION_TTL
            return stored

    def login_required(self):
        session = self.session()
        if not session:
            raise ApiError("Sua sessão expirou. Entre novamente.", 401)
        return session

    def authorized_write(self):
        session = self.login_required()
        if not secrets.compare_digest(self.headers.get("X-Beacon-CSRF", ""), session["csrf"]):
            raise ApiError("Sessão inválida. Atualize a página.", 403)
        return session

    def validate_origin(self):
        origin = self.headers.get("Origin", "")
        allowed = f"http://127.0.0.1:{self.server.server_port}"
        if origin and origin != allowed:
            raise ApiError("Origem não autorizada.", 403)
        if self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
            raise ApiError("Requisição externa não permitida.", 403)

    def with_errors(self, fn):
        try:
            fn()
        except ApiError as exc:
            self.output(exc.status, {"error": str(exc)})
        except (ValueError, InvalidOperation, OverflowError) as exc:
            self.output(400, {"error": str(exc)})
        except sqlite3.Error:
            logging.exception("Database failure")
            self.output(500, {"error": "Erro no banco de dados local."})
        except OSError:
            logging.exception("File failure")
            self.output(500, {"error": "Erro ao acessar os arquivos do Beacon."})
        except Exception:
            logging.exception("Unexpected failure")
            self.output(500, {"error": "Não foi possível concluir a operação."})

    def do_GET(self):
        self.with_errors(self.handle_get)

    def do_POST(self):
        self.with_errors(self.handle_post)

    def do_PATCH(self):
        self.with_errors(self.handle_patch)

    def do_DELETE(self):
        self.with_errors(self.handle_delete)

    def handle_get(self):
        url = urlparse(self.path)
        path = url.path
        if path in ASSETS:
            name, mime = ASSETS[path]
            file = STATIC / name
            return self.output(200, file.read_bytes(), mime)
        if not path.startswith("/api/"):
            raise ApiError("Página não encontrada.", 404)
        session = self.login_required()
        uid = session["uid"]
        query = parse_qs(url.query)
        with db_session() as db:
            if path == "/api/session":
                user = db.execute("SELECT id,name,email FROM users WHERE id=?", (uid,)).fetchone()
                if user is None:
                    raise ApiError("Usuário não encontrado.", 401)
                return self.output(200, {"user": dict(user), "csrf": session["csrf"]})
            if path == "/api/dashboard":
                month = validate_month(query.get("month", [None])[0])
                return self.output(200, dashboard_data(db, uid, month))
            if path == "/api/transactions":
                month = query.get("month", [""])[0]
                if month:
                    month = validate_month(month)
                    rows = db.execute("SELECT * FROM transactions WHERE user_id=? AND substr(occurred_on,1,7)=? ORDER BY occurred_on DESC,id DESC LIMIT 1000", (uid, month)).fetchall()
                else:
                    rows = db.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY occurred_on DESC,id DESC LIMIT 1000", (uid,)).fetchall()
                return self.output(200, {"transactions": [serialize_transaction(row) for row in rows]})
            if path == "/api/goals":
                rows = db.execute("SELECT * FROM goals WHERE user_id=? ORDER BY deadline,id", (uid,)).fetchall()
                return self.output(200, {"goals": [serialize_goal(row) for row in rows]})
            if path == "/api/plan":
                return self.output(200, plan_data(db, uid))
            if path == "/api/profile":
                return self.output(200, profile_data(db, uid))
            if path == "/api/education":
                recommended = beacon.education_recommendations(db, uid)
                return self.output(200, {"materials": [{"file": filename, "title": title, "description": description} for filename, title, description in MATERIALS],
                                         "recommended": [{"file": name, "title": title, "reason": reason} for name, title, reason in recommended]})
            if path.startswith("/api/material/"):
                name = path[len("/api/material/"):]
                allowed = {value[0] for value in MATERIALS}
                if name not in allowed:
                    raise ApiError("Material não encontrado.", 404)
                return self.output(200, {"file": name, "content": (ROOT / "materiais" / name).read_text(encoding="utf-8")})
            if path == "/api/faq":
                return self.output(200, {"items": [{"question": q, "answer": a} for q, a in beacon.FAQ_ITEMS]})
            if path == "/api/export/csv":
                return self.output(200, csv_document(db, uid), "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="beacon_transacoes.csv"'})
            if path == "/api/export/pdf":
                month = validate_month(query.get("month", [None])[0])
                return self.output(200, beacon.financial_pdf(db, uid, month), "application/pdf", {"Content-Disposition": f'attachment; filename="beacon_relatorio_{month}.pdf"'})
        raise ApiError("Rota não encontrada.", 404)

    def handle_post(self):
        self.validate_origin()
        path = urlparse(self.path).path
        body = self.body()
        if path == "/api/auth/register":
            email = required_text(body.get("email"), "E-mail", 254).lower()
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                raise ApiError("Informe um e-mail válido.")
            name = required_text(body.get("name"), "Nome", 120)
            password = body.get("password")
            if not isinstance(password, str) or not 8 <= len(password) <= 128:
                raise ApiError("Use uma senha entre 8 e 128 caracteres.")
            if body.get("confirm") != password:
                raise ApiError("As senhas não coincidem.")
            salt = secrets.token_bytes(16)
            with db_session() as db:
                try:
                    with db:
                        db.execute("INSERT INTO users(name,email,salt,password_hash) VALUES(?,?,?,?)", (name, email, salt.hex(), beacon.hash_password(password, salt)))
                except sqlite3.IntegrityError:
                    raise ApiError("E-mail já cadastrado.", 409)
            return self.output(201, {"message": "Conta criada. Entre com seus dados."})
        if path == "/api/auth/login":
            email = str(body.get("email", "")).strip().lower()
            password = body.get("password", "")
            with db_session() as db:
                user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                if user is None or not isinstance(password, str) or not secrets.compare_digest(user["password_hash"], beacon.hash_password(password, bytes.fromhex(user["salt"]))):
                    raise ApiError("E-mail ou senha incorretos.", 401)
                token = secrets.token_urlsafe(36)
                csrf = secrets.token_urlsafe(32)
                with SESSION_LOCK:
                    SESSIONS[token] = {"uid": user["id"], "csrf": csrf, "expires": time.time() + SESSION_TTL}
                return self.output(200, {"user": {"id": user["id"], "name": user["name"], "email": user["email"]}, "csrf": csrf},
                                   extra={"Set-Cookie": f"beacon_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}"})
        session = self.authorized_write()
        uid = session["uid"]
        with db_session() as db:
            if path == "/api/auth/logout":
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                item = cookie.get("beacon_session")
                if item:
                    with SESSION_LOCK:
                        SESSIONS.pop(item.value, None)
                return self.output(200, {"message": "Sessão encerrada."}, extra={"Set-Cookie": "beacon_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
            if path == "/api/transactions":
                kind = body.get("kind")
                if kind not in ("receita", "despesa"):
                    raise ValueError("Selecione receita ou despesa.")
                amount = beacon.parse_money(str(body.get("amount", "")))
                category = required_text(body.get("category"), "Categoria", 60)
                description = body.get("description") or "Sem descrição"
                description = required_text(description, "Descrição", 160)
                when = beacon.parse_date(str(body.get("date", "")))
                optional = int(bool(body.get("optional"))) if kind == "despesa" else 0
                with db:
                    db.execute("INSERT INTO transactions(user_id,kind,amount_cents,category,description,discretionary,occurred_on) VALUES(?,?,?,?,?,?,?)", (uid, kind, amount, category, description, optional, when))
                return self.output(201, {"message": "Transação cadastrada."})
            if path == "/api/goals":
                name = required_text(body.get("name"), "Meta", 120)
                target = beacon.parse_money(str(body.get("target", "")))
                saved = beacon.parse_money(str(body.get("saved", "0")), allow_zero=True)
                deadline = beacon.parse_date(str(body.get("deadline", "")))
                if saved > target:
                    raise ValueError("O valor reservado não pode ultrapassar a meta.")
                if deadline < date.today().isoformat():
                    raise ValueError("Escolha uma data futura ou de hoje.")
                with db:
                    db.execute("INSERT INTO goals(user_id,name,target_cents,saved_cents,deadline) VALUES(?,?,?,?,?)", (uid, name, target, saved, deadline))
                return self.output(201, {"message": "Meta criada."})
            if path == "/api/profile":
                return self.output(200, {"profile": save_profile(db, uid, body)})
            if path == "/api/purchase":
                month = validate_month(str(body.get("month", "")))
                amount = beacon.parse_money(str(body.get("amount", "")))
                installments = int(body.get("installments", 1))
                raw = str(body.get("monthlyRate", "0")).replace(",", ".")
                rate = Decimal(raw)
                schedule = beacon.create_payment_schedule(amount, installments, rate)
                result = beacon.purchase_analysis(db, uid, amount, schedule, month)
                total = sum(schedule)
                warning = "ok"
                if any(item["before"] < 0 for item in result):
                    warning = "existing-shortfall"
                elif any(item["new_shortfall"] for item in result):
                    warning = "new-shortfall"
                elif min(item["after"] for item in result) < max(1, result[0]["income"] // 10):
                    warning = "low-margin"
                return self.output(200, {"amount": cents_to_number(amount), "installments": installments,
                                         "payment": cents_to_number(schedule[0]), "total": cents_to_number(total),
                                         "interest": cents_to_number(max(0, total-amount)), "warning": warning,
                                         "projection": [{k: cents_to_number(v) if isinstance(v, int) and k != "new_shortfall" else v for k, v in row.items()} for row in result]})
            if path == "/api/demo":
                return self.output(200, demo_data(db, uid))
        raise ApiError("Rota não encontrada.", 404)

    def handle_patch(self):
        self.validate_origin()
        session = self.authorized_write()
        body = self.body()
        path = urlparse(self.path).path
        result = re.fullmatch(r"/api/goals/(\d+)", path)
        if not result:
            raise ApiError("Rota não encontrada.", 404)
        goal_id = int(result.group(1))
        with db_session() as db:
            goal = db.execute("SELECT * FROM goals WHERE id=? AND user_id=?", (goal_id, session["uid"])).fetchone()
            if goal is None:
                raise ApiError("Meta não encontrada.", 404)
            saved = beacon.parse_money(str(body.get("saved", "")), allow_zero=True)
            if saved > goal["target_cents"]:
                raise ValueError("O valor reservado não pode superar a meta.")
            with db:
                db.execute("UPDATE goals SET saved_cents=? WHERE id=? AND user_id=?", (saved, goal_id, session["uid"]))
            self.output(200, {"message": "Valor reservado atualizado."})

    def handle_delete(self):
        self.validate_origin()
        session = self.authorized_write()
        path = urlparse(self.path).path
        result = re.fullmatch(r"/api/(transactions|goals)/(\d+)", path)
        if not result:
            raise ApiError("Rota não encontrada.", 404)
        table, item_id = result.group(1), int(result.group(2))
        with db_session() as db:
            with db:
                cursor = db.execute(f"DELETE FROM {table} WHERE id=? AND user_id=?", (item_id, session["uid"]))
            if not cursor.rowcount:
                raise ApiError("Registro não encontrado.", 404)
            self.output(200, {"message": "Registro excluído."})


def run(host="127.0.0.1", port=8765, launch=True):
    with db_session():
        pass
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print("=" * 60)
    print("BEACON | INTERFACE VISUAL LOCAL")
    print(f"Abra no navegador: {url}")
    print("Para encerrar, pressione Ctrl+C nesta janela.")
    print("=" * 60)
    if launch:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        run(port=int(os.environ.get("BEACON_PORT", "8765")))
    except OSError as exc:
        print(f"Não foi possível iniciar a interface: {exc}")
        raise SystemExit(1)
