#!/bin/bash
set -e

echo "========================================"
echo "Claimvoyant AWS Infrastructure Setup"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="us-east-1"
BUCKET_PREFIX="claimvoyant-${AWS_ACCOUNT_ID}"

echo "AWS Account ID: ${AWS_ACCOUNT_ID}"
echo "Region: ${AWS_REGION}"
echo "Bucket Prefix: ${BUCKET_PREFIX}"
echo ""

# Phase 1: Create S3 Buckets
echo "${GREEN}Phase 1: Creating S3 Buckets...${NC}"

for bucket in raw-claims processed reports policies; do
    BUCKET_NAME="${BUCKET_PREFIX}-${bucket}"

    if aws s3api head-bucket --bucket "${BUCKET_NAME}" 2>/dev/null; then
        echo "  ✓ Bucket ${BUCKET_NAME} already exists"
    else
        echo "  Creating bucket: ${BUCKET_NAME}"
        aws s3api create-bucket \
            --bucket "${BUCKET_NAME}" \
            --region "${AWS_REGION}" 2>/dev/null || echo "  ⚠ Bucket creation skipped (may already exist)"

        # Enable versioning
        aws s3api put-bucket-versioning \
            --bucket "${BUCKET_NAME}" \
            --versioning-configuration Status=Enabled

        # Enable encryption
        aws s3api put-bucket-encryption \
            --bucket "${BUCKET_NAME}" \
            --server-side-encryption-configuration '{
                "Rules": [{
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    }
                }]
            }'

        # Block public access
        aws s3api put-public-access-block \
            --bucket "${BUCKET_NAME}" \
            --public-access-block-configuration \
                "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

        echo "  ✓ Bucket ${BUCKET_NAME} created with versioning and encryption"
    fi
done

echo ""

# Phase 2: Create DynamoDB Tables
echo "${GREEN}Phase 2: Creating DynamoDB Tables...${NC}"

# Create Claims table
if aws dynamodb describe-table --table-name Claims --region "${AWS_REGION}" 2>/dev/null; then
    echo "  ✓ Claims table already exists"
else
    echo "  Creating Claims table..."
    aws dynamodb create-table \
        --table-name Claims \
        --attribute-definitions \
            AttributeName=claim_id,AttributeType=S \
            AttributeName=version,AttributeType=S \
        --key-schema \
            AttributeName=claim_id,KeyType=HASH \
            AttributeName=version,KeyType=RANGE \
        --billing-mode PAY_PER_REQUEST \
        --tags Key=Project,Value=Claimvoyant Key=Environment,Value=Production \
        --region "${AWS_REGION}" > /dev/null

    # Wait for table to be active
    aws dynamodb wait table-exists --table-name Claims --region "${AWS_REGION}"

    # Enable Point-in-Time Recovery
    aws dynamodb update-continuous-backups \
        --table-name Claims \
        --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
        --region "${AWS_REGION}" > /dev/null

    echo "  ✓ Claims table created with PITR enabled"
fi

# Create AuditLog table
if aws dynamodb describe-table --table-name AuditLog --region "${AWS_REGION}" 2>/dev/null; then
    echo "  ✓ AuditLog table already exists"
else
    echo "  Creating AuditLog table..."
    aws dynamodb create-table \
        --table-name AuditLog \
        --attribute-definitions \
            AttributeName=log_id,AttributeType=S \
            AttributeName=timestamp,AttributeType=S \
        --key-schema \
            AttributeName=log_id,KeyType=HASH \
            AttributeName=timestamp,KeyType=RANGE \
        --billing-mode PAY_PER_REQUEST \
        --tags Key=Project,Value=Claimvoyant Key=Environment,Value=Production \
        --region "${AWS_REGION}" > /dev/null

    # Wait for table to be active
    aws dynamodb wait table-exists --table-name AuditLog --region "${AWS_REGION}"

    # Enable Point-in-Time Recovery
    aws dynamodb update-continuous-backups \
        --table-name AuditLog \
        --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
        --region "${AWS_REGION}" > /dev/null

    echo "  ✓ AuditLog table created with PITR enabled"
fi

echo ""

# Phase 3: Weaviate Cloud Setup (Manual)
echo "${YELLOW}Phase 3: Weaviate Cloud Setup${NC}"
echo "  Please complete the following steps manually:"
echo "  1. Go to https://console.weaviate.cloud/"
echo "  2. Sign up for free account"
echo "  3. Create cluster: 'claimvoyant-production' in us-east-1"
echo "  4. Generate API key"
echo "  5. Copy Cluster URL and API Key"
echo ""
read -p "Press Enter when you have your Weaviate credentials ready..."

echo ""
read -p "Enter Weaviate Cluster URL: " WEAVIATE_URL
read -p "Enter Weaviate API Key: " WEAVIATE_API_KEY

# Phase 4: Store Weaviate credentials in Secrets Manager
echo "${GREEN}Phase 4: Storing Weaviate credentials in Secrets Manager...${NC}"

SECRET_NAME="claimvoyant/weaviate"

if aws secretsmanager describe-secret --secret-id "${SECRET_NAME}" --region "${AWS_REGION}" 2>/dev/null; then
    echo "  Updating existing secret..."
    aws secretsmanager update-secret \
        --secret-id "${SECRET_NAME}" \
        --secret-string "{\"url\":\"${WEAVIATE_URL}\",\"api_key\":\"${WEAVIATE_API_KEY}\"}" \
        --region "${AWS_REGION}" > /dev/null
else
    echo "  Creating secret..."
    aws secretsmanager create-secret \
        --name "${SECRET_NAME}" \
        --description "Weaviate Cloud credentials for Claimvoyant" \
        --secret-string "{\"url\":\"${WEAVIATE_URL}\",\"api_key\":\"${WEAVIATE_API_KEY}\"}" \
        --region "${AWS_REGION}" > /dev/null
fi

echo "  ✓ Weaviate credentials stored in Secrets Manager"
echo ""

# Phase 5: Create IAM Roles
echo "${GREEN}Phase 5: Creating IAM Roles...${NC}"

# Lambda Execution Role
LAMBDA_ROLE_NAME="ClaimvoyantLambdaExecutionRole"

if aws iam get-role --role-name "${LAMBDA_ROLE_NAME}" 2>/dev/null; then
    echo "  ✓ Lambda execution role already exists"
else
    echo "  Creating Lambda execution role..."

    # Create trust policy
    cat > /tmp/lambda-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    aws iam create-role \
        --role-name "${LAMBDA_ROLE_NAME}" \
        --assume-role-policy-document file:///tmp/lambda-trust-policy.json \
        --description "Execution role for Claimvoyant Lambda functions" > /dev/null

    # Create inline policy
    cat > /tmp/lambda-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:${AWS_REGION}:*:log-group:/aws/lambda/claimvoyant-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::${BUCKET_PREFIX}-*",
        "arn:aws:s3:::${BUCKET_PREFIX}-*/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:UpdateItem",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:${AWS_REGION}:*:table/Claims",
        "arn:aws:dynamodb:${AWS_REGION}:*:table/AuditLog"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "textract:DetectDocumentText",
        "textract:StartDocumentTextDetection",
        "textract:GetDocumentTextDetection"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "rekognition:DetectLabels",
        "rekognition:DetectText"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:${AWS_REGION}::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:${AWS_REGION}:*:secret:claimvoyant/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "states:StartExecution"
      ],
      "Resource": "arn:aws:states:${AWS_REGION}:*:stateMachine:ClaimvoyantWorkflow"
    }
  ]
}
EOF

    aws iam put-role-policy \
        --role-name "${LAMBDA_ROLE_NAME}" \
        --policy-name ClaimvoyantLambdaPolicy \
        --policy-document file:///tmp/lambda-policy.json

    echo "  ✓ Lambda execution role created"
fi

# Step Functions Execution Role
STEPFUNCTIONS_ROLE_NAME="ClaimvoyantStepFunctionsRole"

if aws iam get-role --role-name "${STEPFUNCTIONS_ROLE_NAME}" 2>/dev/null; then
    echo "  ✓ Step Functions role already exists"
else
    echo "  Creating Step Functions execution role..."

    # Create trust policy
    cat > /tmp/stepfunctions-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "states.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    aws iam create-role \
        --role-name "${STEPFUNCTIONS_ROLE_NAME}" \
        --assume-role-policy-document file:///tmp/stepfunctions-trust-policy.json \
        --description "Execution role for Claimvoyant Step Functions" > /dev/null

    # Create inline policy
    cat > /tmp/stepfunctions-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:${AWS_REGION}:*:function:claimvoyant-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
EOF

    aws iam put-role-policy \
        --role-name "${STEPFUNCTIONS_ROLE_NAME}" \
        --policy-name ClaimvoyantStepFunctionsPolicy \
        --policy-document file:///tmp/stepfunctions-policy.json

    echo "  ✓ Step Functions execution role created"
fi

echo ""

# Phase 6: Enable Bedrock Model Access
echo "${YELLOW}Phase 6: Enable Bedrock Model Access${NC}"
echo "  Please complete the following steps manually:"
echo "  1. Go to AWS Console → Bedrock → Model access"
echo "  2. Click 'Modify model access'"
echo "  3. Select 'Anthropic Claude 3.5 Sonnet v2'"
echo "  4. Click 'Request model access'"
echo "  5. Wait for approval (usually instant)"
echo ""
echo "  Verify with: aws bedrock list-foundation-models --by-provider Anthropic --region ${AWS_REGION}"
echo ""
read -p "Press Enter when Bedrock model access is enabled..."

echo ""
echo "${GREEN}========================================"
echo "Infrastructure Setup Complete!"
echo "========================================${NC}"
echo ""
echo "Summary:"
echo "  ✓ S3 Buckets: ${BUCKET_PREFIX}-{raw-claims,processed,reports,policies}"
echo "  ✓ DynamoDB Tables: Claims, AuditLog"
echo "  ✓ Secrets Manager: claimvoyant/weaviate"
echo "  ✓ IAM Roles: ${LAMBDA_ROLE_NAME}, ${STEPFUNCTIONS_ROLE_NAME}"
echo "  ✓ Bedrock: Claude 3.5 Sonnet access enabled"
echo ""
echo "Next steps:"
echo "  1. Initialize Weaviate: python scripts/init_weaviate.py"
echo "  2. Deploy Lambda functions: ./scripts/deploy_lambdas.sh"
echo "  3. Create Step Functions workflow"
echo ""

# Save configuration for later use
cat > .aws-config <<EOF
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}
AWS_REGION=${AWS_REGION}
BUCKET_PREFIX=${BUCKET_PREFIX}
WEAVIATE_URL=${WEAVIATE_URL}
LAMBDA_ROLE_ARN=arn:aws:iam::${AWS_ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}
STEPFUNCTIONS_ROLE_ARN=arn:aws:iam::${AWS_ACCOUNT_ID}:role/${STEPFUNCTIONS_ROLE_NAME}
EOF

echo "Configuration saved to .aws-config"
