"""
Configuration management for Claimvoyant.
"""

import os


class Config:
    """Central configuration class."""

    # AWS Configuration
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    BUCKET_PREFIX = os.environ.get("BUCKET_PREFIX", "claimvoyant")

    # DynamoDB Tables
    CLAIMS_TABLE = os.environ.get("CLAIMS_TABLE", "Claims")
    AUDIT_LOG_TABLE = os.environ.get("AUDIT_LOG_TABLE", "AuditLog")

    # Step Functions
    STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")

    # Weaviate (from Secrets Manager)
    WEAVIATE_SECRET_NAME = "claimvoyant/weaviate"

    # Bedrock
    BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
