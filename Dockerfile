FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala FFmpeg, Node.js, npm e curl
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg nodejs npm curl ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Baixa e instala o servidor de PO Token diretamente via pacote release (sem git clone)
RUN mkdir -p /opt/bgutil-pot && \
    curl -L https://github.com -o /tmp/server.tar.gz && \
    tar -xzf /tmp/server.tar.gz -C /opt/bgutil-pot && \
    rm /tmp/server.tar.gz && \
    cd /opt/bgutil-pot/server && \
    npm install --omit=dev

# Instala as dependências Python, o yt-dlp atualizado e o plugin conector
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -U yt-dlp bgutil-ytdlp-pot-provider

COPY . .

# Inicia o servidor de PO Token em segundo plano e o Uvicorn na porta do Render
CMD ["sh", "-c", "node /opt/bgutil-pot/server/build/main.js & uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 300"]
