FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala FFmpeg, Node.js e Git
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg nodejs npm git ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala o provedor automático de PO Token (Node.js) para liberar formatos no YouTube
RUN git clone --single-branch --branch 1.2.2 https://github.com /opt/bgutil-pot && \
    cd /opt/bgutil-pot/server && \
    npm install && \
    npx tsc

# Instala as dependências Python, o yt-dlp atualizado e o plugin conector do PO Token
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -U yt-dlp bgutil-ytdlp-pot-provider

COPY . .

# Inicia o servidor de PO Token em segundo plano e o Uvicorn na porta do Render
CMD ["sh", "-c", "node /opt/bgutil-pot/server/build/main.js & uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 300"]
