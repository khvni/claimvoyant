"""
Intake Agent Lambda Function

Extracts data from uploaded claim documents (PDFs and images) using AWS Textract and Rekognition.
Stores extracted data in Weaviate ClaimArtifacts collection and DynamoDB AuditLog.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict

import boto3

# AWS clients
s3 = boto3.client("s3")
textract = boto3.client("textract")
rekognition = boto3.client("rekognition")
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


def extract_text_from_pdf(bucket: str, key: str) -> Dict[str, Any]:
    """Extract text from PDF using AWS Textract."""
    try:
        # Start asynchronous text detection
        response = textract.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
        )

        job_id = response["JobId"]
        print(f"Started Textract job: {job_id}")

        # Wait for job completion (simplified - in production use Step Functions)
        import time

        while True:
            result = textract.get_document_text_detection(JobId=job_id)
            status = result["JobStatus"]

            if status == "SUCCEEDED":
                # Extract all text blocks
                blocks = result.get("Blocks", [])
                extracted_text = ""

                for block in blocks:
                    if block["BlockType"] == "LINE":
                        extracted_text += block.get("Text", "") + "\n"

                return {"text": extracted_text.strip(), "job_id": job_id}

            elif status == "FAILED":
                raise Exception(f"Textract job failed: {result.get('StatusMessage')}")

            time.sleep(2)  # Poll every 2 seconds

    except Exception as e:
        print(f"Error extracting text from PDF: {str(e)}")
        return {"text": "", "error": str(e)}


def analyze_image(bucket: str, key: str) -> Dict[str, Any]:
    """Analyze image using AWS Rekognition."""
    try:
        # Detect labels (vehicle damage, accident scenes, etc.)
        label_response = rekognition.detect_labels(
            Image={"S3Object": {"Bucket": bucket, "Name": key}},
            MaxLabels=10,
            MinConfidence=70,
        )

        # Detect text in image
        text_response = rekognition.detect_text(Image={"S3Object": {"Bucket": bucket, "Name": key}})

        labels = [
            {"name": label["Name"], "confidence": label["Confidence"]}
            for label in label_response.get("Labels", [])
        ]

        detected_text = " ".join(
            [
                text["DetectedText"]
                for text in text_response.get("TextDetections", [])
                if text["Type"] == "LINE"
            ]
        )

        return {"labels": labels, "detected_text": detected_text}

    except Exception as e:
        print(f"Error analyzing image: {str(e)}")
        return {"labels": [], "detected_text": "", "error": str(e)}


def extract_entities(text: str) -> Dict[str, Any]:
    """Extract claim entities from text using simple pattern matching."""
    entities = {
        "policy_number": None,
        "claimant_name": None,
        "incident_date": None,
        "incident_location": None,
        "vehicle_info": None,
    }

    # Simple pattern matching (in production, use NER or LLM)
    import re

    # Policy number pattern (e.g., AUTO-001, POL-123456)
    policy_match = re.search(r"(AUTO-\d+|POL-\d+|POLICY[:\s]+(\w+-?\d+))", text, re.I)
    if policy_match:
        entities["policy_number"] = policy_match.group(1)

    # Date pattern (e.g., 2025-10-22, 10/22/2025)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})", text)
    if date_match:
        entities["incident_date"] = date_match.group(1)

    return entities


def lambda_handler(event, context):
    """Lambda handler for Intake Agent."""
    try:
        # Extract S3 event details
        print(f"Event: {json.dumps(event)}")

        # Handle S3 event or direct invocation
        if "Records" in event:
            # S3 event trigger
            bucket = event["Records"][0]["s3"]["bucket"]["name"]
            key = event["Records"][0]["s3"]["object"]["key"]
        else:
            # Direct invocation (for testing or Step Functions)
            bucket = event.get("bucket")
            key = event.get("key")

        if not bucket or not key:
            raise ValueError("Missing bucket or key in event")

        # Generate claim ID
        claim_id = event.get("claim_id") or f"CLAIM-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        print(f"Processing claim {claim_id}: s3://{bucket}/{key}")

        # Determine file type
        file_extension = key.lower().split(".")[-1]
        extracted_data = {}

        if file_extension == "pdf":
            # Extract text from PDF using Textract
            extracted_data = extract_text_from_pdf(bucket, key)
            extracted_data["file_type"] = "pdf"
        elif file_extension in ["jpg", "jpeg", "png"]:
            # Analyze image using Rekognition
            extracted_data = analyze_image(bucket, key)
            extracted_data["file_type"] = "image"
        else:
            extracted_data = {
                "file_type": "unknown",
                "error": f"Unsupported file type: {file_extension}",
            }

        # Extract entities from text
        text_content = (
            extracted_data.get("text", "") + " " + extracted_data.get("detected_text", "")
        )
        entities = extract_entities(text_content)

        # Store in Weaviate ClaimArtifacts collection
        try:
            weaviate_client = get_weaviate_client()
            artifacts = weaviate_client.collections.get("ClaimArtifacts")

            artifacts.data.insert(
                properties={
                    "claim_id": claim_id,
                    "s3_bucket": bucket,
                    "s3_key": key,
                    "file_type": extracted_data.get("file_type", "unknown"),
                    "extracted_text": text_content[:50000],  # Limit text length
                    "entities": json.dumps(entities),
                    "metadata": json.dumps(extracted_data),
                }
            )

            weaviate_client.close()
            print(f"Stored claim {claim_id} in Weaviate")

        except Exception as e:
            print(f"Error storing in Weaviate: {str(e)}")
            # Continue processing even if Weaviate fails

        # Log to DynamoDB AuditLog
        log_id = f"{claim_id}-intake"
        audit_log_table.put_item(
            Item={
                "log_id": log_id,
                "timestamp": datetime.now().isoformat(),
                "claim_id": claim_id,
                "agent": "intake",
                "action": "extract_data",
                "status": "success" if not extracted_data.get("error") else "error",
                "details": json.dumps(
                    {
                        "bucket": bucket,
                        "key": key,
                        "file_type": extracted_data.get("file_type"),
                        "entities": entities,
                    }
                ),
            }
        )

        # Return result for Step Functions
        return {
            "statusCode": 200,
            "claim_id": claim_id,
            "bucket": bucket,
            "key": key,
            "extracted_data": extracted_data,
            "entities": entities,
        }

    except Exception as e:
        print(f"Error in Intake Agent: {str(e)}")
        import traceback

        traceback.print_exc()

        return {"statusCode": 500, "error": str(e)}
