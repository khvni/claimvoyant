"""
Initialize Weaviate collections and load sample policy data.

Run this script after setting up Weaviate Cloud cluster.
"""

import json
import os

import weaviate
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.init import Auth


def create_collections(client):
    """Create Weaviate collections for Claimvoyant."""
    print("Creating PolicyDocuments collection...")

    # Create PolicyDocuments collection
    client.collections.create(
        name="PolicyDocuments",
        vectorizer_config=Configure.Vectorizer.text2vec_weaviate(
            model="snowflake-arctic-embed-l-v2.0"
        ),
        generative_config=Configure.Generative.aws(
            model="anthropic.claude-3-5-sonnet-20241022-v2:0", region="us-east-1"
        ),
        properties=[
            Property(name="policy_id", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="content", data_type=DataType.TEXT),
            Property(name="coverage_type", data_type=DataType.TEXT),
            Property(name="deductible", data_type=DataType.NUMBER, skip_vectorization=True),
            Property(name="coverage_limit", data_type=DataType.NUMBER, skip_vectorization=True),
            Property(
                name="filing_deadline_days",
                data_type=DataType.NUMBER,
                skip_vectorization=True,
            ),
        ],
    )

    print("Creating ClaimArtifacts collection...")

    # Create ClaimArtifacts collection
    client.collections.create(
        name="ClaimArtifacts",
        vectorizer_config=Configure.Vectorizer.text2vec_weaviate(
            model="snowflake-arctic-embed-l-v2.0"
        ),
        properties=[
            Property(name="claim_id", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="s3_bucket", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="s3_key", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="file_type", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="extracted_text", data_type=DataType.TEXT),
            Property(name="entities", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="metadata", data_type=DataType.TEXT, skip_vectorization=True),
        ],
    )

    print("Collections created successfully!")


def load_sample_policies(client):
    """Load sample auto insurance policies into Weaviate."""
    print("Loading sample policies...")

    policies = client.collections.get("PolicyDocuments")

    sample_policies = [
        {
            "policy_id": "AUTO-001",
            "content": """
            Comprehensive Auto Insurance Policy
            Policy Number: AUTO-001
            Coverage Type: Comprehensive + Collision
            Coverage Limit: $50,000
            Deductible: $500
            Filing Deadline: 30 days from incident

            This policy covers damage to your vehicle from accidents, theft, vandalism,
            and natural disasters. Collision coverage includes accidents with other vehicles
            or objects. Comprehensive covers non-collision events like theft, fire, or hail.
            """,
            "coverage_type": "Comprehensive + Collision",
            "deductible": 500.0,
            "coverage_limit": 50000.0,
            "filing_deadline_days": 30,
        },
        {
            "policy_id": "AUTO-002",
            "content": """
            Liability Only Auto Insurance Policy
            Policy Number: AUTO-002
            Coverage Type: Liability Only
            Coverage Limit: $25,000
            Deductible: $0
            Filing Deadline: 60 days from incident

            This policy covers damage or injury you cause to others in an accident.
            It does NOT cover damage to your own vehicle. Includes bodily injury liability
            and property damage liability. No deductible applies.
            """,
            "coverage_type": "Liability Only",
            "deductible": 0.0,
            "coverage_limit": 25000.0,
            "filing_deadline_days": 60,
        },
        {
            "policy_id": "AUTO-003",
            "content": """
            Premium Auto Insurance Policy
            Policy Number: AUTO-003
            Coverage Type: Full Coverage (Comprehensive + Collision + Uninsured Motorist)
            Coverage Limit: $100,000
            Deductible: $250
            Filing Deadline: 90 days from incident

            This premium policy provides maximum protection including coverage for
            uninsured/underinsured motorists. Lower deductible of $250 applies to all claims.
            Includes roadside assistance, rental car reimbursement, and windshield replacement.
            Extended filing deadline of 90 days.
            """,
            "coverage_type": "Full Coverage",
            "deductible": 250.0,
            "coverage_limit": 100000.0,
            "filing_deadline_days": 90,
        },
    ]

    for policy in sample_policies:
        policies.data.insert(properties=policy)
        print(f"  ✓ Loaded policy: {policy['policy_id']}")

    print(f"\n{len(sample_policies)} sample policies loaded successfully!")


def main():
    """Main function to initialize Weaviate."""
    # Get credentials from environment or prompt
    weaviate_url = os.getenv("WEAVIATE_URL", input("Enter Weaviate Cluster URL: ").strip())
    weaviate_api_key = os.getenv("WEAVIATE_API_KEY", input("Enter Weaviate API Key: ").strip())

    print(f"\nConnecting to Weaviate: {weaviate_url}")

    # Connect to Weaviate Cloud
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=weaviate_url, auth_credentials=Auth.api_key(weaviate_api_key)
    )

    print(f"Connected: {client.is_ready()}\n")

    # Check if collections exist
    existing_collections = [c.name for c in client.collections.list_all().values()]

    if "PolicyDocuments" in existing_collections:
        print("⚠️  PolicyDocuments collection already exists")
        recreate = input("Delete and recreate? (y/N): ").strip().lower()
        if recreate == "y":
            client.collections.delete("PolicyDocuments")
            print("  Deleted PolicyDocuments")

    if "ClaimArtifacts" in existing_collections:
        print("⚠️  ClaimArtifacts collection already exists")
        recreate = input("Delete and recreate? (y/N): ").strip().lower()
        if recreate == "y":
            client.collections.delete("ClaimArtifacts")
            print("  Deleted ClaimArtifacts")

    # Create collections
    if "PolicyDocuments" not in existing_collections or recreate == "y":
        create_collections(client)

    # Load sample data
    load_sample = input("\nLoad sample policies? (Y/n): ").strip().lower()
    if load_sample != "n":
        load_sample_policies(client)

    # Close connection
    client.close()

    print("\n✅ Weaviate initialization complete!")
    print("\nNext steps:")
    print("  1. Store credentials in AWS Secrets Manager")
    print("  2. Continue with Lambda deployment")


if __name__ == "__main__":
    main()
