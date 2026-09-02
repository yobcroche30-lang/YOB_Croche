#!/usr/bin/env python3
"""YOB_Crochê - Loja Online com Backend"""
import os
import random
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Compatível com duas estruturas:
# 1) templates/ e static/ (ideal)
# 2) arquivos .html e style.css na raiz (como no GitHub atual)
_base = os.path.dirname(os.path.abspath(__file__))
_tpl = os.path.join(_base, "templates")
_static = os.path.join(_base, "static")
if not os.path.isdir(_tpl):
    # HTML na raiz do repositório
    _tpl = _base
if not os.path.isdir(_static):
    _static = _base

app = Flask(__name__, template_folder=_tpl, static_folder=_static, static_url_path="/static")
app.secret_key = os.environ.get("SECRET_KEY", "yob-croche-secret-2026-change-me")
# uploads
_upload = os.path.join(_base, "static", "uploads")
if not os.path.isdir(os.path.join(_base, "static")):
    _upload = os.path.join(_base, "uploads")
app.config["UPLOAD_FOLDER"] = _upload
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

# Senhas admin: ADMIN_PASSWORD ou várias em ADMIN_PASSWORDS (separadas por vírgula)
_admin_single = os.environ.get("ADMIN_PASSWORD", "yob2026")
_admin_multi = os.environ.get("ADMIN_PASSWORDS", "")
ADMIN_PASSWORDS = set(
    p.strip()
    for p in (_admin_multi.split(",") if _admin_multi else [_admin_single])
    if p.strip()
)
MAX_ADMIN_ATTEMPTS = 5
ADMIN_RECOVERY_CODE = os.environ.get("ADMIN_RECOVERY_CODE", "yob-recovery-2026")
WHATSAPP = os.environ.get("WHATSAPP", "5511999999999")

# No Render a pasta pode ser só leitura — usa /tmp se precisar
_base_dir = os.path.dirname(os.path.abspath(__file__))
_default_db = os.path.join(_base_dir, "yob.db")
_tmp_db = "/tmp/yob_croche.db"


def _resolve_db_path():
    try:
        test = os.path.join(_base_dir, ".write_test")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return _default_db
    except Exception:
        return _tmp_db


DB_PATH = os.environ.get("DATABASE_PATH") or _resolve_db_path()

try:
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
except Exception:
    app.config["UPLOAD_FOLDER"] = "/tmp/yob_uploads"
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'Acessórios',
            color TEXT,
            price REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            description TEXT,
            image TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT NOT NULL UNIQUE,
            contact_type TEXT DEFAULT 'phone',
            password_hash TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_codes (
            contact TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            name TEXT,
            contact_type TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            customer_name TEXT,
            customer_contact TEXT,
            mode TEXT,
            message TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            customer_name TEXT,
            customer_phone TEXT,
            address TEXT,
            delivery_method TEXT,
            delivery_fee REAL DEFAULT 0,
            payment_method TEXT,
            total REAL,
            items_json TEXT,
            status TEXT DEFAULT 'novo',
            created_at TEXT
        )
    """)
    # seed products if empty
    count = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count == 0:
        now = datetime.now().isoformat()
        products = [
            ("Bolsa Porta-Celular", "Acessórios", "Cinza", 35.0, 8,
             "Bolsa porta-celular em crochê, tamanho único. Prática e leve.", None),
            ("Bolsa Porta-Celular", "Acessórios", "Marrom", 35.0, 6,
             "Bolsa porta-celular em crochê com detalhes em rosa. Tamanho único.", None),
            ("Sousplat Floral", "Mesa", "Rosa", 45.0, 10,
             "Sousplat em crochê 100% algodão, diâmetro 35cm.", None),
            ("Bolsa de Ombro", "Bolsas", "Preto", 120.0, 3,
             "Bolsa resistente com forro interno e alça confortável.", None),
            ("Amigurumi Ursinho", "Amigurumi", "Bege", 55.0, 7,
             "Ursinho amigurumi 20cm, perfeito para presente.", None),
            ("Cachecol Inverno", "Acessórios", "Cinza", 65.0, 4,
             "Cachecol macio 1,80m, fio acrílico premium.", None),
        ]
        for p in products:
            c.execute(
                "INSERT INTO products (name,category,color,price,stock,description,image,active,created_at) VALUES (?,?,?,?,?,?,?,1,?)",
                (*p, now),
            )
    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapped


def customer_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("customer_id"):
            return redirect(url_for("auth"))
        return f(*args, **kwargs)
    return wrapped



def get_setting(key, default=None):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def check_admin_password(pwd):
    """Valida senha admin (banco ou variáveis de ambiente)."""
    stored = get_setting("admin_password_hash")
    if stored:
        return check_password_hash(stored, pwd)
    return pwd in ADMIN_PASSWORDS


def find_customer(contact):
    conn = get_db()
    cust = conn.execute(
        "SELECT * FROM customers WHERE contact=?", (contact,)
    ).fetchone()
    if not cust:
        digits = "".join(filter(str.isdigit, contact))
        if digits:
            for r in conn.execute("SELECT * FROM customers").fetchall():
                if "".join(filter(str.isdigit, r["contact"])) == digits:
                    cust = r
                    break
    conn.close()
    return cust


@app.before_request
def setup():
    if not os.path.exists(DB_PATH):
        init_db()


# ---------- LOJA ----------
@app.route("/")
def index():
    if not session.get("customer_id"):
        return redirect(url_for("auth"))
    conn = get_db()
    products = conn.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY id DESC"
    ).fetchall()
    categories = conn.execute(
        "SELECT DISTINCT category FROM products WHERE active=1"
    ).fetchall()
    conn.close()
    cart = session.get("cart", {})
    return render_template(
        "index.html",
        products=products,
        categories=categories,
        cart_count=sum(cart.values()),
        customer=session.get("customer_name"),
        whatsapp=WHATSAPP,
    )


@app.route("/auth", methods=["GET", "POST"])
def auth():
    if session.get("customer_id"):
        return redirect(url_for("index"))
    return render_template("auth.html", hide_nav=True, cart_count=0, customer=None)


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    contact = (data.get("contact") or "").strip()
    contact_type = data.get("type") or "phone"
    if not name or not contact:
        return jsonify({"ok": False, "error": "Preencha nome e contato"}), 400

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM customers WHERE contact=?", (contact,)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"ok": False, "error": "Este contato já está cadastrado. Faça login."}), 400

    code = str(random.randint(1000, 9999))
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO pending_codes (contact, code, name, contact_type, created_at) VALUES (?,?,?,?,?)",
        (contact, code, name, contact_type, now),
    )
    conn.commit()
    conn.close()
    # Em produção real: enviar SMS/e-mail. Aqui retornamos o código para demo + log.
    print(f"[YOB] Código para {contact}: {code}")
    return jsonify({"ok": True, "demo_code": code, "message": "Código gerado"})


@app.route("/api/confirm", methods=["POST"])
def api_confirm():
    data = request.get_json() or {}
    contact = (data.get("contact") or "").strip()
    code = (data.get("code") or "").strip()
    if not contact or not code:
        return jsonify({"ok": False, "error": "Dados incompletos"}), 400

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM pending_codes WHERE contact=?", (contact,)
    ).fetchone()
    if not row or row["code"] != code:
        conn.close()
        return jsonify({"ok": False, "error": "Código incorreto"}), 400

    now = datetime.now().isoformat()
    try:
        cur = conn.execute(
            "INSERT INTO customers (name, contact, contact_type, created_at) VALUES (?,?,?,?)",
            (row["name"], row["contact"], row["contact_type"], now),
        )
        customer_id = cur.lastrowid
    except sqlite3.IntegrityError:
        # já existe
        cust = conn.execute(
            "SELECT id, name FROM customers WHERE contact=?", (contact,)
        ).fetchone()
        customer_id = cust["id"]
        name = cust["name"]
    else:
        name = row["name"]

    conn.execute("DELETE FROM pending_codes WHERE contact=?", (contact,))
    conn.commit()
    conn.close()

    session["customer_id"] = customer_id
    session["customer_name"] = name
    session["customer_contact"] = contact
    return jsonify({"ok": True, "name": name})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    contact = (data.get("contact") or "").strip()
    if not contact:
        return jsonify({"ok": False, "error": "Informe telefone ou e-mail"}), 400
    conn = get_db()
    # match exact or digits-only for phone
    cust = conn.execute(
        "SELECT * FROM customers WHERE contact=?", (contact,)
    ).fetchone()
    if not cust:
        digits = "".join(filter(str.isdigit, contact))
        rows = conn.execute("SELECT * FROM customers").fetchall()
        for r in rows:
            if "".join(filter(str.isdigit, r["contact"])) == digits and digits:
                cust = r
                break
    conn.close()
    if not cust:
        return jsonify({"ok": False, "error": "Cadastro não encontrado"}), 404
    session["customer_id"] = cust["id"]
    session["customer_name"] = cust["name"]
    session["customer_contact"] = cust["contact"]
    return jsonify({"ok": True, "name": cust["name"]})




@app.route("/api/recover", methods=["POST"])
def api_recover():
    """Cliente: envia código para recuperar acesso."""
    data = request.get_json() or {}
    contact = (data.get("contact") or "").strip()
    if not contact:
        return jsonify({"ok": False, "error": "Informe telefone ou e-mail"}), 400
    cust = find_customer(contact)
    if not cust:
        return jsonify({"ok": False, "error": "Cadastro não encontrado"}), 404
    code = str(random.randint(1000, 9999))
    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO pending_codes (contact, code, name, contact_type, created_at) VALUES (?,?,?,?,?)",
        (cust["contact"], code, cust["name"], cust["contact_type"], now),
    )
    conn.commit()
    conn.close()
    print(f"[YOB] Código recuperação {cust['contact']}: {code}")
    return jsonify({"ok": True, "demo_code": code, "contact": cust["contact"], "message": "Código enviado"})


@app.route("/api/recover/confirm", methods=["POST"])
def api_recover_confirm():
    """Cliente: confirma código e entra na conta; opcionalmente define nova senha."""
    data = request.get_json() or {}
    contact = (data.get("contact") or "").strip()
    code = (data.get("code") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    if not contact or not code:
        return jsonify({"ok": False, "error": "Dados incompletos"}), 400
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM pending_codes WHERE contact=?", (contact,)
    ).fetchone()
    if not row or row["code"] != code:
        conn.close()
        return jsonify({"ok": False, "error": "Código incorreto"}), 400
    cust = conn.execute(
        "SELECT * FROM customers WHERE contact=?", (contact,)
    ).fetchone()
    if not cust:
        conn.close()
        return jsonify({"ok": False, "error": "Cliente não encontrado"}), 404
    if new_password:
        if len(new_password) < 4:
            conn.close()
            return jsonify({"ok": False, "error": "Senha deve ter no mínimo 4 caracteres"}), 400
        conn.execute(
            "UPDATE customers SET password_hash=? WHERE id=?",
            (generate_password_hash(new_password), cust["id"]),
        )
    conn.execute("DELETE FROM pending_codes WHERE contact=?", (contact,))
    conn.commit()
    conn.close()
    session["customer_id"] = cust["id"]
    session["customer_name"] = cust["name"]
    session["customer_contact"] = cust["contact"]
    return jsonify({"ok": True, "name": cust["name"]})


@app.route("/api/admin/recover", methods=["POST"])
def api_admin_recover():
    """Admin: valida código de recuperação e define nova senha."""
    data = request.get_json() or {}
    recovery = (data.get("recovery_code") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    if recovery != ADMIN_RECOVERY_CODE:
        return jsonify({"ok": False, "error": "Código de recuperação inválido"}), 400
    if not new_password or len(new_password) < 4:
        return jsonify({"ok": False, "error": "Nova senha deve ter no mínimo 4 caracteres"}), 400
    set_setting("admin_password_hash", generate_password_hash(new_password))
    session["admin"] = True
    session["admin_attempts"] = 0
    return jsonify({"ok": True, "message": "Senha do admin atualizada"})


@app.route("/api/google-login", methods=["POST"])
def api_google_login():
    """Login Google simplificado (nome + email). Para OAuth real use Google Cloud."""
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    if not name or not email:
        return jsonify({"ok": False, "error": "Nome e e-mail obrigatórios"}), 400
    conn = get_db()
    cust = conn.execute(
        "SELECT * FROM customers WHERE contact=?", (email,)
    ).fetchone()
    now = datetime.now().isoformat()
    if cust:
        customer_id = cust["id"]
        name = cust["name"]
    else:
        cur = conn.execute(
            "INSERT INTO customers (name, contact, contact_type, created_at) VALUES (?,?,?,?)",
            (name, email, "google", now),
        )
        customer_id = cur.lastrowid
        conn.commit()
    conn.close()
    session["customer_id"] = customer_id
    session["customer_name"] = name
    session["customer_contact"] = email
    return jsonify({"ok": True, "name": name})


@app.route("/logout")
def logout():
    session.pop("customer_id", None)
    session.pop("customer_name", None)
    session.pop("customer_contact", None)
    return redirect(url_for("auth"))


@app.route("/product/<int:pid>")
@customer_required
def product_detail(pid):
    conn = get_db()
    p = conn.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
    conn.close()
    if not p:
        flash("Produto não encontrado")
        return redirect(url_for("index"))
    cart = session.get("cart", {})
    return render_template(
        "product.html", product=p, cart_count=sum(cart.values()),
        customer=session.get("customer_name"),
    )


@app.route("/cart/add/<int:pid>", methods=["POST"])
@customer_required
def cart_add(pid):
    qty = int(request.form.get("qty", 1) or 1)
    cart = session.get("cart", {})
    key = str(pid)
    cart[key] = cart.get(key, 0) + qty
    session["cart"] = cart
    flash("Adicionado ao carrinho!")
    return redirect(request.referrer or url_for("index"))


@app.route("/cart")
@customer_required
def cart_view():
    cart = session.get("cart", {})
    items = []
    total = 0
    conn = get_db()
    for pid, qty in cart.items():
        p = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if p:
            sub = p["price"] * qty
            total += sub
            items.append({"product": p, "qty": qty, "subtotal": sub})
    conn.close()
    return render_template(
        "cart.html", items=items, total=total,
        cart_count=sum(cart.values()), customer=session.get("customer_name"),
    )


@app.route("/cart/remove/<int:pid>")
@customer_required
def cart_remove(pid):
    cart = session.get("cart", {})
    cart.pop(str(pid), None)
    session["cart"] = cart
    return redirect(url_for("cart_view"))


@app.route("/checkout", methods=["GET", "POST"])
@customer_required
def checkout():
    cart = session.get("cart", {})
    if not cart:
        flash("Carrinho vazio")
        return redirect(url_for("index"))

    conn = get_db()
    items = []
    subtotal = 0
    for pid, qty in cart.items():
        p = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if p:
            sub = p["price"] * qty
            subtotal += sub
            items.append({"product": p, "qty": qty, "subtotal": sub})

    if request.method == "POST":
        name = request.form.get("name", session.get("customer_name", "")).strip()
        phone = request.form.get("phone", session.get("customer_contact", "")).strip()
        address = request.form.get("address", "").strip()
        delivery = request.form.get("delivery", "retirada")
        payment = request.form.get("payment", "pix")
        fee = 5.0 if delivery == "uber" else 0.0
        if delivery == "uber" and not address:
            flash("Informe o endereço para entrega Uber Flex")
            conn.close()
            return render_template(
                "checkout.html", items=items, subtotal=subtotal, fee=fee,
                total=subtotal + fee, cart_count=sum(cart.values()),
                customer=session.get("customer_name"),
                customer_contact=session.get("customer_contact"),
            )
        total = subtotal + fee
        import json
        items_json = json.dumps([
            {"id": i["product"]["id"], "name": i["product"]["name"],
             "color": i["product"]["color"], "qty": i["qty"], "price": i["product"]["price"]}
            for i in items
        ], ensure_ascii=False)
        now = datetime.now().isoformat()
        conn.execute(
            """INSERT INTO orders (customer_id, customer_name, customer_phone, address,
               delivery_method, delivery_fee, payment_method, total, items_json, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,'novo',?)""",
            (session.get("customer_id"), name, phone, address, delivery, fee, payment, total, items_json, now),
        )
        # baixa estoque
        for i in items:
            conn.execute(
                "UPDATE products SET stock = MAX(0, stock - ?) WHERE id=?",
                (i["qty"], i["product"]["id"]),
            )
        conn.commit()
        conn.close()
        session["cart"] = {}

        # monta mensagem WhatsApp
        lines = [f"• {i['product']['name']} ({i['product']['color'] or '-'}) x{i['qty']} = R$ {i['subtotal']:.2f}" for i in items]
        delivery_txt = "Uber Flex (+R$ 5,00)" if delivery == "uber" else "Retirada"
        msg = (
            f"Olá! Pedido YOB_Crochê 🧶\n\n"
            f"*Cliente:* {name}\n*WhatsApp:* {phone}\n*Endereço:* {address or 'A combinar'}\n\n"
            f"*Pedido:*\n" + "\n".join(lines) +
            f"\n\n*Entrega:* {delivery_txt}\n*Total: R$ {total:.2f}*\n"
            f"*Pagamento:* {'Pix' if payment == 'pix' else 'Combinar no WhatsApp'}\n\nAguardo confirmação! 💜"
        )
        wa_url = f"https://wa.me/{WHATSAPP}?text=" + __import__("urllib.parse").parse.quote(msg)
        return render_template("success.html", name=name, total=total, wa_url=wa_url, customer=name)

    conn.close()
    return render_template(
        "checkout.html", items=items, subtotal=subtotal, fee=0, total=subtotal,
        cart_count=sum(cart.values()), customer=session.get("customer_name"),
        customer_contact=session.get("customer_contact"),
    )



@app.route("/poster")
@customer_required
def poster():
    conn = get_db()
    products = conn.execute(
        "SELECT * FROM products WHERE active=1 ORDER BY id DESC"
    ).fetchall()
    conn.close()
    cart = session.get("cart", {})
    return render_template(
        "poster.html",
        products=products,
        cart_count=sum(cart.values()),
        customer=session.get("customer_name"),
        whatsapp=WHATSAPP,
    )


@app.route("/attend")
@customer_required
def attend():
    cart = session.get("cart", {})
    return render_template(
        "attend.html",
        cart_count=sum(cart.values()),
        customer=session.get("customer_name"),
        whatsapp=WHATSAPP,
    )


@app.route("/rights")
@customer_required
def rights():
    cart = session.get("cart", {})
    return render_template(
        "rights.html",
        cart_count=sum(cart.values()),
        customer=session.get("customer_name"),
        whatsapp=WHATSAPP,
    )


@app.route("/api/ticket", methods=["POST"])
@customer_required
def api_ticket():
    data = request.get_json() or {}
    mode = (data.get("mode") or "vendedor").strip()
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "Mensagem vazia"}), 400
    conn = get_db()
    conn.execute(
        """INSERT INTO tickets (customer_id, customer_name, customer_contact, mode, message, created_at)
           VALUES (?,?,?,?,?,?)""",
        (
            session.get("customer_id"),
            session.get("customer_name"),
            session.get("customer_contact"),
            mode,
            message,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})



# ---------- ADMIN ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Acesso restrito. URL não aparece no menu da loja para clientes."""
    attempts = session.get("admin_attempts", 0)
    if attempts >= MAX_ADMIN_ATTEMPTS:
        flash("Muitas tentativas. Aguarde ou limpe os cookies do navegador.")
        return render_template("admin_login.html", hide_nav=True, cart_count=0, customer=None), 429

    if request.method == "POST":
        pwd = (request.form.get("password") or "").strip()
        if check_admin_password(pwd):
            session["admin"] = True
            session["admin_attempts"] = 0
            return redirect(url_for("admin"))
        session["admin_attempts"] = attempts + 1
        left = MAX_ADMIN_ATTEMPTS - session["admin_attempts"]
        flash(f"Senha incorreta. Tentativas restantes: {left}")
    return render_template("admin_login.html", hide_nav=True, cart_count=0, customer=None)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin():
    conn = get_db()
    products = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    orders = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20").fetchall()
    customers = conn.execute("SELECT * FROM customers ORDER BY id DESC LIMIT 50").fetchall()
    tickets = conn.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 30").fetchall()
    conn.close()
    admin_photo = get_setting("admin_photo")
    return render_template(
        "admin.html", products=products, orders=orders, customers=customers, tickets=tickets,
        admin_photo=admin_photo, customer=session.get("customer_name"), cart_count=0
    )



@app.route("/admin/profile-photo", methods=["POST"])
@admin_required
def admin_profile_photo():
    f = request.files.get("photo")
    if not f or not f.filename:
        flash("Selecione uma foto")
        return redirect(url_for("admin"))
    if not allowed_file(f.filename):
        flash("Use PNG, JPG, JPEG, GIF ou WEBP")
        return redirect(url_for("admin"))
    fname = secure_filename(f"admin_profile_{datetime.now().strftime('%Y%m%d%H%M%S')}_{f.filename}")
    path = os.path.join(app.config["UPLOAD_FOLDER"], fname)
    f.save(path)
    rel = f"uploads/{fname}"
    set_setting("admin_photo", rel)
    flash("Foto do perfil atualizada!")
    return redirect(url_for("admin"))


@app.route("/admin/product/save", methods=["POST"])
@admin_required
def admin_product_save():
    pid = request.form.get("id")
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "Acessórios").strip()
    color = request.form.get("color", "").strip()
    price = float(request.form.get("price") or 0)
    stock = int(request.form.get("stock") or 0)
    description = request.form.get("description", "").strip()
    active = 1 if request.form.get("active") == "1" else 0

    image_path = None
    f = request.files.get("image")
    if f and f.filename and allowed_file(f.filename):
        fname = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{f.filename}")
        f.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))
        image_path = f"uploads/{fname}"

    conn = get_db()
    if pid:
        if image_path:
            conn.execute(
                """UPDATE products SET name=?, category=?, color=?, price=?, stock=?,
                   description=?, image=?, active=? WHERE id=?""",
                (name, category, color, price, stock, description, image_path, active, pid),
            )
        else:
            conn.execute(
                """UPDATE products SET name=?, category=?, color=?, price=?, stock=?,
                   description=?, active=? WHERE id=?""",
                (name, category, color, price, stock, description, active, pid),
            )
    else:
        conn.execute(
            """INSERT INTO products (name,category,color,price,stock,description,image,active,created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (name, category, color, price, stock, description, image_path, active, datetime.now().isoformat()),
        )
    conn.commit()
    conn.close()
    flash("Produto salvo!")
    return redirect(url_for("admin"))


@app.route("/admin/product/delete/<int:pid>")
@admin_required
def admin_product_delete(pid):
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    flash("Produto excluído")
    return redirect(url_for("admin"))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# init on import (for gunicorn)
try:
    init_db()
except Exception as e:
    print("AVISO init_db:", e)


@app.route("/health")
def health():
    return {"ok": True, "service": "YOB_Croche"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
