#!/bin/bash

# Ativa o ambiente do python
source .venv/bin/activate

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Útil para rodar junto com o cloudflared para rodar na WEB
cloudflared tunnel run --token "$CLOUDFLARED_TOKEN" > /dev/null 2>&1 &
CLOUDFLARED_PID=$!

uvicorn main:app --host localhost --port 5000

kill $CLOUDFLARED_PID