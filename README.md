# Acervo de História

App web (FastAPI) para buscar imagens em acervos de museus de acesso aberto
(Wikimedia Commons, The Met, Smithsonian) e salvar as escolhidas numa biblioteca
pessoal com tags, notas e coleções. Interface em português.

No ar: https://acervo-historia-matostf.fly.dev

## Rodar localmente

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env            # opcional; sem APP_PASSWORD o login é desativado
DATA_DIR=./data ./.venv/bin/uvicorn app.main:app --reload --port 8099
```

Abra http://127.0.0.1:8099

## Deploy (Fly.io)

```bash
fly deploy
```

Os secrets `SECRET_KEY` e `APP_PASSWORD` já estão configurados na Fly.
Para habilitar a fonte Smithsonian: `fly secrets set SMITHSONIAN_API_KEY=...`

Mais detalhes de arquitetura em [CLAUDE.md](CLAUDE.md).
