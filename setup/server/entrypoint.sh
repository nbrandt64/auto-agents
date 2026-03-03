#!/bin/sh
set -e

echo "Waiting for DynamoDB Local..."
while ! python3 -c "
import boto3, sys
try:
    client = boto3.client('dynamodb',
        endpoint_url='${DYNAMODB_ENDPOINT:-http://dynamodb-local:8000}',
        region_name='${AWS_REGION:-us-east-1}',
        aws_access_key_id='local',
        aws_secret_access_key='local')
    client.list_tables()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    sleep 1
done
echo "DynamoDB Local is ready."

echo "Creating tables..."
python3 create_tables.py

echo "Starting comms server..."
exec uvicorn server:app --host 0.0.0.0 --port 8000
