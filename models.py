from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Usuario(db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default="corredor")  # corredor / administrador

    def set_password(self, clave):
        self.password_hash = generate_password_hash(clave)

    def check_password(self, clave):
        return check_password_hash(self.password_hash, clave)


class Calificacion(db.Model):
    __tablename__ = "calificaciones"
    id = db.Column(db.Integer, primary_key=True)
    mercado = db.Column(db.String(30), nullable=False)       # Acciones, CFI, Fondos mutuos
    instrumento = db.Column(db.String(60), nullable=False)
    ejercicio = db.Column(db.Integer, nullable=False)        # año comercial
    secuencia_evento = db.Column(db.Integer, nullable=False)
    dividendo = db.Column(db.Float, default=0)
    fecha_pago = db.Column(db.Date, nullable=False)
    valor_historico = db.Column(db.Float, default=0)
    descripcion = db.Column(db.String(200))
    isfut = db.Column(db.Boolean, default=False)
    factor_actualizacion = db.Column(db.Float, default=0)
    origen = db.Column(db.String(20), default="manual")      # manual / archivo / sistema
    fecha_modificacion = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    usuario = db.relationship("Usuario", backref="calificaciones")

    # Factores 8 al 37: factor_8, factor_9, ..., factor_37
    for _n in range(8, 38):
        locals()[f"factor_{_n}"] = db.Column(db.Float, default=0)
    del _n

    def suma_factores_8_16(self):
        return sum((getattr(self, f"factor_{n}") or 0) for n in range(8, 17))