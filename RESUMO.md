# Resumo do Projeto — Acervo de História

## O que é

Aplicação web (FastAPI) para uma professora de História **buscar imagens em
acervos de museus de acesso aberto**, pré-visualizar resultados e **salvar as
escolhidas numa biblioteca pessoal** (arquivos em disco + metadados em SQLite),
organizadas por **tags, anotações e coleções**. Interface em português.

- **No ar:** https://acervo-historia-matostf.fly.dev
- **Hospedagem:** Fly.io (app `acervo-historia-matostf`, região `gru`), com
  volume persistente `acervo_data` montado em `/data`.

## Como rodar localmente

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
DATA_DIR=./data ./.venv/bin/uvicorn app.main:app --reload --port 8099
# Abra http://127.0.0.1:8099
```
Sem `APP_PASSWORD` e sem contas cadastradas, a autenticação fica **desligada**
(conveniência para desenvolvimento).

## Arquitetura (resumo)

| Arquivo | Papel |
|---------|-------|
| `app/main.py` | Rotas FastAPI, autenticação (sessão por cookie) e lógica do app. |
| `app/auth.py` | Hash de senha (PBKDF2), comparação em tempo constante, tokens de redefinição e envio de e-mail por SMTP. |
| `app/db.py` | Acesso a SQLite (`library.db`): imagens, tags, coleções, usuários e tokens de reset. |
| `app/sources/` | Um módulo por fonte (`wikimedia`, `met`, `smithsonian`; `artic` desativada). |
| `app/static/` | Front sem build: busca, biblioteca, tema escuro. |
| `tests/test_smoke.py` | Smoke test (sobe o app em processo e exercita as rotas de auth). |
| `.github/workflows/ci.yml` | CI: instala deps, compila os fontes e roda o smoke test. |

## Estado atual (o que foi feito)

### 1. Sistema de contas de usuário + recuperação de senha *(PR #1 — mesclado)*
- Registro aberto (e-mail/senha), login por conta, e fluxo de **recuperação de
  senha** com token de uso único enviado por **SMTP**.
- Biblioteca **compartilhada** (sem isolamento por usuário).
- `APP_PASSWORD` liga/desliga a autenticação e funciona como **senha mestra**.
- Senhas com **PBKDF2-HMAC-SHA256** (apenas biblioteca padrão, sem dependências
  novas).

### 2. Correções de segurança + CI *(PR #2 — aberto, CI verde)*
Da revisão de código, **10 itens resolvidos**:

| # | Correção |
|---|----------|
| 1 | Link de redefinição **nunca** vai na resposta HTTP (era account takeover sem SMTP); agora só no log do servidor. |
| 2 | Link montado a partir de `APP_BASE_URL`; avisa no log se cair no Host da requisição (Host-poisoning). |
| 3 | Autenticação exigida quando há `APP_PASSWORD` **ou** qualquer conta — a biblioteca não fica pública se a senha for esvaziada. |
| 4 | Redefinir senha **invalida todas as sessões ativas** (via `session_version`). |
| 5 | Front redireciona para `/login` em qualquer 401 (não mostra mais app vazio). |
| 6 | Comparação de tempo constante na senha mestra. |
| 7 | `/forgot` envia o e-mail em *background* → tempo de resposta uniforme (anti-enumeração). |
| 8 | Reset atômico: token consumido junto com a troca de senha. |
| 9 | `password_resets` faz *prune* de tokens usados/expirados (não cresce sem limite). |
| 10 | Limpezas: query redundante removida, tipos da sessão consistentes, dedup. |

Adicionado também: **CI** (GitHub Actions) + **smoke test** com 18 verificações,
e uma **migração idempotente** para a coluna `session_version`.

## Pendências / próximos passos

1. **Mesclar o PR #2** (`claude/auth-security-fixes`) em `master`.
2. **Configurar o SMTP** (recomendado: Gmail com "senha de app") + `APP_BASE_URL`
   nos *secrets* da Fly, para os e-mails de recuperação serem enviados de fato:
   ```bash
   fly secrets set \
     APP_BASE_URL=https://acervo-historia-matostf.fly.dev \
     SMTP_HOST=smtp.gmail.com SMTP_PORT=587 \
     SMTP_USER=seu-email@gmail.com SMTP_PASSWORD="<senha de app>" \
     "SMTP_FROM=Acervo de História <seu-email@gmail.com>"
   ```
3. **Deploy:** `git checkout master && git pull && fly deploy`.

> Enquanto o SMTP não estiver configurado, a recuperação de senha funciona, mas o
> link só é **registrado no log do servidor** (`fly logs`) — nunca exibido na
> página, por segurança.

## Variáveis de ambiente

Veja `.env.example`. Principais: `APP_PASSWORD`, `SECRET_KEY`, `DATA_DIR`,
`APP_BASE_URL`, `SMTP_*` (envio de e-mail) e `SMITHSONIAN_API_KEY` (habilita a
fonte Smithsonian).
