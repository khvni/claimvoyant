"""
Decision Agent Lambda Function

Uses AWS Bedrock Claude 3.5 Sonnet to make intelligent claim decisions
based on extracted data, policy details, and damage assessment.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict

import boto3

# AWS clients
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# DynamoDB table
claims_table = dynamodb.Table("Claims")
audit_log_table = dynamodb.Table("AuditLog")


def invoke_claude(prompt: str) -> Dict[str, Any]:
    """Invoke AWS Bedrock Claude 3.5 Sonnet for claim reasoning."""
    try:
        model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,  # Lower temperature for more deterministic decisions
        }

        response = bedrock.invoke_model(modelId=model_id, body=json.dumps(request_body))

        response_body = json.loads(response["body"].read())
        content = response_body["content"][0]["text"]

        # Parse JSON response from Claude
        # Claude is instructed to return structured JSON
        decision_data = json.loads(content)

        return decision_data

    except Exception as e:
        print(f"Error invoking Claude: {str(e)}")
        return {
            "decision": "ERROR",
            "reasoning": f"Failed to process claim: {str(e)}",
            "confidence": 0.0,
        }


def build_decision_prompt(event: Dict[str, Any]) -> str:
    """Build comprehensive prompt for Claude to make claim decision."""
    claim_id = event.get("claim_id")
    policy_data = event.get("policy_data", {})
    extracted_data = event.get("extracted_data", {})
    entities = event.get("entities", {})

    prompt = f"""You are an expert auto insurance claims adjuster. Analyze the following claim and provide a decision.

CLAIM ID: {claim_id}

POLICY INFORMATION:
{json.dumps(policy_data, indent=2)}

EXTRACTED CLAIM DATA:
{json.dumps(extracted_data, indent=2)}

EXTRACTED ENTITIES:
{json.dumps(entities, indent=2)}

INSTRUCTIONS:
1. Review the policy coverage and limits
2. Assess the claim validity based on extracted information
3. Check if the claim falls within coverage
4. Determine if deductible applies
5. Calculate estimated payout (if applicable)
6. Provide a clear decision: APPROVED, DENIED, or PENDING

RESPOND WITH VALID JSON ONLY (no markdown, no code blocks):
{{
  "decision": "APPROVED|DENIED|PENDING",
  "reasoning": "Brief explanation of your decision (2-3 sentences)",
  "confidence": 0.0-1.0,
  "estimated_payout": 0.0,
  "deductible_applies": true|false,
  "required_actions": ["list", "of", "actions"],
  "risk_factors": ["identified", "risks"]
}}

Respond now with JSON:"""

    return prompt


def lambda_handler(event, context):
    """Lambda handler for Decision Agent."""
    try:
        print(f"Event: {json.dumps(event)}")

        claim_id = event.get("claim_id")
        bucket_prefix = os.environ.get("BUCKET_PREFIX", "claimvoyant")

        # Build decision prompt
        prompt = build_decision_prompt(event)

        print(f"Making decision for claim {claim_id}")

        # Invoke Claude for decision
        decision_data = invoke_claude(prompt)

        print(f"Decision: {decision_data.get('decision')}")

        # Store decision in DynamoDB with versioning
        version = datetime.now().isoformat()
        claims_table.put_item(
            Item={
                "claim_id": claim_id,
                "version": version,
                "status": decision_data.get("decision", "ERROR"),
                "decision_data": json.dumps(decision_data),
                "policy_data": json.dumps(event.get("policy_data", {})),
                "extracted_data": json.dumps(event.get("extracted_data", {})),
                "entities": json.dumps(event.get("entities", {})),
                "timestamp": version,
            }
        )

        # Save decision report to S3
        report = {
            "claim_id": claim_id,
            "timestamp": version,
            "decision": decision_data.get("decision"),
            "reasoning": decision_data.get("reasoning"),
            "confidence": decision_data.get("confidence"),
            "estimated_payout": decision_data.get("estimated_payout"),
            "deductible_applies": decision_data.get("deductible_applies"),
            "required_actions": decision_data.get("required_actions", []),
            "risk_factors": decision_data.get("risk_factors", []),
            "policy_data": event.get("policy_data"),
            "entities": event.get("entities"),
        }

        report_key = f"{claim_id}/final_decision.json"
        s3.put_object(
            Bucket=f"{bucket_prefix}-reports",
            Key=report_key,
            Body=json.dumps(report, indent=2),
            ContentType="application/json",
        )

        print(f"Saved decision report to s3://{bucket_prefix}-reports/{report_key}")

        # Log to DynamoDB AuditLog
        log_id = f"{claim_id}-decision"
        audit_log_table.put_item(
            Item={
                "log_id": log_id,
                "timestamp": version,
                "claim_id": claim_id,
                "agent": "decision",
                "action": "make_decision",
                "status": "success",
                "details": json.dumps(
                    {
                        "decision": decision_data.get("decision"),
                        "confidence": decision_data.get("confidence"),
                    }
                ),
            }
        )

        # Return result
        return {
            "statusCode": 200,
            "claim_id": claim_id,
            "version": version,
            "decision": decision_data.get("decision"),
            "decision_data": decision_data,
            "report_s3_key": report_key,
        }

    except Exception as e:
        print(f"Error in Decision Agent: {str(e)}")
        import traceback

        traceback.print_exc()

        return {"statusCode": 500, "claim_id": event.get("claim_id"), "error": str(e)}
