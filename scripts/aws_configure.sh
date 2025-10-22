#!/bin/bash
set -e

echo "========================================="
echo "Claimvoyant AWS Configuration Script"
echo "========================================="
echo ""

# Check if AWS CLI is configured
if aws sts get-caller-identity &>/dev/null; then
    echo "✅ AWS CLI is already configured"
    aws sts get-caller-identity
    echo ""
    read -p "Do you want to reconfigure AWS CLI? (y/N): " reconfigure
    if [[ ! "$reconfigure" =~ ^[Yy]$ ]]; then
        echo "Skipping AWS CLI configuration"
        exit 0
    fi
fi

echo "Follow these steps to configure AWS:"
echo ""
echo "1. If you don't have an AWS account, create one at https://aws.amazon.com/"
echo "2. Sign in to AWS Console: https://console.aws.amazon.com/"
echo "3. Navigate to IAM → Users → Add users"
echo "4. Create user: claimvoyant-admin"
echo "5. Enable programmatic access (Access Key)"
echo "6. Attach AdministratorAccess policy (temporary for setup)"
echo "7. Download the credentials CSV"
echo ""
read -p "Press Enter when you have your Access Key ID and Secret Access Key ready..."

echo ""
echo "Configuring AWS CLI..."
echo ""

aws configure

echo ""
echo "✅ AWS CLI configured successfully!"
echo ""
echo "Verifying credentials..."
aws sts get-caller-identity

echo ""
echo "========================================="
echo "AWS Configuration Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Run: source venv/bin/activate"
echo "  2. Run: ./scripts/setup_aws_infrastructure.sh"
