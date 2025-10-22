"""
API Lambda Function

FastAPI REST API for Claimvoyant frontend.
Deployed via Mangum adapter for AWS Lambda.
"""

import json
import os
from datetime import datetime
from typing import List

import boto3
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

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

# FastAPI app
app = FastAPI(
    title="Claimvoyant API",
    description="Multi-agent auto claims processing system",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Claimvoyant API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/v1/claims/upload")
async def upload_claim(files: List[UploadFile] = File(...)):
    """Upload claim documents and trigger processing workflow."""
    try:
        # Generate claim ID
        claim_id = f"CLAIM-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        uploaded_files = []

        # Upload files to S3
        for file in files:
            key = f"{claim_id}/{file.filename}"
            content = await file.read()

            s3.put_object(
                Bucket=f"{BUCKET_PREFIX}-raw-claims",
                Key=key,
                Body=content,
                ContentType=file.content_type or "application/octet-stream",
            )

            uploaded_files.append(
                {
                    "filename": file.filename,
                    "s3_key": key,
                    "size": len(content),
                }
            )

        # Trigger Step Functions workflow
        if STATE_MACHINE_ARN:
            execution_input = {
                "claim_id": claim_id,
                "bucket": f"{BUCKET_PREFIX}-raw-claims",
                "key": uploaded_files[0]["s3_key"],  # Process first file
            }

            stepfunctions.start_execution(
                stateMachineArn=STATE_MACHINE_ARN,
                name=f"{claim_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                input=json.dumps(execution_input),
            )

        return {
            "claim_id": claim_id,
            "status": "processing",
            "files": uploaded_files,
            "message": "Claim uploaded successfully and processing started",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/claims/{claim_id}")
def get_claim(claim_id: str):
    """Get claim status and details."""
    try:
        # Query DynamoDB for latest claim version
        response = claims_table.query(
            KeyConditionExpression="claim_id = :cid",
            ExpressionAttributeValues={":cid": claim_id},
            ScanIndexForward=False,  # Descending order (latest first)
            Limit=1,
        )

        items = response.get("Items", [])

        if not items:
            # Check if claim is still processing (not in Claims table yet)
            return {
                "claim_id": claim_id,
                "status": "processing",
                "message": "Claim is being processed",
            }

        claim = items[0]

        # Parse JSON fields
        decision_data = json.loads(claim.get("decision_data", "{}"))
        entities = json.loads(claim.get("entities", "{}"))

        return {
            "claim_id": claim_id,
            "version": claim.get("version"),
            "status": claim.get("status"),
            "timestamp": claim.get("timestamp"),
            "decision": decision_data.get("decision"),
            "reasoning": decision_data.get("reasoning"),
            "confidence": decision_data.get("confidence"),
            "estimated_payout": decision_data.get("estimated_payout"),
            "entities": entities,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/claims/{claim_id}/audit")
def get_claim_audit_log(claim_id: str):
    """Get audit log for a claim."""
    try:
        # Query DynamoDB AuditLog for all logs related to claim
        response = audit_log_table.query(
            IndexName="claim_id-index",  # Requires GSI on claim_id
            KeyConditionExpression="claim_id = :cid",
            ExpressionAttributeValues={":cid": claim_id},
            ScanIndexForward=True,  # Ascending order (chronological)
        )

        logs = response.get("Items", [])

        # Parse details JSON
        for log in logs:
            if "details" in log:
                log["details"] = json.loads(log["details"])

        return {"claim_id": claim_id, "audit_logs": logs}

    except Exception as e:
        # If GSI doesn't exist, scan table (inefficient, for demo only)
        try:
            response = audit_log_table.scan(
                FilterExpression="claim_id = :cid",
                ExpressionAttributeValues={":cid": claim_id},
            )

            logs = response.get("Items", [])

            for log in logs:
                if "details" in log:
                    log["details"] = json.loads(log["details"])

            return {"claim_id": claim_id, "audit_logs": logs}

        except Exception as scan_error:
            raise HTTPException(status_code=500, detail=str(scan_error))


@app.get("/api/v1/claims")
def list_claims(limit: int = 10):
    """List recent claims."""
    try:
        # Scan Claims table (in production, use GSI on timestamp)
        response = claims_table.scan(Limit=limit)

        items = response.get("Items", [])

        # Group by claim_id and keep latest version
        claims_dict = {}
        for item in items:
            claim_id = item["claim_id"]
            if claim_id not in claims_dict:
                claims_dict[claim_id] = item
            else:
                # Keep latest version
                if item["version"] > claims_dict[claim_id]["version"]:
                    claims_dict[claim_id] = item

        # Parse JSON fields and format response
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

        # Sort by timestamp descending
        claims.sort(key=lambda x: x["timestamp"], reverse=True)

        return {"claims": claims[:limit]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Mangum handler for AWS Lambda
handler = Mangum(app)


# For local testing with uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
