# Deploying production_tracker to Vercel
Set up the same way as kaon_tracker: Vercel team `novaninesx` (Hobby), project `production-tracker`, Django zero-config
(`vercel.json` pins `framework: django`, region `fra1`), Neon Postgres for the records. Staging = Vercel Preview.

| | Production | Staging |
|---|---|---|
| URL | https://production-tracker-six-omega.vercel.app | https://production-tracker-staging.vercel.app (behind Vercel login) |
| Vercel env | production (+ development) | preview |
| Database | Neon `production-tracker-db` (fra1) -> `DATABASE_URL` | Neon `production-tracker-staging-db` (fra1) -> `STAGING_DATABASE_URL` |

Safety: settings.py ignores `DATABASE_URL` when `VERCEL_ENV=preview` and refuses to start without `STAGING_DATABASE_URL`,
so a preview can never write to the production records. Unlike kaon_tracker, the production DB is NOT connected to Preview.

Env vars: `DJANGO_SECRET_KEY` (sensitive), `DJANGO_DEBUG=0`, `PROJECT_TRACKER_URL` (link to kaon_tracker; prod -> kaon prod,
preview -> kaon staging). No file store is needed: imports are parsed in memory, nothing is saved to disk.

## Deploy: staging first, production only after sign-off
```bash
tools/deploy.sh staging      # preview deploy + alias production-tracker-staging.vercel.app
# test staging (login, records list, import a small file, export)
tools/deploy.sh production   # asks you to type 'publish', then deploys to production
```
Preview also has `DJANGO_ALLOWED_HOSTS`/`DJANGO_CSRF_TRUSTED_ORIGINS` = the staging alias.
Staging DB holds only the user account (no records); copy sample data there if a test needs it.
Imports: Vercel caps a request at 4.5 MB, so split bigger CSV/XLSX files before uploading.

## Management commands against a hosted DB
```bash
vercel env pull /tmp/e.env --environment production --yes      # or preview
export DATABASE_URL="$(grep '^DATABASE_URL_UNPOOLED=' /tmp/e.env | cut -d= -f2- | tr -d '"')"   # staging: STAGING_DATABASE_URL_UNPOOLED
DJANGO_DEBUG=1 python manage.py migrate          # or createsuperuser, seed_columns
rm /tmp/e.env
```
New migrations: run them on staging first, back up production, migrate production, then `vercel deploy --prod` straight away.
