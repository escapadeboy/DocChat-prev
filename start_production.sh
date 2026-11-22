#!/bin/bash
set -e

echo "================================"
echo "DocChat Production Server Startup"
echo "================================"
echo ""

# Change to the DocChat directory
cd "$(dirname "$0")"

echo "Building frontend..."
cd frontend
npm run build
cd ..

echo ""
echo "Frontend build complete!"
echo ""

echo "Starting production server on port 8000..."
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

echo ""
echo "Server stopped."

