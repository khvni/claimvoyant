# Claimvoyant

**Production-ready, multi-agent auto claims processing system powered by AWS serverless architecture.**

Claimvoyant automates insurance claims processing using AI agents orchestrated through AWS Step Functions. The system intelligently extracts data from claim documents, validates policy coverage, assesses damage, and makes claim decisions using Claude 3.5 Sonnet.

## Architecture

```
Next.js Frontend (Vercel)
    ↓
API Gateway → FastAPI Lambda
    ↓
S3 Upload → EventBridge → Step Functions
    ↓
┌─────────────────────────────────────┐
│  Multi-Agent Workflow Orchestration │
└─────────────────────────────────────┘
    ↓                ↓                ↓
Intake Agent    Policy Agent    Damage Agent
    ↓                ↓                ↓
Valuation Agent ←────┴────→ Decision Agent
                     ↓
         ┌────────────────────┐
         │ AWS Bedrock Claude │
         │  (Final Decision)  │
         └────────────────────┘
                     ↓
         ┌────────────────────┐
         │ DynamoDB + S3      │
         │ (Versioned Claims) │
         └────────────────────┘
```

### Tech Stack

- **AI/ML**: AWS Bedrock (Claude 3.5 Sonnet), AWS Textract, AWS Rekognition
- **Orchestration**: AWS Step Functions
- **Compute**: AWS Lambda (Python 3.13)
- **Storage**: S3 (versioned, encrypted), DynamoDB (PITR enabled)
- **Vector DB**: Weaviate Cloud (RAG for policy retrieval)
- **API**: FastAPI + Mangum
- **Frontend**: Next.js 14 + shadcn/ui (Vercel)
- **IaC**: AWS CLI scripts (SAM/CDK optional)

## Project Structure

```
claimvoyant/
├── src/
│   ├── shared/              # Shared utilities and common code
│   │   ├── config/          # Configuration management
│   │   ├── utils/           # Utility functions
│   │   └── models/          # Data models (Pydantic)
│   └── functions/           # Lambda functions
│       ├── api/             # REST API endpoint
│       ├── intake/          # Textract + Rekognition extraction
│       ├── policy/          # Weaviate RAG policy retrieval
│       ├── damage/          # Damage assessment (placeholder)
│       ├── valuation/       # Vehicle valuation (placeholder)
│       └── decision/        # Bedrock Claude decision engine
├── infrastructure/          # Infrastructure as Code
│   └── stepfunctions/       # Step Functions state machines
├── scripts/                 # Deployment and utility scripts
│   ├── setup_aws_infrastructure.sh
│   ├── deploy_lambdas.sh
│   ├── test_e2e.sh
│   └── init_weaviate.py
├── tests/                   # Unit and integration tests
├── docs/                    # Documentation
│   ├── AWS_SETUP_GUIDE.md
│   ├── DEPLOYMENT_SUMMARY.md
│   └── PROGRESS.md
├── requirements.txt         # Production dependencies
├── requirements-dev.txt     # Development dependencies
├── pyproject.toml           # Python tooling config
└── CLAUDE.md                # Repository context for Claude
```

## Quick Start

### Prerequisites

- AWS Account
- Python 3.13+
- Node.js 18+
- AWS CLI v2
- Weaviate Cloud account (free tier)

### 1. Clone and Setup

```bash
git clone <your-repo-url>
cd claimvoyant

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

### 2. Configure AWS

```bash
# Interactive AWS CLI configuration
./scripts/aws_configure.sh

# Verify AWS credentials
aws sts get-caller-identity
```

### 3. Provision AWS Infrastructure

Follow the detailed steps in [AWS_SETUP_GUIDE.md](./AWS_SETUP_GUIDE.md) to:

1. ✅ Create S3 buckets (raw-claims, processed, reports, policies)
2. ✅ Create DynamoDB tables (Claims, AuditLog)
3. ✅ Set up Weaviate Cloud cluster
4. ✅ Store Weaviate credentials in Secrets Manager
5. ✅ Create IAM roles for Lambda and Step Functions
6. ✅ Enable Bedrock model access (Claude 3.5 Sonnet)
7. Deploy Lambda functions
8. Create Step Functions state machine
9. Configure EventBridge S3 trigger
10. Deploy API Gateway
11. Build and deploy Next.js frontend

### 4. Initialize Weaviate

```bash
# Load sample policies into Weaviate
python scripts/init_weaviate.py
```

### 5. Deploy Lambda Functions

```bash
# Package and deploy each Lambda function
./scripts/deploy_lambdas.sh
```

### 6. Test E2E Workflow

```bash
# Upload a test claim
aws s3 cp tests/fixtures/sample_claim.pdf s3://claimvoyant-{ACCOUNT_ID}-raw-claims/

# Check claim status
python scripts/check_claim_status.py CLAIM-20251022...
```

## Features

### AI-Powered Claims Processing

- **Intelligent Document Extraction**: AWS Textract extracts text from PDFs, AWS Rekognition analyzes images
- **Policy RAG**: Weaviate vector search retrieves relevant policy details
- **Reasoning Engine**: Claude 3.5 Sonnet makes claim decisions with explainable reasoning
- **Multi-Agent Workflow**: Specialized agents handle intake, policy validation, damage assessment, valuation, and final decision

### Production-Grade Architecture

- **Serverless**: Pay-per-request pricing, auto-scaling to zero
- **Versioned Claims**: Complete audit trail with DynamoDB versioning
- **Encrypted Storage**: S3 server-side encryption (AES-256)
- **Disaster Recovery**: DynamoDB Point-in-Time Recovery enabled
- **Security**: AWS Secrets Manager, least-privilege IAM roles, gitleaks scanning

### Developer Experience

- **Pre-commit Hooks**: Black, isort, gitleaks for code quality
- **Comprehensive Logging**: CloudWatch Logs with structured JSON
- **Type Safety**: Python type hints, Pydantic models
- **Testing**: pytest, moto for AWS service mocking
- **Documentation**: Detailed setup guide, inline docstrings

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/api/v1/claims/upload` | Upload claim documents |
| `GET` | `/api/v1/claims/{id}` | Get claim status and decision |
| `GET` | `/api/v1/claims/{id}/audit` | Get audit log for claim |
| `GET` | `/api/v1/claims` | List recent claims |

## Cost Estimates

**Estimated monthly cost for 1000 claims/month:**

- S3: ~$1-2 (storage + requests)
- DynamoDB: ~$5-10 (on-demand pricing)
- Lambda: ~$5-10 (1M free requests/month)
- Bedrock Claude 3.5 Sonnet: ~$15-20 (input/output tokens)
- Textract: ~$5 (1000 pages)
- Rekognition: ~$2 (1000 images)
- Step Functions: ~$0.50 (4000 state transitions)
- Weaviate Cloud: **$0** (free tier up to 50GB)

**Total: ~$33-50/month**

## Development

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=lambda --cov-report=html

# Run specific test file
pytest tests/test_intake_agent.py
```

### Local API Development

```bash
# Run FastAPI locally
cd lambda/api
uvicorn lambda_function:app --reload
```

### Code Quality

```bash
# Format code
black lambda/ scripts/

# Sort imports
isort lambda/ scripts/

# Lint code
flake8 lambda/ scripts/

# Type check
mypy lambda/
```

## Monitoring

### CloudWatch Logs

```bash
# View Lambda logs
aws logs tail /aws/lambda/claimvoyant-intake --follow

# Filter for errors
aws logs filter-pattern /aws/lambda/claimvoyant-decision --pattern ERROR
```

### Step Functions Execution

```bash
# List executions
aws stepfunctions list-executions --state-machine-arn <ARN>

# Get execution history
aws stepfunctions get-execution-history --execution-arn <ARN>
```

## Troubleshooting

### Common Issues

1. **Textract Job Timeout**: Increase Lambda timeout or use Step Functions wait state
2. **Bedrock Access Denied**: Ensure model access is enabled in AWS Console
3. **Weaviate Connection Failed**: Check credentials in Secrets Manager
4. **DynamoDB Throughput Exceeded**: Switch from provisioned to on-demand billing

See [AWS_SETUP_GUIDE.md](./AWS_SETUP_GUIDE.md) for detailed troubleshooting.

## Roadmap

- [ ] Add computer vision model for damage assessment
- [ ] Integrate KBB/NADA API for vehicle valuation
- [ ] Implement real-time notifications (SNS/EventBridge)
- [ ] Add Cognito authentication to frontend
- [ ] Deploy frontend to Vercel
- [ ] Add CloudWatch alarms and X-Ray tracing
- [ ] Implement claim dispute workflow
- [ ] Add support for additional document types (photos, repair estimates)

## Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make changes and commit: `git commit -m "feat: add feature"`
3. Push to branch: `git push origin feature/your-feature`
4. Pre-commit hooks will run automatically
5. Create a Pull Request

## License

MIT License - see [LICENSE](LICENSE) file for details

## Acknowledgments

- AWS Samples for serverless patterns
- Weaviate for vector search capabilities
- Anthropic for Claude 3.5 Sonnet reasoning
- LlamaIndex for multi-agent orchestration inspiration

---

**Built with ❤️ using AWS serverless and Claude 3.5 Sonnet**

For detailed setup instructions, see [AWS_SETUP_GUIDE.md](./AWS_SETUP_GUIDE.md)
