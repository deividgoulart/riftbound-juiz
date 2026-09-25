# API do Juiz Riftbound (api/main.py) pro Hugging Face Spaces (Docker, plano grátis: 2 CPUs e 16 GB de RAM).
# Também roda em qualquer lugar com Docker:
#   docker build -t juiz-riftbound . && docker run -p 7860:7860 --env-file .env juiz-riftbound
FROM python:3.12-slim

# git: o juiz baixa o FAQ com git (juiz/baixar_faq.py)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# O Hugging Face roda o contêiner com o usuário 1000: a pasta do app precisa ser dele.
RUN useradd -m -u 1000 juiz
USER juiz
ENV HOME=/home/juiz PATH=/home/juiz/.local/bin:$PATH PYTHONUNBUFFERED=1 HF_HOME=/home/juiz/.cache/huggingface
WORKDIR /home/juiz/app

COPY --chown=juiz requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=juiz . .

EXPOSE 7860
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
