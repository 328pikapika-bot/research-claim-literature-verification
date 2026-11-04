#!/bin/bash
set -e

export BACKEND_HOST="${BACKEND_HOST:-backend}"
export BACKEND_PORT="${BACKEND_PORT:-38004}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"

echo "============================================"
echo " ClaimConsistency Frontend Nginx"
echo " Backend: ${BACKEND_URL}"
echo " Listen:  38005"
echo "============================================"

envsubst '${BACKEND_HOST} ${BACKEND_PORT}' \
    < /etc/nginx/templates/nginx.conf.template \
    > /etc/nginx/conf.d/nginx.conf

rm -f /etc/nginx/conf.d/default.conf
