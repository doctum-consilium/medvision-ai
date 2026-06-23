FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Point d'entrée : récupère les artefacts DVC depuis S3 avant de démarrer l'app
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000 8501 5000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["streamlit", "run", "streamlit_app.py", "--server.address", "0.0.0.0"]
