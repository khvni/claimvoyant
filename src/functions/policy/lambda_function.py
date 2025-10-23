"""
Policy Agent Lambda Function

Queries Weaviate PolicyDocuments collection to retrieve relevant policy details
based on the claim information.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict

import boto3

# AWS clients
dynamodb = boto3.resource("dynamodb")
secrets_manager = boto3.client("secretsmanager")

# DynamoDB table
audit_log_table = dynamodb.Table("AuditLog")


def get_weaviate_client():
    """Initialize Weaviate client with credentials from Secrets Manager."""
    try:
        import weaviate
        from weaviate.classes.init import Auth

        secret_response = secrets_manager.get_secret_value(SecretId="claimvoyant/weaviate")
        secret_data = json.loads(secret_response["SecretString"])

        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=secret_data["url"],
            auth_credentials=Auth.api_key(secret_data["api_key"]),
        )

        return client
    except Exception as e:
        print(f"Error connecting to Weaviate: {str(e)}")
        raise


def query_policy(policy_number: str) -> Dict[str, Any]:
    """Query Weaviate for policy details."""
    try:
        weaviate_client = get_weaviate_client()
        policies = weaviate_client.collections.get("PolicyDocuments")

        # Hybrid search (combines vector and keyword search)
        result = policies.query.hybrid(query=policy_number, limit=1)

        weaviate_client.close()

        if result.objects:
            policy_data = result.objects[0].properties
            return {
                "found": True,
                "policy_id": policy_data.get("policy_id"),
                "coverage_type": policy_data.get("coverage_type"),
                "deductible": policy_data.get("deductible"),
                "coverage_limit": policy_data.get("coverage_limit"),
                "filing_deadline_days": policy_data.get("filing_deadline_days"),
                "content": policy_data.get("content"),
            }
        else:
            return {"found": False, "error": "Policy not found"}

    except Exception as e:
        print(f"Error querying policy: {str(e)}")
        return {"found": False, "error": str(e)}


def lambda_handler(event, context):
    """Lambda handler for Policy Agent."""
    try:
        print(f"Event: {json.dumps(event)}")

        claim_id = event.get("claim_id")
        entities = event.get("entities", {})

        # Extract policy number from entities or use default for testing
        policy_number = entities.get("policy_number") or "AUTO-001"

        print(f"Querying policy: {policy_number} for claim {claim_id}")

        # Query Weaviate for policy details
        policy_data = query_policy(policy_number)

        # Log to DynamoDB AuditLog
        log_id = f"{claim_id}-policy"
        audit_log_table.put_item(
            Item={
                "log_id": log_id,
                "timestamp": datetime.now().isoformat(),
                "claim_id": claim_id,
                "agent": "policy",
                "action": "query_policy",
                "status": "success" if policy_data.get("found") else "not_found",
                "details": json.dumps(
                    {
                        "policy_number": policy_number,
                        "found": policy_data.get("found"),
                    }
                ),
            }
        )

        # Return result for Step Functions
        return {
            "statusCode": 200,
            "claim_id": claim_id,
            "policy_number": policy_number,
            "policy_data": policy_data,
            "entities": entities,
            "extracted_data": event.get("extracted_data"),
        }

    except Exception as e:
        print(f"Error in Policy Agent: {str(e)}")
        import traceback

        traceback.print_exc()

        return {"statusCode": 500, "error": str(e)}
