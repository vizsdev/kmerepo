# production_tracker (KME Tracker) — Claude Code context

Django 5 app for manufacturing production records (serials, MACs, pallets), CSV/XLSX/JSON import/export,
custom columns. Sister project of `~/Project/kaon_tracker` and deployed the same way (see DEPLOY_VERCEL.md).

## Deploy rule (mandatory)
1. Every change goes to **staging first**: `tools/deploy.sh staging` -> https://production-tracker-staging.vercel.app
2. Then **stop and ask the user** to test staging and confirm before production. Never run
   `tools/deploy.sh production` or `vercel deploy --prod` without the user's explicit go-ahead for that release.
3. New migrations: run on the staging DB first; production DB only after the user confirms (back it up first).

## Environments
- Production: https://production-tracker-six-omega.vercel.app, Neon `production-tracker-db` (`DATABASE_URL`).
- Staging (Vercel Preview, behind Vercel login): Neon `production-tracker-staging-db` (`STAGING_DATABASE_URL`).
  settings.py refuses to start a preview without it, so staging can never touch production records.
- Sidebar link to kaon_tracker via `PROJECT_TRACKER_URL` (prod -> kaon prod, preview -> kaon staging).

## Local
```bash
source .venv/bin/activate && pip install -r requirements.txt
DJANGO_DEBUG=1 python manage.py migrate && DJANGO_DEBUG=1 python manage.py runserver
```
