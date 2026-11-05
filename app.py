# SMART STORE PRO - Online Store + Private Admin Dashboard
# Install: pip install -r requirements.txt
# Local run: python app.py
# Production: gunicorn app:app

from flask import Flask, request, redirect, url_for, session, flash, render_template_string, abort
import sqlite3, os, secrets
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Render: set DATABASE_PATH=/var/data/smart_store_web.db and attach a persistent disk at /var/data
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'smart_store_web.db'))

app = Flask(__name__)
app.secret_key = os.environ.get('SMART_STORE_SECRET') or secrets.token_hex(32)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE', '0') == '1'

PAYMENT_METHODS = ['الدفع عند الاستلام', 'Vodafone Cash', 'InstaPay', 'Visa / Mastercard', 'تحويل بنكي']
STATUSES = ['جديد', 'تم القبول', 'جاري التجهيز', 'تم الشحن', 'تم التسليم', 'مرفوض']


def db():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    con.execute('PRAGMA busy_timeout = 20000')
    return con


def init_db():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT DEFAULT '',
            price REAL NOT NULL, buy_price REAL DEFAULT 0, quantity INTEGER NOT NULL DEFAULT 0,
            image_url TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT NOT NULL, phone TEXT NOT NULL,
            address TEXT NOT NULL, payment_method TEXT NOT NULL, payment_reference TEXT DEFAULT '',
            subtotal REAL NOT NULL, delivery_fee REAL NOT NULL, total REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'جديد', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS order_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            product_id INTEGER, product_name TEXT NOT NULL, quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL, line_total REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        if not con.execute('SELECT 1 FROM admins LIMIT 1').fetchone():
            # Change the default password immediately after first login.
            initial_password = os.environ.get('INITIAL_ADMIN_PASSWORD', '1234')
            con.execute('INSERT INTO admins(username,password_hash) VALUES(?,?)',
                        ('admin', generate_password_hash(initial_password)))
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('delivery_fee','200')")


def setting(key, default=''):
    with db() as con:
        row = con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper


BASE = '''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }} - SMART STORE PRO</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#172033;font-family:Tahoma,Arial,sans-serif}header{background:#101b35;color:white;padding:17px 5%;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}header a{color:white;text-decoration:none;margin:0 8px}.brand{font-size:22px;font-weight:bold}.wrap{max-width:1100px;margin:25px auto;padding:0 15px}.hero{background:linear-gradient(120deg,#14264d,#2876b9);color:white;border-radius:18px;padding:30px;margin-bottom:22px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.card,.box{background:white;border-radius:14px;padding:18px;box-shadow:0 3px 14px #17203312}.card img{width:100%;height:165px;object-fit:cover;border-radius:10px;background:#edf1f6}.price{font-size:20px;color:#087b50;font-weight:bold}input,textarea,select{width:100%;padding:12px;margin:7px 0 13px;border:1px solid #d5dce8;border-radius:8px;font:inherit}button,.btn{background:#1769aa;color:white;border:0;border-radius:8px;padding:11px 17px;cursor:pointer;text-decoration:none;display:inline-block;font:inherit}.danger{background:#b52d3a}.muted{color:#667085}.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}table{width:100%;border-collapse:collapse;background:white}th,td{padding:11px;border-bottom:1px solid #e8ebf1;text-align:right}th{background:#edf2f8}.scroll{overflow-x:auto}.msg{padding:12px;background:#e3f7eb;border-radius:8px;margin:10px 0}.small{font-size:13px}.actions{display:flex;gap:7px;flex-wrap:wrap}.footer{text-align:center;padding:25px;color:#778}
@media(max-width:600px){header{display:block}header nav{margin-top:12px}header a{display:inline-block;margin:5px}.wrap{margin:14px auto}.hero{padding:20px}}
</style></head><body>
<header><a class="brand" href="{{ url_for('home') }}">SMART STORE PRO</a><nav><a href="{{ url_for('home') }}">المتجر</a><a href="{{ url_for('track') }}">متابعة الطلب</a>{% if session.get('admin_id') %}<a href="{{ url_for('dashboard') }}">لوحة الإدارة</a><a href="{{ url_for('logout') }}">خروج</a>{% else %}<a href="{{ url_for('login') }}">دخول الإدارة</a>{% endif %}</nav></header>
<div class="wrap">{% with messages=get_flashed_messages() %}{% for m in messages %}<div class="msg">{{m}}</div>{% endfor %}{% endwith %}{{ body|safe }}</div><div class="footer">SMART STORE PRO</div></body></html>'''


def page(title, body, **context):
    return render_template_string(BASE, title=title, body=render_template_string(body, **context), **context)


HOME = '''<section class="hero"><h1>أهلاً بيك في SMART STORE PRO</h1><p>اختار منتجاتك واطلب بسهولة، وتابع حالة طلبك من صفحة متابعة الطلب.</p><b>مصاريف التوصيل الحالية: {{ fee }} جنيه</b></section>
{% if products %}<div class="grid">{% for p in products %}<article class="card">{% if p.image_url %}<img src="{{p.image_url}}" alt="{{p.name}}">{% else %}<div style="height:165px;background:#edf1f6;border-radius:10px;display:grid;place-items:center">صورة المنتج</div>{% endif %}<h3>{{p.name}}</h3><p class="muted">{{p.description}}</p><div class="price">{{'%.2f'|format(p.price)}} جنيه</div><p class="small">المتاح: {{p.quantity}}</p>{% if p.quantity>0 %}<a class="btn" href="{{url_for('checkout',product_id=p.id)}}">اطلب الآن</a>{% else %}<span class="muted">غير متوفر حالياً</span>{% endif %}</article>{% endfor %}</div>{% else %}<div class="box">لسه مفيش منتجات. الإدارة هتضيف المنتجات قريباً.</div>{% endif %}'''


@app.route('/')
def home():
    with db() as con:
        products = con.execute('SELECT * FROM products WHERE active=1 ORDER BY id DESC').fetchall()
    return page('المتجر', HOME, products=products, fee=setting('delivery_fee', '200'))


CHECKOUT = '''<div class="box"><h2>إتمام الطلب</h2><h3>{{p.name}} — {{'%.2f'|format(p.price)}} جنيه</h3><p>مصاريف التوصيل: <b>{{fee}} جنيه</b> — إجمالي القطعة: <b>{{'%.2f'|format(p.price+fee)}} جنيه</b></p>
<form method="post"><label>الاسم بالكامل</label><input name="customer_name" required maxlength="100"><label>رقم الموبايل</label><input name="phone" required maxlength="30"><label>العنوان بالتفصيل</label><textarea name="address" required rows="3"></textarea><label>الكمية</label><input type="number" name="quantity" min="1" max="{{p.quantity}}" value="1" required><label>طريقة الدفع</label><select name="payment_method">{% for m in methods %}<option>{{m}}</option>{% endfor %}</select><label>رقم التحويل (لو دفعت بمحفظة أو InstaPay)</label><input name="payment_reference"><button type="submit">تأكيد الطلب</button></form><p class="small muted">اختيار البطاقة أو المحفظة هنا لا يسحب أموالاً تلقائياً؛ يلزم ربط بوابة دفع للتحصيل الإلكتروني.</p></div>'''


@app.route('/checkout/<int:product_id>', methods=['GET', 'POST'])
def checkout(product_id):
    with db() as con:
        p = con.execute('SELECT * FROM products WHERE id=? AND active=1', (product_id,)).fetchone()
    if not p:
        abort(404)
    if request.method == 'POST':
        name = request.form.get('customer_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        method = request.form.get('payment_method', '')
        reference = request.form.get('payment_reference', '').strip()
        try:
            qty = int(request.form.get('quantity', '1'))
        except ValueError:
            qty = 0
        if not name or not phone or not address or method not in PAYMENT_METHODS or qty < 1:
            flash('راجع البيانات وحاول تاني.')
            return redirect(url_for('checkout', product_id=product_id))

        # Delivery fee is saved with this order; later fee changes do not alter old orders.
        fee = float(setting('delivery_fee', '200'))
        with db() as con:
            con.execute('BEGIN IMMEDIATE')
            current = con.execute('SELECT * FROM products WHERE id=? AND active=1', (product_id,)).fetchone()
            if not current or current['quantity'] < qty:
                flash('الكمية المطلوبة غير متاحة حالياً.')
                return redirect(url_for('home'))
            subtotal = round(current['price'] * qty, 2)
            total = round(subtotal + fee, 2)
            cur = con.execute('INSERT INTO orders(customer_name,phone,address,payment_method,payment_reference,subtotal,delivery_fee,total,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (name, phone, address, method, reference, subtotal, fee, total, 'جديد', datetime.now().strftime('%Y-%m-%d %H:%M')))
            oid = cur.lastrowid
            con.execute('INSERT INTO order_items(order_id,product_id,product_name,quantity,unit_price,line_total) VALUES(?,?,?,?,?,?)',
                (oid, product_id, current['name'], qty, current['price'], subtotal))
            con.execute('UPDATE products SET quantity=quantity-? WHERE id=?', (qty, product_id))
        return redirect(url_for('order_done', order_id=oid))

    fee = float(setting('delivery_fee', '200'))
    return page('إتمام الطلب', CHECKOUT, p=p, fee=fee, methods=PAYMENT_METHODS)


@app.route('/done/<int:order_id>')
def order_done(order_id):
    with db() as con:
        o = con.execute('SELECT id,phone,total,status FROM orders WHERE id=?', (order_id,)).fetchone()
    if not o:
        abort(404)
    body = '''<div class="box"><h2>طلبك اتسجل بنجاح ✅</h2><p>رقم الطلب: <b>#{{o.id}}</b></p><p>رقم الموبايل: {{o.phone}}</p><p>الإجمالي: {{'%.2f'|format(o.total)}} جنيه</p><p>الحالة: {{o.status}}</p><p>احتفظ برقم الطلب ورقم الموبايل لمتابعته.</p><a class="btn" href="{{url_for('track')}}">متابعة الطلب</a></div>'''
    return page('تم الطلب', body, o=o)


@app.route('/track', methods=['GET', 'POST'])
def track():
    result = None
    if request.method == 'POST':
        try:
            oid = int(request.form.get('order_id', ''))
        except ValueError:
            oid = 0
        phone = request.form.get('phone', '').strip()
        with db() as con:
            result = con.execute('SELECT id,status,total,created_at FROM orders WHERE id=? AND phone=?', (oid, phone)).fetchone()
        if not result:
            flash('ملقيناش طلب بالبيانات دي.')
    body = '''<div class="box"><h2>متابعة طلبك</h2><form method="post"><label>رقم الطلب</label><input name="order_id" type="number" required><label>رقم الموبايل المسجل في الطلب</label><input name="phone" required><button>عرض الحالة</button></form>{% if result %}<hr><h3>الطلب #{{result.id}}</h3><p>الحالة: <b>{{result.status}}</b></p><p>الإجمالي: {{'%.2f'|format(result.total)}} جنيه</p><p>التاريخ: {{result.created_at}}</p>{% endif %}</div>'''
    return page('متابعة الطلب', body, result=result)


@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        with db() as con:
            a = con.execute('SELECT * FROM admins WHERE username=?', (username,)).fetchone()
        if a and check_password_hash(a['password_hash'], password):
            session.clear()
            session['admin_id'] = a['id']
            return redirect(url_for('dashboard'))
        flash('اسم المستخدم أو كلمة المرور غلط.')
    body = '''<div class="box" style="max-width:450px;margin:auto"><h2>دخول الإدارة</h2><form method="post"><label>اسم المستخدم</label><input name="username" required><label>كلمة المرور</label><input name="password" type="password" required><button>دخول</button></form><p class="small muted">اسم المستخدم الافتراضي admin. غيّر كلمة المرور فوراً بعد أول دخول.</p></div>'''
    return page('دخول الإدارة', body)


@app.route('/admin/logout')
@admin_required
def logout():
    session.clear()
    return redirect(url_for('home'))


DASH = '''<h1>لوحة الإدارة الخاصة</h1><div class="row"><div class="box"><h3>إجمالي الطلبات</h3><h2>{{stats.orders}}</h2></div><div class="box"><h3>إجمالي المنتجات</h3><h2>{{stats.products}}</h2></div><div class="box"><h3>قيمة التوصيل الحالية</h3><h2>{{fee}} جنيه</h2></div></div>
<div class="box" style="margin:16px 0"><h2>تحديد مصاريف التوصيل</h2><p>أنت اللي بتحدد المبلغ، ويتطبق على الطلبات الجديدة.</p><form method="post" action="{{url_for('save_delivery')}}"><div style="max-width:300px"><label>مصاريف التوصيل بالجنيه</label><input type="number" name="delivery_fee" min="0" step="0.01" value="{{fee}}" required></div><button>حفظ مصاريف التوصيل</button></form></div>
<div class="actions"><a class="btn" href="{{url_for('products_admin')}}">إدارة المنتجات</a><a class="btn" href="{{url_for('orders_admin')}}">إدارة الطلبات</a><a class="btn" href="{{url_for('change_password')}}">تغيير كلمة المرور</a></div>'''


@app.route('/admin')
@admin_required
def dashboard():
    with db() as con:
        stats = {
            'orders': con.execute('SELECT COUNT(*) n FROM orders').fetchone()['n'],
            'products': con.execute('SELECT COUNT(*) n FROM products').fetchone()['n']
        }
    return page('لوحة الإدارة', DASH, stats=stats, fee=setting('delivery_fee', '200'))


@app.route('/admin/delivery', methods=['POST'])
@admin_required
def save_delivery():
    try:
        fee = float(request.form.get('delivery_fee', ''))
    except ValueError:
        fee = -1
    if fee < 0:
        flash('اكتب مبلغ صحيح أكبر من أو يساوي صفر.')
    else:
        with db() as con:
            con.execute("INSERT INTO settings(key,value) VALUES('delivery_fee',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(round(fee, 2)),))
        flash('تم حفظ مصاريف التوصيل. هتتطبق على الطلبات الجديدة فقط.')
    return redirect(url_for('dashboard'))


PRODUCTS_ADMIN = '''<div class="box"><h2>{{'تعديل منتج' if p else 'إضافة منتج جديد'}}</h2><form method="post"><label>اسم المنتج</label><input name="name" value="{{p.name if p else ''}}" required><label>وصف المنتج</label><textarea name="description">{{p.description if p else ''}}</textarea><div class="row"><div><label>سعر البيع</label><input name="price" type="number" min="0" step="0.01" value="{{p.price if p else ''}}" required></div><div><label>سعر الشراء (للإدارة)</label><input name="buy_price" type="number" min="0" step="0.01" value="{{p.buy_price if p else 0}}"></div><div><label>الكمية بالمخزون</label><input name="quantity" type="number" min="0" value="{{p.quantity if p else 0}}" required></div></div><label>رابط صورة المنتج (اختياري)</label><input name="image_url" value="{{p.image_url if p else ''}}"><label><input style="width:auto" type="checkbox" name="active" {% if not p or p.active %}checked{% endif %}> عرض المنتج في المتجر</label><button>حفظ المنتج</button></form></div><h2>المنتجات</h2><div class="scroll"><table><tr><th>المنتج</th><th>السعر</th><th>المخزون</th><th>الحالة</th><th>إجراءات</th></tr>{% for x in products %}<tr><td>{{x.name}}</td><td>{{x.price}} ج</td><td>{{x.quantity}}</td><td>{{'ظاهر' if x.active else 'مخفي'}}</td><td class="actions"><a class="btn" href="{{url_for('products_admin',edit=x.id)}}">تعديل</a><form method="post" action="{{url_for('delete_product',pid=x.id)}}" onsubmit="return confirm('حذف المنتج؟')"><button class="danger">حذف</button></form></td></tr>{% endfor %}</table></div>'''


@app.route('/admin/products', methods=['GET', 'POST'])
@admin_required
def products_admin():
    edit = request.args.get('edit', type=int)
    with db() as con:
        p = con.execute('SELECT * FROM products WHERE id=?', (edit,)).fetchone() if edit else None
        if request.method == 'POST':
            try:
                name = request.form['name'].strip()
                price = float(request.form['price'])
                buy = float(request.form.get('buy_price') or 0)
                qty = int(request.form['quantity'])
                if not name or price < 0 or buy < 0 or qty < 0:
                    raise ValueError()
                vals = (name, request.form.get('description', '').strip(), price, buy, qty,
                        request.form.get('image_url', '').strip(), 1 if request.form.get('active') else 0)
                if edit:
                    con.execute('UPDATE products SET name=?,description=?,price=?,buy_price=?,quantity=?,image_url=?,active=? WHERE id=?', vals + (edit,))
                else:
                    con.execute('INSERT INTO products(name,description,price,buy_price,quantity,image_url,active) VALUES(?,?,?,?,?,?,?)', vals)
                flash('تم حفظ المنتج.')
                return redirect(url_for('products_admin'))
            except (ValueError, KeyError):
                flash('راجع بيانات المنتج والأسعار والكميات.')
        products = con.execute('SELECT * FROM products ORDER BY id DESC').fetchall()
    return page('إدارة المنتجات', PRODUCTS_ADMIN, p=p, products=products)


@app.route('/admin/products/delete/<int:pid>', methods=['POST'])
@admin_required
def delete_product(pid):
    with db() as con:
        con.execute('DELETE FROM products WHERE id=?', (pid,))
    flash('تم حذف المنتج.')
    return redirect(url_for('products_admin'))


ORDERS = '''<h1>الطلبات — للإدارة فقط</h1><div class="scroll"><table><tr><th>رقم</th><th>العميل</th><th>الموبايل</th><th>الإجمالي</th><th>الدفع</th><th>الحالة</th><th>التاريخ</th><th>التفاصيل</th></tr>{% for o in orders %}<tr><td>#{{o.id}}</td><td>{{o.customer_name}}</td><td>{{o.phone}}</td><td>{{o.total}} ج</td><td>{{o.payment_method}}</td><td>{{o.status}}</td><td>{{o.created_at}}</td><td><a class="btn" href="{{url_for('order_detail',oid=o.id)}}">فتح</a></td></tr>{% endfor %}</table></div>'''


@app.route('/admin/orders')
@admin_required
def orders_admin():
    with db() as con:
        orders = con.execute('SELECT * FROM orders ORDER BY id DESC').fetchall()
    return page('إدارة الطلبات', ORDERS, orders=orders)


DETAIL = '''<div class="box"><h2>الطلب #{{o.id}}</h2><p><b>العميل:</b> {{o.customer_name}}</p><p><b>الموبايل:</b> {{o.phone}}</p><p><b>العنوان:</b> {{o.address}}</p><p><b>طريقة الدفع:</b> {{o.payment_method}}</p><p><b>مرجع التحويل:</b> {{o.payment_reference or '—'}}</p><div class="scroll"><table><tr><th>المنتج</th><th>الكمية</th><th>السعر</th><th>الإجمالي</th></tr>{% for i in items %}<tr><td>{{i.product_name}}</td><td>{{i.quantity}}</td><td>{{i.unit_price}}</td><td>{{i.line_total}}</td></tr>{% endfor %}</table></div><p>قيمة المنتجات: {{o.subtotal}} جنيه</p><p>التوصيل: {{o.delivery_fee}} جنيه</p><h3>الإجمالي: {{o.total}} جنيه</h3><form method="post"><label>تحديث حالة الطلب</label><select name="status">{% for s in statuses %}<option {% if o.status==s %}selected{% endif %}>{{s}}</option>{% endfor %}</select><button>حفظ الحالة</button></form><button onclick="window.print()">طباعة الفاتورة</button></div>'''


@app.route('/admin/order/<int:oid>', methods=['GET', 'POST'])
@admin_required
def order_detail(oid):
    with db() as con:
        o = con.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
        if not o:
            abort(404)
        if request.method == 'POST':
            status = request.form.get('status')
            if status in STATUSES:
                old = o['status']
                items = con.execute('SELECT * FROM order_items WHERE order_id=?', (oid,)).fetchall()
                if status == 'مرفوض' and old != 'مرفوض':
                    for i in items:
                        if i['product_id']:
                            con.execute('UPDATE products SET quantity=quantity+? WHERE id=?', (i['quantity'], i['product_id']))
                elif old == 'مرفوض' and status != 'مرفوض':
                    for i in items:
                        if i['product_id']:
                            cur = con.execute('UPDATE products SET quantity=quantity-? WHERE id=? AND quantity>=?', (i['quantity'], i['product_id'], i['quantity']))
                            if cur.rowcount == 0:
                                flash('لا يوجد مخزون كافٍ لإعادة تفعيل الطلب.')
                                return redirect(url_for('order_detail', oid=oid))
                con.execute('UPDATE orders SET status=? WHERE id=?', (status, oid))
                flash('تم تحديث حالة الطلب.')
                return redirect(url_for('order_detail', oid=oid))
        o = con.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone()
        items = con.execute('SELECT * FROM order_items WHERE order_id=?', (oid,)).fetchall()
    return page('تفاصيل الطلب', DETAIL, o=o, items=items, statuses=STATUSES)


@app.route('/admin/password', methods=['GET', 'POST'])
@admin_required
def change_password():
    if request.method == 'POST':
        old = request.form.get('old', '')
        new = request.form.get('new', '')
        with db() as con:
            a = con.execute('SELECT * FROM admins WHERE id=?', (session['admin_id'],)).fetchone()
        if not check_password_hash(a['password_hash'], old):
            flash('كلمة المرور الحالية غير صحيحة.')
        elif len(new) < 8:
            flash('كلمة المرور الجديدة لازم تكون 8 أحرف على الأقل.')
        else:
            with db() as con:
                con.execute('UPDATE admins SET password_hash=? WHERE id=?', (generate_password_hash(new), session['admin_id']))
            flash('تم تغيير كلمة المرور بنجاح.')
    body = '''<div class="box" style="max-width:450px"><h2>تغيير كلمة المرور</h2><form method="post"><label>الحالية</label><input type="password" name="old" required><label>الجديدة (8 أحرف على الأقل)</label><input type="password" name="new" minlength="8" required><button>تغيير</button></form></div>'''
    return page('تغيير كلمة المرور', body)


# IMPORTANT: run database initialization when Gunicorn imports this module too.
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5000'))
    print(f'SMART STORE PRO running on port {port}')
    app.run(host='0.0.0.0', port=port, debug=False)