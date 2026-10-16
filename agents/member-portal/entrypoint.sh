#!/bin/sh
# One image, three modes. The Deployment selects the mode with args: ["portal-api"|"portal-consumer"|"loadgen"].
set -e
case "${1:-portal-api}" in
  portal-api)      exec python -m portal.api ;;
  portal-consumer) exec python -m portal.consumer ;;
  loadgen)         exec python -m portal.loadgen ;;
  *)               exec "$@" ;;
esac
