import csv
import os
import tempfile
import io
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
from docxtpl import DocxTemplate
from datetime import datetime
from num2words import num2words
import subprocess
import random
import pytz
from PyPDF2 import PdfReader, PdfWriter
from docx import Document  # Asegurarse de importar Document
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
import pandas as pd
from io import BytesIO
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Añadir impresión de la versión de Flask para depuración
import flask
print(f"Flask version: {flask.__version__}")

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecretkey')

# Configuración de la base de datos
# Asegúrate de usar 'postgresql' o 'postgresql+psycopg2' en la URL
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///recibos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuraciones de seguridad para cookies
app.config['SESSION_COOKIE_SECURE'] = False  # Cambia a True en producción con HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db = SQLAlchemy(app)

# Inicializar Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Redirige a 'login' si no está autenticado
login_manager.login_message_category = 'info'  # Categoría para mensajes flash

# Ruta para los recursos externos
def get_resource_path(relative_path):
    base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Rutas del CSV y la plantilla DOCX
CSV_PATH = get_resource_path('codigos.csv')
DOCX_TEMPLATE_PATH = get_resource_path('170000.docx')

# Modelos de la base de datos
class Recibo(db.Model):
    __tablename__ = 'recibos'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    contribuyente = db.Column(db.String(255), nullable=False)
    calle = db.Column(db.String(255), nullable=False)
    colonia = db.Column(db.String(255), nullable=False)
    municipio = db.Column(db.String(255), nullable=False)
    dependencia = db.Column(db.String(255), nullable=False)
    observaciones = db.Column(db.Text, nullable=True)
    elaborado_por = db.Column(db.String(255), nullable=False)
    orden_pago = db.Column(db.String(50), unique=True, nullable=False)
    total_global = db.Column(db.Float, nullable=False)
    total_en_letras = db.Column(db.String(255), nullable=False)
    centavos = db.Column(db.Integer, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    conceptos = relationship('Concepto', backref='recibo', cascade="all, delete-orphan")

class Concepto(db.Model):
    __tablename__ = 'conceptos'
    id = db.Column(db.Integer, primary_key=True)
    concepto = db.Column(db.String(255), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    recibo_id = db.Column(db.Integer, db.ForeignKey('recibos.id'), nullable=False)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Cargar usuario
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Función para leer el archivo CSV
def leer_codigos_postales():
    codigos_postales = {}
    if not os.path.exists(CSV_PATH):
        print(f"Archivo CSV no encontrado en la ruta: {CSV_PATH}")
        return codigos_postales
    with open(CSV_PATH, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) < 4:
                continue  # Evita errores si una fila tiene menos de 4 columnas
            colonia = row[0]
            tipo = row[1]
            municipio = row[2]
            codigo_postal = row[3]
            codigos_postales[codigo_postal] = {
                'colonia': colonia.upper(),
                'municipio': municipio.upper()
            }
    return codigos_postales

codigos_postales = leer_codigos_postales()

# Función para convertir números a letras
def numero_a_letras(num):
    try:
        return num2words(num, lang='es').upper()
    except NotImplementedError:
        return "Número no soportado"

# Función para generar el folio
def generar_folio(fecha):
    año = fecha.year
    mes = fecha.strftime('%B')[0].upper()
    random_digits = f"{random.randint(1000, 9999)}"
    return f"{año}{mes}{random_digits}"

# Crear las tablas antes de iniciar la app
with app.app_context():
    print("Creando tablas en la base de datos...")
    db.create_all()
    print("Tablas creadas exitosamente.")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('listar_recibos'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Has iniciado sesión correctamente.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('listar_recibos'))
        else:
            flash('Nombre de usuario o contraseña incorrectos.', 'danger')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('listar_recibos'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Por favor completa todos los campos.', 'danger')
            return redirect(url_for('register'))
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('El nombre de usuario ya existe.', 'warning')
            return redirect(url_for('register'))
        
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('Usuario registrado exitosamente. Por favor inicia sesión.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required  # Mantener logout protegido
def logout():
    logout_user()
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('index'))

@app.route('/get_cp_data', methods=['GET'])
def get_cp_data():
    cp = request.args.get('cp')
    if cp in codigos_postales:
        data = codigos_postales[cp]
        formatted_colonia = f"{data['colonia']}. CP: {cp}"
        formatted_municipio = f"{data['municipio']}, SAN LUIS POTOSÍ"
        return jsonify({
            'colonia': formatted_colonia,
            'municipio': formatted_municipio
        })
    else:
        return jsonify({'error': 'Código postal no encontrado'})

@app.route('/generate-docx', methods=['POST'])
# Remover @login_required para que esta ruta no requiera autenticación
def generate_docx_route():
    try:
        # Validar que todos los campos requeridos estén presentes
        fecha_seleccionada = request.form.get('fecha')
        if not fecha_seleccionada:
            raise ValueError("La fecha es requerida")
        fecha_seleccionada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d').date()

        # Validar otros campos requeridos
        required_fields = ['contribuyente', 'calle', 'colonia', 'municipio', 'dependencia', 'elaborado_por']
        for field in required_fields:
            if not request.form.get(field):
                raise ValueError(f"El campo '{field}' es requerido")

        datos_formulario = {
            'contribuyente': request.form['contribuyente'].upper(),
            'calle': request.form['calle'].upper(),
            'colonia': request.form['colonia'].upper(),
            'municipio': request.form['municipio'].upper(),
            'dependencia': request.form['dependencia'].upper(),
            'observaciones': request.form.get('observaciones', '').upper(),
            'elaborado_por': request.form['elaborado_por'].upper(),
            'orden_pago': generar_folio(fecha_seleccionada)
        }

        # Procesar los conceptos
        conceptos = []
        conceptos_raw = zip(
            request.form.getlist('concepto[]'),
            request.form.getlist('valor[]'),
            request.form.getlist('cantidad[]'),
            request.form.getlist('total[]')
        )
        for concepto, valor, cantidad, total in conceptos_raw:
            if not concepto or not valor or not cantidad or not total:
                raise ValueError("Todos los campos de concepto son requeridos")
            conceptos.append({
                'concepto': concepto.upper(),
                'valor': float(valor),
                'cantidad': float(cantidad),
                'total': float(total)
            })

        # Calcular totales
        total_global = sum(c['total'] for c in conceptos)
        centavos = int(round((total_global - int(total_global)) * 100))
        total_en_letras = numero_a_letras(int(total_global))

        # Crear el recibo en la base de datos
        nuevo_recibo = Recibo(
            fecha=fecha_seleccionada,
            contribuyente=datos_formulario['contribuyente'],
            calle=datos_formulario['calle'],
            colonia=datos_formulario['colonia'],
            municipio=datos_formulario['municipio'],
            dependencia=datos_formulario['dependencia'],
            observaciones=datos_formulario['observaciones'],
            elaborado_por=datos_formulario['elaborado_por'],
            orden_pago=datos_formulario['orden_pago'],
            total_global=total_global,
            total_en_letras=f"({total_en_letras} PESOS {centavos:02d}/100 M.N.)" if centavos > 0 else f"({total_en_letras} PESOS 00/100 M.N.)",
            centavos=centavos
        )

        # Añadir conceptos
        for c in conceptos:
            nuevo_concepto = Concepto(
                concepto=c['concepto'],
                valor=c['valor'],
                cantidad=c['cantidad'],
                total=c['total'],
                recibo=nuevo_recibo
            )
            db.session.add(nuevo_concepto)

        db.session.add(nuevo_recibo)
        db.session.commit()

        # Generar el documento DOCX en memoria
        output_docx_path = generar_docx(datos_formulario, conceptos, total_global, total_en_letras, centavos)

        # Generar el PDF en memoria
        output_pdf_io = generar_pdf(output_docx_path)

        # Enviar el PDF directamente desde la memoria
        output_pdf_io.seek(0)  # Asegurarse de que el puntero esté al inicio
        return send_file(
            output_pdf_io,
            mimetype='application/pdf',
            as_attachment=False,
            download_name="document.pdf"
        )

    except ValueError as e:
        flash(str(e), 'danger')  # Cambiar 'error' a 'danger' para coincidir con Bootstrap
        return redirect(url_for('index'))

    except Exception as e:
        print(f"Error inesperado: {e}")
        flash('Error al generar el documento. Intente de nuevo.', 'danger')
        return redirect(url_for('index'))

def generar_docx(datos_formulario, conceptos, total_global, total_en_letras, centavos):
    doc = DocxTemplate(DOCX_TEMPLATE_PATH)
    
    timezone = pytz.timezone('America/Mexico_City')
    fecha_actual = datetime.now(timezone).strftime("%d/%m/%Y %I:%M %p")

    contexto = {
        'folio': datos_formulario['orden_pago'],
        'fecha_actual': f"FI: {fecha_actual}",
        'contribuyente': datos_formulario['contribuyente'],
        'calle': datos_formulario['calle'],
        'colonia': datos_formulario['colonia'],
        'municipio': datos_formulario['municipio'],
        'dependencia': datos_formulario['dependencia'],
        'observaciones': datos_formulario['observaciones'],
        'elaborado_por': datos_formulario['elaborado_por'],
        'conceptos': conceptos,
        'total_global': f"${total_global:.2f}",
        'total_letras': f"({total_en_letras} PESOS {centavos:02d}/100 M.N.)" if centavos > 0 else f"({total_en_letras} PESOS 00/100 M.N.)"
    }

    # Crear archivo temporal para el DOCX
    with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp_docx:
        doc.render(contexto)
        doc.save(tmp_docx.name)
        tmp_docx_path = tmp_docx.name

    # Abrir el DOCX con python-docx para eliminar párrafos vacíos al final
    document = Document(tmp_docx_path)
    paragraphs = document.paragraphs

    # Iterar desde el final y eliminar párrafos vacíos
    for paragraph in reversed(paragraphs):
        if not paragraph.text.strip():
            p = paragraph._element
            p.getparent().remove(p)
        else:
            break  # Detenerse al encontrar el primer párrafo no vacío

    # Guardar nuevamente el DOCX sin los párrafos vacíos
    document.save(tmp_docx_path)

    return tmp_docx_path

def generar_pdf(input_docx_path):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
        try:
            subprocess.run([
                "soffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", os.path.dirname(tmp_pdf.name),
                input_docx_path
            ], check=True)
        except subprocess.CalledProcessError as e:
            raise Exception(f"Error al convertir DOCX a PDF: {e}")
        
        # La conversión crea un archivo PDF con el mismo nombre base que el DOCX
        pdf_filename = os.path.splitext(os.path.basename(input_docx_path))[0] + '.pdf'
        pdf_path = os.path.join(os.path.dirname(tmp_pdf.name), pdf_filename)
        
        # Leer el PDF en BytesIO
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        # Limpiar archivos temporales
        os.remove(input_docx_path)
        os.remove(pdf_path)
        
        return io.BytesIO(pdf_bytes)

@app.route('/recibos')
@login_required  # Mantener esta ruta protegida
def listar_recibos():
    page = request.args.get('page', 1, type=int)
    recibos = Recibo.query.order_by(Recibo.fecha_creacion.desc()).paginate(page=page, per_page=10)
    return render_template('recibos.html', recibos=recibos)

@app.route('/exportar_excel')
# Remover @login_required para que esta ruta no requiera autenticación
def exportar_excel():
    recibos = Recibo.query.all()
    data = []
    for recibo in recibos:
        for concepto in recibo.conceptos:
            data.append({
                'ID': recibo.id,
                'Fecha': recibo.fecha.strftime('%Y-%m-%d'),
                'Contribuyente': recibo.contribuyente,
                'Calle': recibo.calle,
                'Colonia': recibo.colonia,
                'Municipio': recibo.municipio,
                'Dependencia': recibo.dependencia,
                'Observaciones': recibo.observaciones,
                'Elaborado Por': recibo.elaborado_por,
                'Orden de Pago': recibo.orden_pago,
                'Total Global': recibo.total_global,
                'Total en Letras': recibo.total_en_letras,
                'Centavos': recibo.centavos,
                'Fecha de Creación': recibo.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S'),
                'Concepto': concepto.concepto,
                'Valor': concepto.valor,
                'Cantidad': concepto.cantidad,
                'Total Concepto': concepto.total
            })
    
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Recibos')
    output.seek(0)
    
    return send_file(output, download_name="recibos.xlsx", as_attachment=True)

@app.route('/descargar_pdf/<int:recibo_id>')
# Remover @login_required para que esta ruta no requiera autenticación
def descargar_pdf(recibo_id):
    recibo = Recibo.query.get_or_404(recibo_id)
    conceptos = [{
        'concepto': c.concepto,
        'valor': f"${c.valor:.2f}",
        'cantidad': c.cantidad,
        'total': f"${c.total:.2f}"
    } for c in recibo.conceptos]
    
    # Generar el documento DOCX en memoria
    datos_formulario = {
        'contribuyente': recibo.contribuyente,
        'calle': recibo.calle,
        'colonia': recibo.colonia,
        'municipio': recibo.municipio,
        'dependencia': recibo.dependencia,
        'observaciones': recibo.observaciones,
        'elaborado_por': recibo.elaborado_por,
        'orden_pago': recibo.orden_pago
    }
    total_global = recibo.total_global
    total_en_letras = numero_a_letras(int(total_global))
    centavos = recibo.centavos

    output_docx_path = generar_docx(datos_formulario, conceptos, total_global, total_en_letras, centavos)
    
    # Generar el PDF en memoria
    output_pdf_io = generar_pdf(output_docx_path)
    
    # Enviar el PDF directamente desde la memoria
    output_pdf_io.seek(0)
    return send_file(
        output_pdf_io,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"recibo_{recibo.id}.pdf"
    )

# Comando de Flask CLI para crear un usuario
@app.cli.command('create-user')
def create_user():
    """Crear un usuario administrador."""
    import getpass
    username = input("Nombre de usuario: ")
    password = getpass.getpass("Contraseña: ")
    confirm_password = getpass.getpass("Confirmar contraseña: ")

    if password != confirm_password:
        print("Las contraseñas no coinciden. Intente de nuevo.")
        return

    if User.query.filter_by(username=username).first():
        print("El usuario ya existe.")
        return

    new_user = User(username=username)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    print("Usuario creado exitosamente.")
    

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
