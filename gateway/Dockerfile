FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1
ENV GATEWAY_DB_PATH=/babytime/gateway.db
ENV GATEWAY_CONFIG_PATH=/babytime/config.json
ENV GATEWAY_TOKEN=
ENV GATEWAY_BIND_HOST=0.0.0.0
ENV GATEWAY_BIND_PORT=8080

EXPOSE 8080
VOLUME ["/babytime"]

# --no-proxy-headers: the app resolves X-Forwarded-For itself (config
# `trusted_proxies`), so uvicorn must leave request.client as the real TCP
# peer instead of rewriting it from forwarded headers it half-trusts.
CMD ["sh", "-c", "uvicorn app.main:app --host ${GATEWAY_BIND_HOST} --port ${GATEWAY_BIND_PORT} --no-proxy-headers"]
