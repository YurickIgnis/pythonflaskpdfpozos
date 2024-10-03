import csv
import os
import tempfile
from flask import Flask, render_template, request, jsonify, send_file, make_response, flash, redirect, url_for
from docxtpl import DocxTemplate
from datetime import datetime
from num2words import num2words
import subprocess
import random
import pytz

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Ruta para los recursos externos
def get_resource_path(relative_path):
    base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Rutas del CSV y la plantilla DOCX
CSV_PATH = get_resource_path('codigos.csv')
DOCX_TEMPLATE_PATH = get_resource_path('170000.docx')

# Función para leer el archivo CSV
def leer_codigos_postales():
    codigos_postales = {}
    with open(CSV_PATH, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        for row in reader:
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
    return num2words(num, lang='es').upper()

# Función para generar el folio
def generar_folio(fecha):
    año = fecha.year
    mes = fecha.strftime('%B')[0].upper()
    random_digits = f"{random.randint(1000, 9999)}"
    return f"{año}{mes}{random_digits}"

@app.route('/')
def index():
    return render_template('index.html')

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
def generate_docx():
    try:
        # Validar que todos los campos requeridos estén presentes
        fecha_seleccionada = request.form['fecha']
        if not fecha_seleccionada:
            raise ValueError("La fecha es requerida")
        fecha_seleccionada = datetime.strptime(fecha_seleccionada, '%Y-%m-%d')

        # Validar otros campos requeridos
        if not request.form['contribuyente']:
            raise ValueError("El nombre del contribuyente es requerido")
        if not request.form['calle']:
            raise ValueError("La calle es requerida")
        if not request.form['colonia']:
            raise ValueError("La colonia es requerida")
        if not request.form['municipio']:
            raise ValueError("El municipio es requerido")
        if not request.form['dependencia']:
            raise ValueError("La dependencia es requerida")

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
        for concepto, valor, cantidad, total in zip(request.form.getlist('concepto[]'),
                                                    request.form.getlist('valor[]'),
                                                    request.form.getlist('cantidad[]'),
                                                    request.form.getlist('total[]')):
            if not concepto or not valor or not cantidad or not total:
                raise ValueError("Todos los campos de concepto son requeridos")
            conceptos.append({
                'concepto': concepto.upper(),
                'valor': f"${float(valor):.2f}",
                'cantidad': int(cantidad),
                'total': f"${float(total):.2f}"
            })

        # Calcular totales
        total_global = sum(float(c['total'][1:]) for c in conceptos)
        centavos = int(total_global % 1 * 100)
        total_en_letras = numero_a_letras(int(total_global))

        # Generar el documento
        output_docx = generar_docx(datos_formulario, conceptos, total_global, total_en_letras, centavos)

        # Generar el PDF
        output_pdf = generar_pdf(output_docx)

        # Enviar el archivo para abrir en el navegador
        response = send_file(output_pdf, mimetype='application/pdf', as_attachment=False)
        response.headers['Content-Disposition'] = 'inline; filename="document.pdf"'
        return response

    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('index'))

    except Exception as e:
        flash('Error al generar el documento. Intente de nuevo.', 'error')
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
    temp_dir = tempfile.gettempdir()
    output_docx = os.path.join(temp_dir, f"output_{int(datetime.now().timestamp())}.docx")
    doc.render(contexto)
    doc.save(output_docx)

    return output_docx

def generar_pdf(output_docx):
    temp_dir = tempfile.gettempdir()
    output_pdf = os.path.join(temp_dir, f"output_{int(datetime.now().timestamp())}.pdf")
    
    try:
        subprocess.run([
            "soffice", 
            "--headless", 
            "--convert-to", "pdf", 
            "--outdir", temp_dir, 
            output_docx
        ], check=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Error al convertir DOCX a PDF: {e}")

    return output_pdf

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
