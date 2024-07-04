from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
import logging, os, aiomysql, traceback, asyncio, locale
from functools import wraps
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash


import ssl, certifi, json, traceback
import aiomqtt

logging.basicConfig(format='%(asctime)s - CRUD - %(levelname)s - %(message)s', level=logging.INFO)

app = Flask(__name__)

app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

app.secret_key = os.environ["FLASK_SECRET_KEY"]
app.config["MYSQL_USER"] = os.environ["MYSQL_USER"]
app.config["MYSQL_PASSWORD"] = os.environ["MYSQL_PASSWORD"]
app.config["MYSQL_DB"] = os.environ["MYSQL_DB"]
app.config["MYSQL_HOST"] = os.environ["MYSQL_HOST"]
app.config['PERMANENT_SESSION_LIFETIME']=1800
mysql = MySQL(app)

tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
tls_context.verify_mode = ssl.CERT_REQUIRED
tls_context.check_hostname = True
tls_context.load_default_certs()

nodo = ''

# rutas

def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    """Registrar usuario"""
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("usuario"):
            return "el campo usuario es oblicatorio"

        # Ensure password was submitted
        elif not request.form.get("password"):
            return "el campo contraseña es oblicatorio"

        passhash=generate_password_hash(request.form.get("password"), method='scrypt', salt_length=16)
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO usuarios (usuario, hash) VALUES (%s,%s)", (request.form.get("usuario"), passhash[17:]))
        if mysql.connection.affected_rows():
            flash('Se agregó un usuario')  # usa sesión
            logging.info("se agregó un usuario")
        mysql.connection.commit()
        return redirect(url_for('index'))

    return render_template('registrar.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("usuario"):
            return "el campo usuario es oblicatorio"
        # Ensure password was submitted
        elif not request.form.get("password"):
            return "el campo contraseña es oblicatorio"

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM usuarios WHERE usuario LIKE %s", (request.form.get("usuario"),))
        rows=cur.fetchone()
        if(rows):
            if (check_password_hash('scrypt:32768:8:1$' + rows[2],request.form.get("password"))):
                session.permanent = True
                session["user_id"]=request.form.get("usuario")
                logging.info("se autenticó correctamente")
                return redirect(url_for('index'))
            else:
                flash('usuario o contraseña incorrecto')
                return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/')
@require_login
def index():
    cur = mysql.connection.cursor()
    cur.execute('SELECT * FROM nodos')
    datos = cur.fetchall()
    cur.close()
    theme = session.get('theme', 'cerulean')
    logging.info(datos)
    return render_template('index.html', nodos = datos,theme=theme)

@app.route('/cambiar_tema')
def cambiar_tema():
    tema_actual = session.get('theme', 'cerulean')
    nuevo_tema = 'darkly' if tema_actual == 'cerulean' else 'cerulean'
    session['theme'] = nuevo_tema
    return redirect(url_for('index'))

@app.route('/add_nodo', methods=['GET'])
@require_login
def add_nodo():
    global nodo
    nodo = request.args.get('id')
    logging.info(f'Selected ID: {nodo}')  # Log the selected ID

    if nodo is not None:
        flash(f'You selected: {nodo}')
        return render_template('panel.html',theme='cerulean')


@app.route('/destello', methods=['GET'])
@require_login
def destello():
    logging.info('Destello')  # Log the selected ID
    flash('Destello')
    global nodo

    async def destello_mqtt():
        async with aiomqtt.Client(
            os.environ["SERVIDOR"],
            username=os.environ["MQTT_USR"],
            password=os.environ["MQTT_PASS"],
            port=int(os.environ["PUERTO_MQTTS"]),
            tls_context=tls_context,
        ) as client:
            topic = nodo + '/Destello'
            await client.publish(topic=topic, payload=1, qos=1)
    asyncio.run(destello_mqtt())
    return render_template('panel.html',theme='cerulean')

@app.route('/setpoint', methods=['GET'])
@require_login
def setpoint():
    setpoint = request.args.get('setpoint')
    logging.info(f'Setpoint: {setpoint}')  # Log the selected ID
    flash(f'Setpoint: {setpoint}')

    global nodo
    async def setpoint_mqtt():
        async with aiomqtt.Client(
            os.environ["SERVIDOR"],
            username=os.environ["MQTT_USR"],
            password=os.environ["MQTT_PASS"],
            port=int(os.environ["PUERTO_MQTTS"]),
            tls_context=tls_context,
        ) as client:
            topic = nodo + '/Setpoint'
            await client.publish(topic=topic, payload=setpoint, qos=1)
    asyncio.run(setpoint_mqtt())
    return render_template('panel.html',theme='cerulean')

@app.route('/Volver', methods=['GET'])
@require_login
def Volver():
    return redirect(url_for('index'))

@app.route("/logout")
@require_login
def logout():
    session.clear()
    logging.info("el usuario {} cerró su sesión".format(session.get("user_id")))
    return redirect(url_for('index'))
