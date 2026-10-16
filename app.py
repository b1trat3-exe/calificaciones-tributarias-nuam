from flask import Flask
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


@app.route("/")
def inicio():
    return "Mantenedor de Calificaciones Tributarias - NUAM"


if __name__ == "__main__":
    app.run(debug=True)