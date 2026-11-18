#!/usr/bin/env bash
# Deploy production_tracker. Staging first, always:
#   tools/deploy.sh staging      -> preview deploy + alias https://production-tracker-staging.vercel.app
#   tools/deploy.sh production   -> asks for confirmation, then promotes the current code to production
set -euo pipefail
cd "$(dirname "$0")/.."
SCOPE=novaninesx
STAGING_ALIAS=production-tracker-staging.vercel.app

DJANGO_DEBUG=1 python3 manage.py check

case "${1:-staging}" in
  staging)
    url=$(vercel deploy --yes --scope "$SCOPE" 2>/dev/null | grep -Eo 'https://production-tracker-[a-z0-9-]+\.vercel\.app' | head -1)
    [ -n "$url" ] || { echo "Deploy failed: run 'vercel deploy --scope $SCOPE' to see why"; exit 1; }
    vercel alias set "$url" "$STAGING_ALIAS" --scope "$SCOPE" >/dev/null
    echo "Staging ready: https://$STAGING_ALIAS  (deployment $url)"
    echo "Test it, then run: tools/deploy.sh production"
    ;;
  production)
    echo "This publishes the current code to PRODUCTION (live records database)."
    echo "Has this exact version been tested on https://$STAGING_ALIAS ? Type 'publish' to continue:"
    read -r answer
    [ "$answer" = "publish" ] || { echo "Cancelled."; exit 1; }
    vercel deploy --prod --yes --scope "$SCOPE"
    ;;
  *) echo "usage: tools/deploy.sh staging|production"; exit 1 ;;
esac
