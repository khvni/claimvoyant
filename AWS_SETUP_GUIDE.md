# Claimvoyant AWS Setup Guide

This guide provides step-by-step instructions for setting up the production AWS infrastructure for Claimvoyant.

## Prerequisites

- macOS (you're on Darwin 24.4.0)
- Python 3.13.7 installed ✅
- pip 25.2 installed ✅
- Virtual environment created ✅
- Pre-commit hooks installed ✅

## Phase 0: AWS Account & CLI Setup

### Step 1: Create AWS Account (if you don't have one)

1. Go to https://aws.amazon.com/
2. Click "Create an AWS Account"
3. Follow the signup process (requires credit card, but most services we use are pay-per-request)
4. Enable MFA for root account security

### Step 2: Create IAM User for CLI Access

1. Sign in to AWS Console: https://console.aws.amazon.com/
2. Navigate to IAM → Users → Add users
3. Username: `claimvoyant-admin`
4. Check "Provide user access to the AWS Management Console" (optional)
5. Check "Access key - Programmatic access" ✅
6. Attach policies:
   - `AdministratorAccess` (for initial setup; we'll create least-privilege roles later)
7. Download credentials CSV file (contains Access Key ID and Secret Access Key)
8. **IMPORTANT:** Store credentials securely, never commit to git

### Step 3: Install AWS CLI

```bash
# Install AWS CLI using Homebrew
brew install awscli

# Verify installation
aws --version
# Expected: aws-cli/2.x.x Python/3.x.x Darwin/24.4.0
```

### Step 4: Configure AWS CLI

```bash
# Activate virtual environment
source venv/bin/activate

# Configure AWS credentials
aws configure

# You'll be prompted for:
# AWS Access Key ID: [paste from CSV]
# AWS Secret Access Key: [paste from CSV]
# Default region name: us-east-1
# Default output format: json
```

### Step 5: Verify AWS CLI Access

```bash
# Test AWS credentials
aws sts get-caller-identity

# Expected output:
# {
#     "UserId": "AIDAEXAMPLEUSERID",
#     "Account": "123456789012",
#     "Arn": "arn:aws:iam::123456789012:user/claimvoyant-admin"
# }
```

### Step 6: Install AWS SAM CLI (already installed via requirements-dev.txt)

```bash
# Verify SAM CLI installation
sam --version

# Expected: SAM CLI, version 1.145.2+
```

---

## Phase 1: Create S3 Buckets

We need 4 S3 buckets with versioning and encryption enabled.

```bash
# Set bucket prefix (use your AWS account ID to ensure global uniqueness)
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export BUCKET_PREFIX="claimvoyant-$AWS_ACCOUNT_ID"

# Create raw claims bucket
aws s3api create-bucket \
  --bucket "$BUCKET_PREFIX-raw-claims" \
  --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket "$BUCKET_PREFIX-raw-claims" \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket "$BUCKET_PREFIX-raw-claims" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Block public access
aws s3api put-public-access-block \
  --bucket "$BUCKET_PREFIX-raw-claims" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Repeat for other 3 buckets
for bucket in processed reports policies; do
  aws s3api create-bucket \
    --bucket "$BUCKET_PREFIX-$bucket" \
    --region us-east-1

  aws s3api put-bucket-versioning \
    --bucket "$BUCKET_PREFIX-$bucket" \
    --versioning-configuration Status=Enabled

  aws s3api put-bucket-encryption \
    --bucket "$BUCKET_PREFIX-$bucket" \
    --server-side-encryption-configuration '{
      "Rules": [{
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        }
      }]
    }'

  aws s3api put-public-access-block \
    --bucket "$BUCKET_PREFIX-$bucket" \
    --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
done

# Verify buckets
aws s3 ls | grep claimvoyant
```

---

## Phase 2: Create DynamoDB Tables

### Create Claims Table

```bash
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
  --region us-east-1

# Enable Point-in-Time Recovery for disaster recovery
aws dynamodb update-continuous-backups \
  --table-name Claims \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
  --region us-east-1
```

### Create AuditLog Table

```bash
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
  --region us-east-1

# Enable Point-in-Time Recovery
aws dynamodb update-continuous-backups \
  --table-name AuditLog \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
  --region us-east-1
```

### Verify Tables

```bash
aws dynamodb list-tables --region us-east-1
```

---

## Phase 3: Set up Weaviate Cloud

### Create Weaviate Cloud Cluster

1. Go to https://console.weaviate.cloud/
2. Sign up for free account
3. Create new cluster:
   - **Cluster Name:** `claimvoyant-production`
   - **Tier:** Serverless (Free tier with 50GB storage)
   - **Region:** `us-east-1` (same as AWS)
   - **Weaviate Version:** Latest stable (v1.27+)
4. Wait for cluster provisioning (~2-3 minutes)
5. Copy credentials:
   - **Cluster URL:** `https://claimvoyant-production-xxxxx.weaviate.network`
   - **API Key:** Click "Generate API Key" → Copy key

### Test Weaviate Connection

```bash
# Create test script
cat > test_weaviate.py <<'EOF'
import weaviate
from weaviate.classes.init import Auth
import os

# Replace with your actual credentials
WEAVIATE_URL = "https://claimvoyant-production-xxxxx.weaviate.network"
WEAVIATE_API_KEY = "your-api-key-here"

client = weaviate.connect_to_weaviate_cloud(
    cluster_url=WEAVIATE_URL,
    auth_credentials=Auth.api_key(WEAVIATE_API_KEY)
)

print(f"Connected to Weaviate: {client.is_ready()}")
client.close()
EOF

# Run test
python test_weaviate.py
```

---

## Phase 4: Store Secrets in AWS Secrets Manager

```bash
# Store Weaviate credentials
aws secretsmanager create-secret \
  --name claimvoyant/weaviate \
  --description "Weaviate Cloud credentials for Claimvoyant" \
  --secret-string '{
    "url":"https://claimvoyant-production-xxxxx.weaviate.network",
    "api_key":"your-weaviate-api-key-here"
  }' \
  --region us-east-1

# Verify secret creation
aws secretsmanager list-secrets --region us-east-1
```

---

## Phase 5: Create IAM Roles

### Lambda Execution Role

```bash
# Create trust policy for Lambda
cat > /tmp/lambda-trust-policy.json <<'EOF'
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

# Create IAM role
aws iam create-role \
  --role-name ClaimvoyantLambdaExecutionRole \
  --assume-role-policy-document file:///tmp/lambda-trust-policy.json \
  --description "Execution role for Claimvoyant Lambda functions"

# Create inline policy with least-privilege permissions
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
      "Resource": "arn:aws:logs:us-east-1:*:log-group:/aws/lambda/claimvoyant-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::$BUCKET_PREFIX-*",
        "arn:aws:s3:::$BUCKET_PREFIX-*/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:UpdateItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:*:table/Claims",
        "arn:aws:dynamodb:us-east-1:*:table/AuditLog"
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
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:claimvoyant/*"
    }
  ]
}
EOF

# Attach policy to role
aws iam put-role-policy \
  --role-name ClaimvoyantLambdaExecutionRole \
  --policy-name ClaimvoyantLambdaPolicy \
  --policy-document file:///tmp/lambda-policy.json
```

### Step Functions Execution Role

```bash
# Create trust policy for Step Functions
cat > /tmp/stepfunctions-trust-policy.json <<'EOF'
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

# Create IAM role
aws iam create-role \
  --role-name ClaimvoyantStepFunctionsRole \
  --assume-role-policy-document file:///tmp/stepfunctions-trust-policy.json \
  --description "Execution role for Claimvoyant Step Functions"

# Create inline policy
cat > /tmp/stepfunctions-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:us-east-1:*:function:claimvoyant-*"
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

# Attach policy
aws iam put-role-policy \
  --role-name ClaimvoyantStepFunctionsRole \
  --policy-name ClaimvoyantStepFunctionsPolicy \
  --policy-document file:///tmp/stepfunctions-policy.json
```

---

## Phase 6: Enable AWS Bedrock Model Access

### Request Model Access

1. Go to AWS Console → Bedrock → Model access
2. Click "Modify model access"
3. Select **Anthropic Claude 3.5 Sonnet v2** (model ID: `anthropic.claude-3-5-sonnet-20241022-v2:0`)
4. Click "Request model access"
5. Wait for approval (usually instant for Anthropic models)

### Verify Model Access via CLI

```bash
aws bedrock list-foundation-models \
  --by-provider Anthropic \
  --region us-east-1 \
  --query 'modelSummaries[?contains(modelId, `claude-3-5-sonnet`)].{ModelId:modelId,Name:modelName}' \
  --output table
```

---

## Next Steps

After completing Phase 0-6, you're ready to:

1. **Phase 7:** Deploy Lambda functions (we'll create the code next)
2. **Phase 8:** Create Step Functions state machine
3. **Phase 9:** Configure EventBridge S3 trigger
4. **Phase 10:** Deploy API Gateway
5. **Phase 11:** Build Next.js frontend

## Estimated Costs

With the setup above, estimated monthly costs for **1000 claims/month**:

- **S3:** ~$1-2 (storage + requests)
- **DynamoDB:** ~$5-10 (on-demand pricing)
- **Lambda:** ~$5-10 (1M free requests/month)
- **Bedrock Claude 3.5 Sonnet:** ~$15-20 (input/output tokens)
- **Textract:** ~$5 (1000 pages)
- **Rekognition:** ~$2 (1000 images)
- **Step Functions:** ~$0.50 (4000 state transitions)
- **Weaviate Cloud:** **$0** (free tier up to 50GB)

**Total: ~$33-50/month**

## Troubleshooting

### AWS CLI Not Found

```bash
# Reinstall AWS CLI
brew reinstall awscli
```

### Permission Denied Errors

```bash
# Check IAM user has AdministratorAccess
aws iam list-attached-user-policies --user-name claimvoyant-admin
```

### S3 Bucket Name Already Exists

```bash
# S3 bucket names are globally unique
# Add a random suffix to your bucket prefix
export BUCKET_PREFIX="claimvoyant-$AWS_ACCOUNT_ID-$(date +%s)"
```

### Bedrock Model Access Denied

- Wait 5-10 minutes after requesting model access
- Check region is `us-east-1` (Claude models may not be available in all regions)
- Contact AWS support if access is not granted after 24 hours

---

**Ready to proceed with Phase 7: Lambda Deployment?** Let me know when Phases 0-6 are complete!
