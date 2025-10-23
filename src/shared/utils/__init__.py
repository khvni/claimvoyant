"""
Utility functions for Claimvoyant Lambda functions.
"""

import json
from typing import Any, Dict


def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a standardized API Gateway response.

    Args:
        status_code: HTTP status code
        body: Response body dictionary

    Returns:
        API Gateway compatible response dictionary
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }


def get_secret(secret_name: str, secrets_manager_client) -> Dict[str, Any]:
    """
    Retrieve a secret from AWS Secrets Manager.

    Args:
        secret_name: Name of the secret
        secrets_manager_client: Boto3 Secrets Manager client

    Returns:
        Dictionary containing secret data
    """
    secret_response = secrets_manager_client.get_secret_value(SecretId=secret_name)
    return json.loads(secret_response["SecretString"])
