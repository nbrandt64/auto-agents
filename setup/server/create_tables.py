#!/usr/bin/env python3
"""Create DynamoDB tables for the comms API server.

Idempotent — skips tables that already exist.
Configures TTL on both tables.

Usage: python create_tables.py
"""

import os
import sys

import boto3
from botocore.exceptions import ClientError

MESSAGES_TABLE = os.environ.get("DYNAMODB_MESSAGES_TABLE", "comms-messages")
AGENTS_TABLE = os.environ.get("DYNAMODB_AGENTS_TABLE", "comms-agents")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "")


def create_messages_table(client):
    """Create the comms-messages table with a GSI on project."""
    try:
        client.create_table(
            TableName=MESSAGES_TABLE,
            KeySchema=[
                {"AttributeName": "channel", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "channel", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
                {"AttributeName": "project", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "project-index",
                    "KeySchema": [
                        {"AttributeName": "project", "KeyType": "HASH"},
                        {"AttributeName": "sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"Created table: {MESSAGES_TABLE}")
        # Wait for table to become active
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=MESSAGES_TABLE)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"Table already exists: {MESSAGES_TABLE}")
        else:
            raise


def create_agents_table(client):
    """Create the comms-agents table."""
    try:
        client.create_table(
            TableName=AGENTS_TABLE,
            KeySchema=[
                {"AttributeName": "sessionId", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "sessionId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"Created table: {AGENTS_TABLE}")
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=AGENTS_TABLE)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"Table already exists: {AGENTS_TABLE}")
        else:
            raise


def enable_ttl(client, table_name):
    """Enable TTL on the 'ttl' attribute for a table."""
    try:
        client.update_time_to_live(
            TableName=table_name,
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": "ttl",
            },
        )
        print(f"Enabled TTL on: {table_name}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ValidationException" and "already enabled" in str(e).lower():
            print(f"TTL already enabled on: {table_name}")
        else:
            raise


def main():
    print(f"Region: {AWS_REGION}")
    print(f"Messages table: {MESSAGES_TABLE}")
    print(f"Agents table: {AGENTS_TABLE}")
    print()

    kwargs = {"region_name": AWS_REGION}
    if DYNAMODB_ENDPOINT:
        kwargs["endpoint_url"] = DYNAMODB_ENDPOINT
    client = boto3.client("dynamodb", **kwargs)

    create_messages_table(client)
    create_agents_table(client)

    print()
    enable_ttl(client, MESSAGES_TABLE)
    enable_ttl(client, AGENTS_TABLE)

    print()
    print("Done. Tables are ready.")


if __name__ == "__main__":
    main()
