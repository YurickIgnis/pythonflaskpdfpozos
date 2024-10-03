# Dockerfile

FROM python:3.12.7-slim

# Instala dependencias del sistema necesarias, incluyendo LibreOffice
RUN apt-get update && apt-get install -y \
    libreoffice \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Establece el directorio de trabajo
WORKDIR /app

# Copia los archivos del proyecto
COPY . .

# Instala las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Expones el puerto 5000 para Flask
EXPOSE 5000

# Comando para ejecutar la aplicación Flask
CMD ["python", "app.py"]
