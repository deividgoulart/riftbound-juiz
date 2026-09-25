# API do Juiz Riftbound (api/main.py) pro Render (plano grátis: 512 MB de memória; veja o README).
# Também roda em qualquer lugar com Docker:
#   docker build -t juiz-riftbound . && docker run -p 8000:8000 --env-file .env juiz-riftbound
FROM python:3.12-slim

# git: o juiz baixa o FAQ com git (juiz/baixar_faq.py)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

RUN useradd -m juiz
USER juiz
ENV PATH=/home/juiz/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/juiz/app

COPY --chown=juiz requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=juiz . .

# O Render diz a porta em $PORT; fora dele, 8000.
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips "*"
