#!/bin/sh
# Start the images for the commit that's checked out, then tidy up. The deploy workflow
# checks out the commit first and then runs this, so the newest version of this script is
# the one that runs. By hand:
#   git fetch && git checkout --detach origin/main && sh deploy/update.sh
set -eu
cd "$(dirname "$0")/.."
# CI tags every image sha-<first 7 of the commit>; pin to exactly those
export TAG="sha-$(git rev-parse --short=7 HEAD)"
echo "Deploying $TAG"
docker compose pull --quiet
docker compose up -d --remove-orphans
docker image prune -f > /dev/null
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
