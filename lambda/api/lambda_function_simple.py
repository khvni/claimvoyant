"""
Simplified API Lambda Function without FastAPI dependencies.
Uses pure Python with boto3 only.
"""

import json
import os
from datetime import datetime

import boto3

# AWS clients
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
stepfunctions = boto3.client("stepfunctions")

# DynamoDB tables
claims_table = dynamodb.Table("Claims")
audit_log_table = dynamodb.Table("AuditLog")

# Environment variables
BUCKET_PREFIX = os.environ.get("BUCKET_PREFIX", "claimvoyant")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")


def response(status_code, body):
    """Create API Gateway response."""
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


def handler(event, context):
    """Lambda handler for API requests."""
    try:
        print(f"Event: {json.dumps(event)}")

        # Parse request
        http_method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
        raw_path = event.get("rawPath", "/")

        # Strip stage prefix if present (e.g., /prod/ -> /)
        path = raw_path
        if path.startswith("/prod/"):
            path = path[5:]  # Remove '/prod'
        elif path.startswith("/prod"):
            path = path[5:] or "/"

        # Ensure path starts with /
        if not path.startswith("/"):
            path = "/" + path

        # Route handling
        if path == "/" and http_method == "GET":
            return handle_health_check()

        elif path == "/api/v1/claims" and http_method == "GET":
            return handle_list_claims()

        elif path.startswith("/api/v1/claims/") and http_method == "GET":
            claim_id = path.split("/")[-1]
            return handle_get_claim(claim_id)

        elif path == "/api/v1/claims/upload" and http_method == "POST":
            return handle_upload_claim(event)

        else:
            return response(404, {"error": "Not found", "path": path, "method": http_method})

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback

        traceback.print_exc()
        return response(500, {"error": str(e)})


def handle_health_check():
    """Health check endpoint."""
    return response(
        200,
        {
            "status": "ok",
            "service": "Claimvoyant API",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
        },
    )


def handle_list_claims():
    """List recent claims."""
    try:
        scan_response = claims_table.scan(Limit=10)
        items = scan_response.get("Items", [])

        # Group by claim_id and keep latest version
        claims_dict = {}
        for item in items:
            claim_id = item["claim_id"]
            if claim_id not in claims_dict:
                claims_dict[claim_id] = item
            else:
                if item["version"] > claims_dict[claim_id]["version"]:
                    claims_dict[claim_id] = item

        # Format response
        claims = []
        for claim in claims_dict.values():
            decision_data = json.loads(claim.get("decision_data", "{}"))
            claims.append(
                {
                    "claim_id": claim["claim_id"],
                    "version": claim["version"],
                    "status": claim["status"],
                    "timestamp": claim["timestamp"],
                    "decision": decision_data.get("decision"),
                    "confidence": decision_data.get("confidence"),
                }
            )

        claims.sort(key=lambda x: x["timestamp"], reverse=True)

        return response(200, {"claims": claims})

    except Exception as e:
        return response(500, {"error": str(e)})


def handle_get_claim(claim_id):
    """Get claim details."""
    try:
        query_response = claims_table.query(
            KeyConditionExpression="claim_id = :cid",
            ExpressionAttributeValues={":cid": claim_id},
            ScanIndexForward=False,
            Limit=1,
        )

        items = query_response.get("Items", [])

        if not items:
            return response(
                200,
                {
                    "claim_id": claim_id,
                    "status": "processing",
                    "message": "Claim is being processed",
                },
            )

        claim = items[0]

        # Parse JSON fields
        decision_data = json.loads(claim.get("decision_data", "{}"))
        entities = json.loads(claim.get("entities", "{}"))

        return response(
            200,
            {
                "claim_id": claim_id,
                "version": claim.get("version"),
                "status": claim.get("status"),
                "timestamp": claim.get("timestamp"),
                "decision": decision_data.get("decision"),
                "reasoning": decision_data.get("reasoning"),
                "confidence": decision_data.get("confidence"),
                "estimated_payout": decision_data.get("estimated_payout"),
                "entities": entities,
            },
        )

    except Exception as e:
        return response(500, {"error": str(e)})


def handle_upload_claim(event):
    """Handle claim upload (simplified - expects base64 encoded file)."""
    try:
        # Parse body
        body = event.get("body", "")
        if event.get("isBase64Encoded"):
            import base64

            body = base64.b64decode(body).decode("utf-8")

        data = json.loads(body) if body else {}

        # Generate claim ID
        claim_id = f"CLAIM-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # For now, just trigger Step Functions with dummy data
        # In production, this would handle actual file uploads

        if STATE_MACHINE_ARN:
            execution_input = {
                "claim_id": claim_id,
                "bucket": f"{BUCKET_PREFIX}-raw-claims",
                "key": f"{claim_id}/test.txt",
            }

            stepfunctions.start_execution(
                stateMachineArn=STATE_MACHINE_ARN,
                name=f"{claim_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                input=json.dumps(execution_input),
            )

        return response(
            200,
            {
                "claim_id": claim_id,
                "status": "processing",
                "message": "Claim uploaded successfully",
            },
        )

    except Exception as e:
        return response(500, {"error": str(e)})
