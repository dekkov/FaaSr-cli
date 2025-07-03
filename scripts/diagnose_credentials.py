#!/usr/bin/env python3

import os
import json
import sys

def check_environment_variables():
    """Check if all required environment variables are set."""
    required_vars = {
        'MINIO_ACCESS_KEY': 'MinIO access key for data storage',
        'MINIO_SECRET_KEY': 'MinIO secret key for data storage', 
        'AWS_ACCESS_KEY_ID': 'AWS access key for Lambda execution',
        'AWS_SECRET_ACCESS_KEY': 'AWS secret key for Lambda execution',
        'AWS_LAMBDA_ROLE_ARN': 'AWS Lambda execution role ARN',
        'GITHUB_TOKEN': 'GitHub personal access token'
    }
    
    print("=== Environment Variables Check ===")
    missing_vars = []
    for var_name, description in required_vars.items():
        value = os.getenv(var_name)
        if value:
            print(f"✓ {var_name}: SET ({description})")
            # Show first/last 4 characters for security
            if len(value) > 8:
                print(f"  Value: {value[:4]}...{value[-4:]}")
            else:
                print(f"  Value: {'*' * len(value)}")
        else:
            print(f"✗ {var_name}: MISSING ({description})")
            missing_vars.append(var_name)
    
    return missing_vars

def validate_workflow_file(workflow_path):
    """Validate workflow file configuration."""
    print(f"\n=== Workflow File Check: {workflow_path} ===")
    
    try:
        with open(workflow_path, 'r') as f:
            workflow = json.load(f)
        
        # Check DataStores configuration
        if 'DataStores' in workflow:
            for store_name, store_config in workflow['DataStores'].items():
                print(f"\nDataStore: {store_name}")
                print(f"  Endpoint: {store_config.get('Endpoint', 'NOT_SET')}")
                print(f"  Bucket: {store_config.get('Bucket', 'NOT_SET')}")
                print(f"  AccessKey: {store_config.get('AccessKey', 'NOT_SET')}")
                print(f"  SecretKey: {store_config.get('SecretKey', 'NOT_SET')}")
        
        # Check ComputeServers configuration
        if 'ComputeServers' in workflow:
            for server_name, server_config in workflow['ComputeServers'].items():
                print(f"\nComputeServer: {server_name}")
                print(f"  FaaSType: {server_config.get('FaaSType', 'NOT_SET')}")
                if server_config.get('FaaSType') == 'Lambda':
                    print(f"  Region: {server_config.get('Region', 'NOT_SET')}")
                    print(f"  AccessKey: {server_config.get('AccessKey', 'NOT_SET')}")
                    print(f"  SecretKey: {server_config.get('SecretKey', 'NOT_SET')}")
        
        return workflow
        
    except FileNotFoundError:
        print(f"✗ Workflow file not found: {workflow_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in workflow file: {e}")
        return None

def check_credential_mapping(workflow):
    """Check if credential mapping is correct."""
    print(f"\n=== Credential Mapping Check ===")
    
    if not workflow:
        return
    
    # Expected credential mappings
    expected_mappings = {
        'My_Minio_Bucket_ACCESS_KEY': os.getenv('MINIO_ACCESS_KEY'),
        'My_Minio_Bucket_SECRET_KEY': os.getenv('MINIO_SECRET_KEY'),
        'My_Lambda_Account_ACCESS_KEY': os.getenv('AWS_ACCESS_KEY_ID'),
        'My_Lambda_Account_SECRET_KEY': os.getenv('AWS_SECRET_ACCESS_KEY'),
    }
    
    for key, env_value in expected_mappings.items():
        if env_value:
            print(f"✓ {key} -> Environment variable SET")
        else:
            print(f"✗ {key} -> Environment variable MISSING")

def main():
    print("FaaSr Credential Diagnostics")
    print("=" * 50)
    
    # Check environment variables
    missing_vars = check_environment_variables()
    
    # Check workflow file if provided
    workflow_file = sys.argv[1] if len(sys.argv) > 1 else 'payload_aws.json'
    workflow = validate_workflow_file(workflow_file)
    
    # Check credential mapping
    check_credential_mapping(workflow)
    
    # Summary
    print(f"\n=== Summary ===")
    if missing_vars:
        print(f"✗ Missing environment variables: {', '.join(missing_vars)}")
        print("  Set these variables before deploying:")
        for var in missing_vars:
            print(f"    export {var}='your_value_here'")
    else:
        print("✓ All environment variables are set")
    
    if not workflow:
        print("✗ Workflow file has issues")
    else:
        print("✓ Workflow file is valid")
    
    print("\nNext steps:")
    print("1. Fix any missing environment variables")
    print("2. Verify AWS credentials have proper permissions")
    print("3. Check MinIO endpoint accessibility")
    print("4. Re-deploy with: python scripts/deploy_functions.py --workflow-file <your_file>")

if __name__ == '__main__':
    main() 