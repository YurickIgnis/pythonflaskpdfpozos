# Dockerfile

FROM python:3.12.7-slim

# Instala dependencias del sistema necesarias, incluyendo LibreOffice, libpq-dev y gcc para PostgreSQL
RUN apt-get update && apt-get install -y \
    libreoffice \
    libpq-dev \
    gcc \
    bash \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Establece el directorio de trabajo
WORKDIR /app

# Copia los archivos del proyecto
COPY . .

# Instala las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia wait-for-it.sh al contenedor
COPY wait-for-it.sh /wait-for-it.sh
RUN chmod +x /wait-for-it.sh

# Expones el puerto 5000 para Flask
EXPOSE 5000

# Comando para ejecutar la aplicación Flask después de esperar a que PostgreSQL esté listo
CMD ["./wait-for-it.sh", "db:5432", "--", "python", "app.py"]
