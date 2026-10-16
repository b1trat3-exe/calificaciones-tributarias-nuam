from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, Usuario

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///nuam.db"
app.config["SECRET_KEY"] = "cambiar-esto-despues"
db.init_app(app)

with app.app_context():
    db.create_all()
    if not Usuario.query.filter_by(correo="admin@nuam.cl").first():
        admin = Usuario(nombre="Administrador", correo="admin@nuam.cl", rol="administrador")
        admin.set_password("Admin1234")
        db.session.add(admin)
        db.session.commit()


def login_requerido(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return envoltura


@app.route("/")
def inicio():
    if "usuario_id" in session:
        return redirect(url_for("mantenedor"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        clave = request.form.get("clave", "")
        usuario = Usuario.query.filter_by(correo=correo).first()
        if usuario and usuario.check_password(clave):
            session.clear()
            session["usuario_id"] = usuario.id
            session["nombre"] = usuario.nombre
            session["rol"] = usuario.rol
            return redirect(url_for("mantenedor"))
        flash("Correo o contraseña incorrectos")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/mantenedor")
@login_requerido
def mantenedor():
    return render_template("mantenedor.html")


if __name__ == "__main__":
    app.run(debug=True)