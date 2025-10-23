#!/bin/bash
set -e

echo "========================================"
echo "Claimvoyant Lambda Deployment"
echo "========================================"
echo ""

# Load AWS configuration
if [ -f .aws-config ]; then
    source .aws-config
    echo "Loaded configuration from .aws-config"
else
    echo "Error: .aws-config not found. Run ./scripts/setup_aws_infrastructure.sh first"
    exit 1
fi

echo "AWS Account: ${AWS_ACCOUNT_ID}"
echo "Region: ${AWS_REGION}"
echo "Lambda Role ARN: ${LAMBDA_ROLE_ARN}"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to deploy a Lambda function
deploy_lambda() {
    local FUNCTION_NAME=$1
    local FUNCTION_DIR=$2
    local HANDLER=${3:-lambda_function.lambda_handler}
    local TIMEOUT=${4:-120}
    local MEMORY=${5:-512}

    echo "${GREEN}Deploying ${FUNCTION_NAME}...${NC}"

    # Create deployment package
    local CURRENT_DIR=$(pwd)
    cd "${CURRENT_DIR}/${FUNCTION_DIR}"

    # Create a clean zip file
    rm -f function.zip

    # Add Lambda function code
    zip -q function.zip lambda_function.py

    # Add shared code if exists
    if [ -d "${CURRENT_DIR}/src/shared" ]; then
        cd "${CURRENT_DIR}/src"
        zip -qr "${CURRENT_DIR}/${FUNCTION_DIR}/function.zip" shared/
    fi

    # Add dependencies from virtual environment
    if [ -d "${CURRENT_DIR}/venv/lib/python3.13/site-packages" ]; then
        cd "${CURRENT_DIR}/venv/lib/python3.13/site-packages"
        zip -qr -u "${CURRENT_DIR}/${FUNCTION_DIR}/function.zip" \
            boto3* \
            botocore* \
            weaviate* \
            fastapi* \
            mangum* \
            pydantic* \
            starlette* \
            anyio* \
            typing_extensions* \
            annotated_types* \
            sniffio* \
            idna* \
            2>/dev/null || echo "  (Some dependencies not found, Lambda may use built-in versions)"
        cd "${CURRENT_DIR}"
    fi

    cd "${CURRENT_DIR}/${FUNCTION_DIR}"

    # Check if function exists
    if aws lambda get-function --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}" 2>/dev/null; then
        echo "  Updating existing function..."
        aws lambda update-function-code \
            --function-name "${FUNCTION_NAME}" \
            --zip-file fileb://function.zip \
            --region "${AWS_REGION}" > /dev/null

        # Update configuration
        aws lambda update-function-configuration \
            --function-name "${FUNCTION_NAME}" \
            --timeout "${TIMEOUT}" \
            --memory-size "${MEMORY}" \
            --environment "Variables={BUCKET_PREFIX=${BUCKET_PREFIX}}" \
            --region "${AWS_REGION}" > /dev/null

        echo "  ✓ Function updated"
    else
        echo "  Creating new function..."
        aws lambda create-function \
            --function-name "${FUNCTION_NAME}" \
            --runtime python3.13 \
            --role "${LAMBDA_ROLE_ARN}" \
            --handler "${HANDLER}" \
            --zip-file fileb://function.zip \
            --timeout "${TIMEOUT}" \
            --memory-size "${MEMORY}" \
            --environment "Variables={BUCKET_PREFIX=${BUCKET_PREFIX}}" \
            --region "${AWS_REGION}" > /dev/null

        echo "  ✓ Function created"
    fi

    # Wait for function to be active
    aws lambda wait function-active --function-name "${FUNCTION_NAME}" --region "${AWS_REGION}"

    # Clean up
    rm -f function.zip

    cd "${CURRENT_DIR}" > /dev/null

    echo ""
}

# Deploy all Lambda functions
echo "Starting Lambda deployment..."
echo ""

deploy_lambda "claimvoyant-intake" "src/functions/intake" "lambda_function.lambda_handler" 180 1024
deploy_lambda "claimvoyant-policy" "src/functions/policy" "lambda_function.lambda_handler" 60 512
deploy_lambda "claimvoyant-damage" "src/functions/damage" "lambda_function.lambda_handler" 60 512
deploy_lambda "claimvoyant-valuation" "src/functions/valuation" "lambda_function.lambda_handler" 60 512
deploy_lambda "claimvoyant-decision" "src/functions/decision" "lambda_function.lambda_handler" 120 1024
deploy_lambda "claimvoyant-api" "src/functions/api" "lambda_function_simple.handler" 30 512

echo "${GREEN}========================================"
echo "Lambda Deployment Complete!"
echo "========================================${NC}"
echo ""
echo "Deployed functions:"
echo "  ✓ claimvoyant-intake (180s timeout, 1024MB)"
echo "  ✓ claimvoyant-policy (60s timeout, 512MB)"
echo "  ✓ claimvoyant-damage (60s timeout, 512MB)"
echo "  ✓ claimvoyant-valuation (60s timeout, 512MB)"
echo "  ✓ claimvoyant-decision (120s timeout, 1024MB)"
echo "  ✓ claimvoyant-api (30s timeout, 512MB)"
echo ""
echo "Next steps:"
echo "  1. Create Step Functions state machine"
echo "  2. Deploy API Gateway"
echo "  3. Configure EventBridge trigger"
