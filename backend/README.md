# Teacher Workspace Backend

This Django service runs in parallel with the existing bot.

## Local setup

1. Start Redis:

```bash
docker compose -f docker-compose.miniapp.yml up -d
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

3. Configure env vars from `backend/.env.example`.

4. Start ASGI server:

```bash
python manage.py runserver 127.0.0.1:8000
```

To mirror the current legacy bot messages into the Mini App, set:

```bash
MINIAPP_BRIDGE_ENABLED=1
```
