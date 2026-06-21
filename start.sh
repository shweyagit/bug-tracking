#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting Docker services..."
docker compose up -d

echo "Starting ngrok tunnel..."
ngrok http 8501 --domain=opisthognathous-amee-digitally.ngrok-free.dev > /tmp/ngrok-bta.log 2>&1 &
NGROK_PID=$!
echo "ngrok PID: $NGROK_PID"

echo "Starting verify service..."
# Kill any existing verify service on port 8502
lsof -ti:8502 | xargs kill -9 2>/dev/null || true
python3 "$SCRIPT_DIR/verify_service.py" > /tmp/verify-service-bta.log 2>&1 &
VERIFY_PID=$!
echo "verify_service PID: $VERIFY_PID"

echo ""
echo "All services running:"
echo "  Dashboard : https://opisthognathous-amee-digitally.ngrok-free.dev"
echo "  Webhook   : http://localhost:8000"
echo "  Verify    : http://localhost:8502  (logs: /tmp/verify-service-bta.log)"
echo "  ngrok     : http://localhost:4040  (logs: /tmp/ngrok-bta.log)"
echo ""
echo "Stop everything: docker compose down && kill $NGROK_PID $VERIFY_PID"
