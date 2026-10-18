import hmac
import json
import os
import secrets
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, abort, jsonify)
from sqlalchemy.exc import IntegrityError
from models import db, Usuario, Calificacion, LogAuditoria
from factores import ETIQUETAS, NUMEROS, calcular_factores, validar_factores

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///nuam.db")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambiar-esto-despues")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE") == "1"   # activar al usar HTTPS
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)             # sesión expira por inactividad
db.init_app(app)

LOG_DIR = os.environ.get("LOG_DIR", os.path.join(app.root_path, "datos"))
MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 10

MERCADOS = ["Acciones", "CFI", "Fondos mutuos"]
ORIGENES = ["manual", "archivo", "sistema"]


# ---------- Inicialización ----------
def crear_usuario(nombre, correo, clave, rol):
    if not Usuario.query.filter_by(correo=correo).first():
        u = Usuario(nombre=nombre, correo=correo, rol=rol)
        u.set_password(clave)
        db.session.add(u)
        db.session.commit()


def inicializar_bd():
    db.create_all()
    crear_usuario("Administrador", "admin@nuam.cl", "Admin1234", "administrador")
    crear_usuario("Corredor Uno", "corredor1@nuam.cl", "Corredor1234", "corredor")


with app.app_context():
    inicializar_bd()


# ---------- Seguridad: CSRF, login, roles ----------
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def proteger_csrf():
    if request.method == "POST":
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
        if not hmac.compare_digest(token, session.get("csrf", "")):
            abort(400)


@app.after_request
def cabeceras_seguridad(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
    return resp


def login_requerido(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return envoltura


def solo_admin(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        if session.get("rol") != "administrador":
            abort(403)
        return f(*args, **kwargs)
    return envoltura


def registrar_log(accion, detalle):
    """Registra el evento en la tabla relacional y en la bitácora de documentos JSON (JSON Lines)."""
    detalle = (detalle or "")[:300]
    ip = request.remote_addr
    db.session.add(LogAuditoria(usuario_id=session.get("usuario_id"),
                                usuario_nombre=session.get("nombre"),
                                accion=accion, detalle=detalle, ip=ip))
    db.session.commit()
    evento = {"fecha": datetime.now().isoformat(timespec="seconds"),
              "usuario_id": session.get("usuario_id"), "usuario": session.get("nombre"),
              "accion": accion, "detalle": detalle, "ip": ip}
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "auditoria.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False) + "\n")
    except OSError:
        pass   # un fallo del archivo no debe botar la operación del usuario


def obtener_calificacion(id):
    c = db.session.get(Calificacion, id)
    if c is None:
        abort(404)
    if session.get("rol") != "administrador" and c.usuario_id != session["usuario_id"]:
        abort(403)   # un corredor no puede tocar calificaciones de otro
    return c


# ---------- Login ----------
@app.route("/")
def inicio():
    return redirect(url_for("mantenedor" if "usuario_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        clave = request.form.get("clave", "")
        usuario = Usuario.query.filter_by(correo=correo).first()
        ahora = datetime.now()

        if usuario and usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
            registrar_log("LOGIN_BLOQUEADO", f"Intento sobre cuenta bloqueada: {correo[:100]}")
            flash("Demasiados intentos fallidos. Intente nuevamente en unos minutos.")
        elif usuario and usuario.check_password(clave):
            usuario.intentos_fallidos = 0
            usuario.bloqueado_hasta = None
            db.session.commit()
            session.clear()
            session.permanent = True
            session["usuario_id"] = usuario.id
            session["nombre"] = usuario.nombre
            session["rol"] = usuario.rol
            registrar_log("LOGIN", f"Inicio de sesión de {usuario.correo}")
            return redirect(url_for("mantenedor"))
        else:
            if usuario:
                usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1
                if usuario.intentos_fallidos >= MAX_INTENTOS:
                    usuario.bloqueado_hasta = ahora + timedelta(minutes=MINUTOS_BLOQUEO)
                    usuario.intentos_fallidos = 0
                    db.session.commit()
                    registrar_log("BLOQUEO_CUENTA", f"Cuenta bloqueada por intentos fallidos: {correo[:100]}")
                else:
                    db.session.commit()
            registrar_log("LOGIN_FALLIDO", f"Credenciales incorrectas para: {correo[:100]}")
            flash("Correo o contraseña incorrectos")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Mantenedor (grilla + filtros) ----------
@app.route("/mantenedor")
@login_requerido
def mantenedor():
    mercado = request.args.get("mercado", "")
    origen = request.args.get("origen", "")
    ejercicio = request.args.get("ejercicio", "").strip()

    q = Calificacion.query
    if session["rol"] != "administrador":
        q = q.filter_by(usuario_id=session["usuario_id"])   # calificaciones locales de cada corredor
    if mercado in MERCADOS:
        q = q.filter_by(mercado=mercado)
    if origen in ORIGENES:
        q = q.filter_by(origen=origen)
    if ejercicio.isdigit():
        q = q.filter_by(ejercicio=int(ejercicio))
    filas = q.order_by(Calificacion.fecha_pago.desc(), Calificacion.id.desc()).limit(300).all()

    return render_template("mantenedor.html", filas=filas, numeros=NUMEROS, etiquetas=ETIQUETAS,
                           mercados=MERCADOS, origenes=ORIGENES,
                           filtro={"mercado": mercado, "origen": origen, "ejercicio": ejercicio})


# ---------- Ingreso / modificación ----------
def a_numero(texto, nombre):
    texto = (texto or "").strip().replace(",", ".")
    if texto == "":
        return 0.0
    try:
        return float(texto)
    except ValueError:
        raise ValueError(f"'{nombre}' debe ser un número.")


def procesar_formulario(form, c=None):
    """Valida el formulario. Devuelve (datos, errores)."""
    errores = []
    datos = {}

    datos["mercado"] = form.get("mercado", "")
    if datos["mercado"] not in MERCADOS:
        errores.append("Seleccione un mercado válido.")
    datos["instrumento"] = form.get("instrumento", "").strip()
    if not datos["instrumento"]:
        errores.append("El instrumento es obligatorio.")
    elif len(datos["instrumento"]) > 60:
        errores.append("El instrumento no puede superar 60 caracteres.")
    datos["descripcion"] = form.get("descripcion", "").strip()[:200]

    try:
        datos["ejercicio"] = int(form.get("ejercicio", ""))
        if not 1990 <= datos["ejercicio"] <= 2100:
            errores.append("El ejercicio (año comercial) no es válido.")
    except ValueError:
        errores.append("El ejercicio (año comercial) debe ser un número.")
    try:
        datos["secuencia_evento"] = int(form.get("secuencia_evento", ""))
        if datos["secuencia_evento"] <= 10000:
            errores.append("La secuencia de evento debe ser superior a 10.000.")
    except ValueError:
        errores.append("La secuencia de evento debe ser un número.")
    try:
        datos["fecha_pago"] = date.fromisoformat(form.get("fecha_pago", ""))
    except ValueError:
        errores.append("La fecha de pago es obligatoria.")

    for campo, nombre in (("dividendo", "Dividendo"), ("valor_historico", "Valor histórico"),
                          ("factor_actualizacion", "Factor de actualización")):
        try:
            datos[campo] = a_numero(form.get(campo), nombre)
        except ValueError as e:
            errores.append(str(e))
    datos["isfut"] = form.get("isfut") == "on"

    # montos y factores
    modo = form.get("modo", "montos")
    montos, factores = {}, {}
    for n in NUMEROS:
        try:
            montos[n] = a_numero(form.get(f"monto_{n}"), f"Monto {n}")
            if montos[n] < 0:
                errores.append(f"El monto {n} no puede ser negativo.")
        except ValueError as e:
            errores.append(str(e))
        try:
            factores[n] = a_numero(form.get(f"factor_{n}"), f"Factor {n}")
        except ValueError as e:
            errores.append(str(e))

    if not errores:
        if modo == "montos":
            if sum(montos[n] for n in range(8, 20)) <= 0:
                errores.append("Ingrese al menos un monto entre las columnas 8 y 19.")
            else:
                factores = calcular_factores(montos)
        errores += validar_factores(factores)

    datos["montos"], datos["factores"] = montos, factores
    return datos, errores


def existe_duplicado(usuario_id, datos, excluir_id=None):
    q = Calificacion.query.filter_by(usuario_id=usuario_id, mercado=datos["mercado"],
                                     instrumento=datos["instrumento"], ejercicio=datos["ejercicio"],
                                     secuencia_evento=datos["secuencia_evento"])
    if excluir_id:
        q = q.filter(Calificacion.id != excluir_id)
    return q.first() is not None


MSG_DUPLICADO = "Ya existe una calificación con el mismo mercado, instrumento, ejercicio y secuencia de evento."


def aplicar_datos(c, datos):
    for campo in ("mercado", "instrumento", "descripcion", "ejercicio", "secuencia_evento",
                  "fecha_pago", "dividendo", "valor_historico", "factor_actualizacion", "isfut"):
        setattr(c, campo, datos[campo])
    for n in NUMEROS:
        setattr(c, f"monto_{n}", datos["montos"][n])
        setattr(c, f"factor_{n}", datos["factores"][n])
    c.fecha_modificacion = datetime.now()


def valores_desde_calificacion(c):
    v = {"mercado": c.mercado, "instrumento": c.instrumento, "ejercicio": c.ejercicio,
         "secuencia_evento": c.secuencia_evento, "dividendo": c.dividendo,
         "fecha_pago": c.fecha_pago.isoformat(), "valor_historico": c.valor_historico,
         "descripcion": c.descripcion or "", "isfut": "on" if c.isfut else "",
         "factor_actualizacion": c.factor_actualizacion, "modo": "montos"}
    for n in NUMEROS:
        v[f"monto_{n}"] = getattr(c, f"monto_{n}")
        v[f"factor_{n}"] = getattr(c, f"factor_{n}")
    return v


@app.route("/calificaciones/nueva", methods=["GET", "POST"])
@login_requerido
def nueva_calificacion():
    if request.method == "POST":
        datos, errores = procesar_formulario(request.form)
        if not errores and existe_duplicado(session["usuario_id"], datos):
            errores.append(MSG_DUPLICADO)
        if not errores:
            c = Calificacion(usuario_id=session["usuario_id"], origen="manual")
            aplicar_datos(c, datos)
            db.session.add(c)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash(MSG_DUPLICADO)
                return render_template("formulario.html", titulo="Ingresar calificación",
                                       valores=request.form.to_dict(), numeros=NUMEROS,
                                       etiquetas=ETIQUETAS, mercados=MERCADOS)
            registrar_log("INGRESO", f"Calificación {c.id} ({c.instrumento}, {c.ejercicio}) ingresada")
            flash("Calificación ingresada correctamente.", "ok")
            return redirect(url_for("mantenedor"))
        for e in errores:
            flash(e)
        valores = request.form.to_dict()
    else:
        sig = (db.session.query(db.func.max(Calificacion.secuencia_evento)).scalar() or 10000) + 1
        valores = {"mercado": request.args.get("mercado", "Acciones"), "ejercicio": date.today().year,
                   "secuencia_evento": sig, "dividendo": 0, "factor_actualizacion": 0,
                   "modo": "montos"}
    return render_template("formulario.html", titulo="Ingresar calificación", valores=valores,
                           numeros=NUMEROS, etiquetas=ETIQUETAS, mercados=MERCADOS)


@app.route("/calificaciones/<int:id>/editar", methods=["GET", "POST"])
@login_requerido
def editar_calificacion(id):
    c = obtener_calificacion(id)
    if request.method == "POST":
        datos, errores = procesar_formulario(request.form, c)
        if not errores and existe_duplicado(c.usuario_id, datos, excluir_id=c.id):
            errores.append(MSG_DUPLICADO)
        if not errores:
            aplicar_datos(c, datos)
            db.session.commit()
            registrar_log("MODIFICACION", f"Calificación {c.id} ({c.instrumento}, {c.ejercicio}) modificada")
            flash("Calificación modificada correctamente.", "ok")
            return redirect(url_for("mantenedor"))
        for e in errores:
            flash(e)
        valores = request.form.to_dict()
    else:
        valores = valores_desde_calificacion(c)
    return render_template("formulario.html", titulo="Modificar calificación", valores=valores,
                           numeros=NUMEROS, etiquetas=ETIQUETAS, mercados=MERCADOS)


@app.route("/calificaciones/<int:id>/eliminar", methods=["POST"])
@login_requerido
def eliminar_calificacion(id):
    c = obtener_calificacion(id)
    detalle = f"Calificación {c.id} ({c.instrumento}, {c.ejercicio}) eliminada"
    db.session.delete(c)
    db.session.commit()
    registrar_log("ELIMINACION", detalle)
    flash("Calificación eliminada.", "ok")
    return redirect(url_for("mantenedor"))


@app.route("/api/calcular", methods=["POST"])
@login_requerido
def api_calcular():
    """Botón 'Calcular': convierte montos en factores usando la misma regla del servidor."""
    datos = request.get_json(silent=True) or {}
    montos = {}
    for n in NUMEROS:
        try:
            montos[n] = a_numero(str(datos.get(str(n), "")), f"Monto {n}")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    if sum(montos[n] for n in range(8, 20)) <= 0:
        return jsonify({"error": "Ingrese al menos un monto entre las columnas 8 y 19."}), 400
    factores = calcular_factores(montos)
    return jsonify({"factores": {str(n): v for n, v in factores.items()},
                    "errores": validar_factores(factores)})


# ---------- Log de auditoría (solo administrador) ----------
@app.route("/log")
@login_requerido
@solo_admin
def ver_log():
    registros = LogAuditoria.query.order_by(LogAuditoria.id.desc()).limit(300).all()
    return render_template("log.html", registros=registros)


if __name__ == "__main__":
    app.run(debug=True)
