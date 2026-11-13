FROM python:3.11-slim

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

# pip ne sert qu'à construire l'image. Celui de l'image de base (pip 24.0 de
# python:3.11-slim, mesuré le 2026-11-13) porte 12 vulnérabilités connues,
# en deux exemplaires : le paquet installé et la roue gardée par
# ensurepip, qui ne sert qu'à `python -m venv`. Rien ne les appelle au
# démarrage : entrypoint.sh lance dvc ; Streamlit, l'API et `mlflow server`
# tournent sans pip. Dernière instruction RUN, après toutes les installations.
RUN pip uninstall -y pip \
    && rm -f /usr/local/lib/python3*/ensurepip/_bundled/pip-*.whl

EXPOSE 8000 8501 5000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["streamlit", "run", "streamlit_app.py", "--server.address", "0.0.0.0"]
