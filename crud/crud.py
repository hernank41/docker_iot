from quart import Quart, render_template, request, redirect, url_for, flash, session, g
from hypercorn.middleware import ProxyFixMiddleware
import os
import logging
from functools import wraps
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import asyncmy
import asyncio

ph = PasswordHasher()

logging.basicConfig(format='%(asctime)s - CRUD - %(levelname)s - %(message)s', level=logging.INFO)

app = Quart(__name__)

@app.before_request
async def handle_root_path():
    # Si Hypercorn no recibe root_path, lo forzamos
    if not request.scope.get("root_path"):
        request.scope["root_path"] = app.config.get("APPLICATION_ROOT", "/crud")
        
PREFIX = os.environ.get("APP_PREFIX", "/crud")
app.config["APPLICATION_ROOT"] = PREFIX
app.secret_key = os.environ["FLASK_SECRET_KEY"]
app.config['PERMANENT_SESSION_LIFETIME'] = 600
logging.info(app.config["APPLICATION_ROOT"])

# Pool de conexiones asíncronas a MySQL
async def create_db_pool():
    pool = await asyncmy.create_pool(
        host=os.environ["MYSQL_HOST"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        db=os.environ["MYSQL_DB"],
        autocommit=True,
        minsize=1,
        maxsize=10
    )
    return pool

@app.before_serving
async def startup():
    app.db_pool = await create_db_pool()

@app.after_serving
async def shutdown():
    app.db_pool.close()
    await app.db_pool.wait_closed()

# Helper para ejecutar consultas
async def execute_query(query, args=None, fetch_one=False, fetch_all=False):
    async with app.db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, args)
            if fetch_one:
                result = await cur.fetchone()
                return result
            elif fetch_all:
                result = await cur.fetchall()
                return result
            else:
                return cur.rowcount

# Decorador de autenticación (compatible con async)
def require_login(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for('login'))
        g.usuario = session.get("user_id")   # igual que en Flask
        return await f(*args, **kwargs)
    return decorated_function

# ---------- Rutas ----------
@app.route("/registrar", methods=["GET", "POST"])
async def registrar():
    if request.method == "POST":
        form = await request.form
        usuario = form.get("usuario")
        password = form.get("password")

        if not usuario:
            return "el campo usuario es oblicatorio"
        if not password:
            return "el campo contraseña es oblicatorio"

        # argon2.hash es bloqueante -> lo ejecutamos en un hilo separado
        passhash = await asyncio.to_thread(ph.hash, password)
        logging.info(passhash)

        rows_affected = await execute_query(
            "INSERT INTO usuarios (usuario, hash) VALUES (%s, %s)",
            (usuario, passhash)
        )
        if rows_affected:
            flash('Se agregó un usuario')
            logging.info("se agregó un usuario")

        return redirect(url_for('index'))

    return await render_template('registrar.html')

@app.route("/login", methods=["GET", "POST"])
async def login():
    if request.method == "POST":
        form = await request.form
        usuario = form.get("usuario")
        password = form.get("password")

        if not usuario:
            return "el campo usuario es oblicatorio"
        if not password:
            return "el campo contraseña es oblicatorio"

        row = await execute_query(
            "SELECT * FROM usuarios WHERE usuario LIKE %s",
            (usuario,),
            fetch_one=True
        )
        if row:
            try:
                # verify también es bloqueante
                await asyncio.to_thread(ph.verify, row[2], password)
                session.permanent = True
                session["user_id"] = usuario
                logging.info("se autenticó correctamente")
                return redirect(url_for('index'))
            except VerifyMismatchError:
                flash('usuario o contraseña incorrecto')
                return redirect(url_for('login'))
        else:
            flash('usuario o contraseña incorrecto')
            return redirect(url_for('login'))

    return await render_template('login.html')

@app.route('/')
@require_login
async def index():
    contactos = await execute_query('SELECT * FROM contactos', fetch_all=True)
    return await render_template('index.html', contactos=contactos)

@app.route('/add_contact', methods=['POST'])
@require_login
async def add_contact():
    form = await request.form
    nombre = form['nombre']
    tel = form['tel']
    email = form['email']
    rows_affected = await execute_query(
        "INSERT INTO contactos (nombre, tel, email) VALUES (%s, %s, %s)",
        (nombre, tel, email)
    )
    if rows_affected:
        flash('Se agregó un contacto')
        logging.info("se agregó un contacto")
    return redirect(url_for('index'))

@app.route('/borrar/<string:id>', methods=['GET'])
@require_login
async def borrar_contacto(id):
    rows_affected = await execute_query(
        'DELETE FROM contactos WHERE id = %s',
        (id,)
    )
    if rows_affected:
        flash('Se eliminó un contacto')
        logging.info("se eliminó un contacto")
    return redirect(url_for('index'))

@app.route('/editar/<id>', methods=['GET'])
@require_login
async def conseguir_contacto(id):
    contacto = await execute_query(
        'SELECT * FROM contactos WHERE id = %s',
        (id,),
        fetch_one=True
    )
    logging.info(contacto)
    return await render_template('editar-contacto.html', contacto=contacto)

@app.route('/actualizar/<id>', methods=['POST'])
@require_login
async def actualizar_contacto(id):
    form = await request.form
    nombre = form['nombre']
    tel = form['tel']
    email = form['email']
    rows_affected = await execute_query(
        "UPDATE contactos SET nombre=%s, tel=%s, email=%s WHERE id=%s",
        (nombre, tel, email, id)
    )
    if rows_affected:
        flash('Se actualizó un contacto')
        logging.info("se actualizó un contacto")
    return redirect(url_for('index'))

@app.route("/logout")
@require_login
async def logout():
    user = g.usuario   # o session.get("user_id")
    session.clear()
    logging.info(f"el usuario {user} cerró su sesión")
    return redirect(url_for('index'))

app.asgi_app = ProxyFixMiddleware(app.asgi_app, mode="legacy", trusted_hops=1)

if __name__ == "__main__":
    app.run()