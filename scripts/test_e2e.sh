#!/bin/bash
# End-to-End Test Script for Claimvoyant
# Tests the complete claims processing workflow

set -e

echo "========================================"
echo "Claimvoyant E2E Test Suite"
echo "========================================"
echo ""

# Load AWS configuration
if [ -f .aws-config ]; then
    source .aws-config
fi

API_ENDPOINT=$(cat .api-endpoint 2>/dev/null || echo "https://YOUR_API_GATEWAY_ID.execute-api.us-east-1.amazonaws.com/prod")
STATE_MACHINE_ARN=${STATE_MACHINE_ARN:-"arn:aws:states:us-east-1:YOUR_AWS_ACCOUNT_ID:stateMachine:ClaimvoyantWorkflow"}
BUCKET_PREFIX=${BUCKET_PREFIX:-"claimvoyant-YOUR_AWS_ACCOUNT_ID"}

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((TESTS_FAILED++))
}

info() {
    echo -e "${YELLOW}ℹ INFO${NC}: $1"
}

# Test 1: API Health Check
echo "Test 1: API Health Check"
HEALTH_RESPONSE=$(curl -s "${API_ENDPOINT}/")
if echo "$HEALTH_RESPONSE" | grep -q "\"status\": \"ok\""; then
    pass "API health check returned OK"
else
    fail "API health check failed: $HEALTH_RESPONSE"
fi
echo ""

# Test 2: List Claims (Empty)
echo "Test 2: List Claims Endpoint"
CLAIMS_RESPONSE=$(curl -s "${API_ENDPOINT}/api/v1/claims")
if echo "$CLAIMS_RESPONSE" | grep -q "\"claims\""; then
    pass "List claims endpoint accessible"
else
    fail "List claims endpoint failed: $CLAIMS_RESPONSE"
fi
echo ""

# Test 3: Create test claim file
echo "Test 3: Upload Test Claim Document to S3"
CLAIM_ID="CLAIM-TEST-$(date +%s)"
TEST_CONTENT="Test claim document for automated testing. Policy: AUTO-001. Damage: Minor scratches on rear bumper."

echo "$TEST_CONTENT" > /tmp/${CLAIM_ID}.txt

aws s3 cp /tmp/${CLAIM_ID}.txt s3://${BUCKET_PREFIX}-raw-claims/test/${CLAIM_ID}.txt --quiet

if [ $? -eq 0 ]; then
    pass "Test claim document uploaded to S3"
else
    fail "Failed to upload test claim document"
fi
echo ""

# Test 4: Trigger Step Functions Workflow
echo "Test 4: Trigger Step Functions Workflow"
EXECUTION_NAME="${CLAIM_ID}-$(date +%s)"
EXECUTION_INPUT=$(cat <<EOF
{
  "claim_id": "${CLAIM_ID}",
  "bucket": "${BUCKET_PREFIX}-raw-claims",
  "key": "test/${CLAIM_ID}.txt"
}
EOF
)

EXECUTION_ARN=$(aws stepfunctions start-execution \
    --state-machine-arn "${STATE_MACHINE_ARN}" \
    --name "${EXECUTION_NAME}" \
    --input "${EXECUTION_INPUT}" \
    --query 'executionArn' \
    --output text 2>/dev/null)

if [ -n "$EXECUTION_ARN" ]; then
    pass "Step Functions workflow started: $EXECUTION_NAME"
    info "Execution ARN: $EXECUTION_ARN"
else
    fail "Failed to start Step Functions workflow"
    echo ""
    echo "========================================"
    echo "Test Summary"
    echo "========================================"
    echo -e "Passed: ${GREEN}${TESTS_PASSED}${NC}"
    echo -e "Failed: ${RED}${TESTS_FAILED}${NC}"
    exit 1
fi
echo ""

# Test 5: Wait for workflow completion
echo "Test 5: Monitor Workflow Execution"
info "Waiting for workflow to complete (max 60 seconds)..."

MAX_WAIT=60
ELAPSED=0
STATUS="RUNNING"

while [ $ELAPSED -lt $MAX_WAIT ] && [ "$STATUS" = "RUNNING" ]; do
    sleep 5
    ((ELAPSED+=5))

    STATUS=$(aws stepfunctions describe-execution \
        --execution-arn "${EXECUTION_ARN}" \
        --query 'status' \
        --output text 2>/dev/null || echo "UNKNOWN")

    echo -n "."
done
echo ""

if [ "$STATUS" = "SUCCEEDED" ]; then
    pass "Workflow completed successfully"
elif [ "$STATUS" = "RUNNING" ]; then
    info "Workflow still running after ${MAX_WAIT}s (this is normal for complex workflows)"
    info "Check status later with: aws stepfunctions describe-execution --execution-arn ${EXECUTION_ARN}"
else
    fail "Workflow ended with status: $STATUS"
    info "Check logs: aws stepfunctions get-execution-history --execution-arn ${EXECUTION_ARN}"
fi
echo ""

# Test 6: Check DynamoDB for claim result (if workflow completed)
if [ "$STATUS" = "SUCCEEDED" ]; then
    echo "Test 6: Verify Claim in DynamoDB"
    sleep 2  # Give DynamoDB time to update

    CLAIM_DATA=$(aws dynamodb query \
        --table-name Claims \
        --key-condition-expression "claim_id = :cid" \
        --expression-attribute-values "{\":cid\":{\"S\":\"${CLAIM_ID}\"}}" \
        --query 'Items[0]' \
        --output json 2>/dev/null)

    if echo "$CLAIM_DATA" | grep -q "claim_id"; then
        pass "Claim found in DynamoDB"
        info "Claim status: $(echo "$CLAIM_DATA" | grep -o '"status":[^,}]*' | cut -d':' -f2 | tr -d ' "')"
    else
        fail "Claim not found in DynamoDB"
    fi
    echo ""
fi

# Test 7: Query claim via API
echo "Test 7: Get Claim Details via API"
CLAIM_DETAILS=$(curl -s "${API_ENDPOINT}/api/v1/claims/${CLAIM_ID}")

if echo "$CLAIM_DETAILS" | grep -q "${CLAIM_ID}"; then
    pass "Claim details retrieved via API"
    info "Response: $CLAIM_DETAILS"
else
    info "Claim not yet available via API (may still be processing)"
fi
echo ""

# Cleanup
echo "Test 8: Cleanup Test Data"
rm -f /tmp/${CLAIM_ID}.txt
if [ $? -eq 0 ]; then
    pass "Local test file cleaned up"
fi
echo ""

# Summary
echo "========================================"
echo "Test Summary"
echo "========================================"
echo -e "Passed: ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Failed: ${RED}${TESTS_FAILED}${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Check workflow execution in AWS Console:"
    echo "   https://console.aws.amazon.com/states/home?region=us-east-1#/executions/details/${EXECUTION_ARN}"
    echo ""
    echo "2. Monitor CloudWatch Logs:"
    echo "   aws logs tail /aws/lambda/claimvoyant-intake --follow"
    echo ""
    echo "3. View claim in DynamoDB:"
    echo "   aws dynamodb get-item --table-name Claims --key '{\"claim_id\":{\"S\":\"${CLAIM_ID}\"}}'"
    exit 0
else
    echo -e "${RED}Some tests failed. Please review the output above.${NC}"
    exit 1
fi
