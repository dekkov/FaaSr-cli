#!/usr/bin/env python3

import argparse
import json
import os
import sys
import requests
import boto3
import subprocess

def parse_arguments():
    parser = argparse.ArgumentParser(description='Trigger FaaSr function from JSON file')
    parser.add_argument('--workflow-file', required=True,
                      help='Path to the workflow JSON file')
    return parser.parse_args()

def read_workflow_file(file_path):
    """Read and parse the workflow JSON file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Workflow file {file_path} not found")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in workflow file {file_path}")
        sys.exit(1)

def get_credentials():
    """Get credentials from environment variables."""
    return {
        "My_GitHub_Account_TOKEN": os.getenv('GITHUB_TOKEN'),
        "My_Minio_Bucket_ACCESS_KEY": os.getenv('MINIO_ACCESS_KEY'),
        "My_Minio_Bucket_SECRET_KEY": os.getenv('MINIO_SECRET_KEY'),
        "My_OW_Account_API_KEY": os.getenv('OW_API_KEY', ''),
        "My_Lambda_Account_ACCESS_KEY": os.getenv('AWS_ACCESS_KEY_ID', ''),
        "My_Lambda_Account_SECRET_KEY": os.getenv('AWS_SECRET_ACCESS_KEY', ''),
    }

def trigger_github_actions(workflow_data, function_name):
    """Trigger a GitHub Actions workflow."""
    # Get function data
    func_data = workflow_data['FunctionList'][function_name]
    server_name = func_data['FaaSServer']
    server_config = workflow_data['ComputeServers'][server_name]
    
    # Get GitHub credentials and repo info
    pat = os.getenv('GITHUB_TOKEN')  # Use actual token from environment
    username = server_config['UserName']
    reponame = server_config['ActionRepoName']
    repo = f"{username}/{reponame}"
    branch = server_config['Branch']
    
    # Use function name directly for workflow name
    workflow_name = f"{function_name}.yml"

    
    # Create payload with credentials
    payload = workflow_data.copy()
    if '_workflow_file' in payload:
        del payload['_workflow_file']
    payload.update(get_credentials())
    
    # Hide credentials in payload for GitHub Actions
    for server_key in payload['ComputeServers']:
        server = payload['ComputeServers'][server_key]
        if server['FaaSType'] == 'GitHubActions':
            server['Token'] = f"{server_key}_TOKEN"
        elif server['FaaSType'] == 'Lambda':
            server['AccessKey'] = f"{server_key}_ACCESS_KEY"
            server['SecretKey'] = f"{server_key}_SECRET_KEY"
        elif server['FaaSType'] == 'OpenWhisk':
            server['API.key'] = f"{server_key}_API_KEY"
    
    for store_key in payload['DataStores']:
        store = payload['DataStores'][store_key]
        store['AccessKey'] = f"{store_key}_ACCESS_KEY"
        store['SecretKey'] = f"{store_key}_SECRET_KEY"
    
    # Prepare request
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_name}/dispatches"
    print(f"Debug: Request URL: {url}")
    
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    body = {
        "ref": branch,
        "inputs": {
            "PAYLOAD": json.dumps(payload)
        }
    }
    
    # Send request
    try:
        response = requests.post(url, headers=headers, json=body)
        if response.status_code == 204:
            print(f"Successfully triggered GitHub Actions workflow: {workflow_name}")
        else:
            print(f"Error triggering GitHub Actions workflow: {response.status_code} - {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error triggering GitHub Actions workflow: {str(e)}")
        sys.exit(1)


def create_secret_payload(workflow_data):
    """
    Create a secret payload that combines all necessary credentials and the complete workflow configuration.
    This payload will be stored as a GitHub secret and used by the deployed functions.
    """
    # Get all required credentials
    credentials = {
        "My_GitHub_Account_TOKEN": get_github_token(),
        "My_Minio_Bucket_ACCESS_KEY": os.getenv('MINIO_ACCESS_KEY'),
        "My_Minio_Bucket_SECRET_KEY": os.getenv('MINIO_SECRET_KEY'),
        "My_OW_Account_API_KEY": os.getenv('OW_API_KEY', ''),
        "My_Lambda_Account_ACCESS_KEY": os.getenv('AWS_ACCESS_KEY_ID', ''),
        "My_Lambda_Account_SECRET_KEY": os.getenv('AWS_SECRET_ACCESS_KEY', ''),
    }
    
    # Create the complete workflow payload by merging the original workflow with credentials
    # Remove the _workflow_file field as it's not part of the FaaSr schema
    complete_payload = workflow_data.copy()
    if '_workflow_file' in complete_payload:
        del complete_payload['_workflow_file']
    
    # Add credentials to the payload
    complete_payload.update(credentials)
    
    return json.dumps(complete_payload)

def get_github_token():
    # Get GitHub PAT from environment variable
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)
    return token

def trigger_lambda(workflow_data, function_name):
    """Trigger an AWS Lambda function."""
    # Get function data
    func_data = workflow_data['FunctionList'][function_name]
    server_name = func_data['FaaSServer']
    server_config = workflow_data['ComputeServers'][server_name]
    
    # Get AWS credentials from environment variables (same as deploy script)
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_region = server_config.get('Region', 'us-east-1')
    
    # Use function name directly
    lambda_function_name = function_name
    
    # Create payload with credentials (same as R implementation)
    payload = workflow_data.copy()
    if '_workflow_file' in payload:
        del payload['_workflow_file']
    
    credentials = get_credentials()
    payload.update(credentials)
    
    # Create Lambda client
    try:
        lambda_client = boto3.client(
            'lambda',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region
        )
    except Exception as e:
        print(f"Error creating Lambda client: {str(e)}")
        sys.exit(1)
    
    # Invoke function asynchronously
    try:
        print(f"Debug: Invoking Lambda function asynchronously: {lambda_function_name}")
        response = lambda_client.invoke(
            FunctionName=lambda_function_name,
            InvocationType='Event',  # Asynchronous invocation - doesn't wait for response
            Payload=json.dumps(payload)
        )
        
        print(f"Debug: Lambda response status: {response.get('StatusCode')}")
        
        # For asynchronous invocations, status 202 means successfully queued
        if response['StatusCode'] == 202:
            print(f"✓ Successfully triggered Lambda function: {lambda_function_name}")
            
        else:
            print(f"✗ Lambda function invocation failed with status: {response['StatusCode']}")
            if 'Payload' in response:
                payload_content = response['Payload'].read()
                if payload_content:
                    print(f"Response payload: {payload_content.decode('utf-8')}")
            sys.exit(1)
            
    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"✗ Error: Lambda function '{lambda_function_name}' not found")
        print(f"  Make sure the function exists in region '{aws_region}'")
        print(f"  You can list functions with: aws lambda list-functions --region {aws_region}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error triggering Lambda function: {str(e)}")
        sys.exit(1)

def trigger_openwhisk(workflow_data, function_name):
    pass

def main():
    args = parse_arguments()
    workflow_data = read_workflow_file(args.workflow_file)
    
    # Store the workflow file path
    workflow_data['_workflow_file'] = args.workflow_file
    
    # Get the function to invoke
    function_invoke = workflow_data.get('FunctionInvoke')
    if not function_invoke:
        print("Error: No FunctionInvoke specified in workflow file")
        sys.exit(1)
    
    if function_invoke not in workflow_data['FunctionList']:
        print(f"Error: FunctionInvoke '{function_invoke}' not found in FunctionList")
        sys.exit(1)
    
    # Get function data
    func_data = workflow_data['FunctionList'][function_invoke]
    server_name = func_data['FaaSServer']
    server_config = workflow_data['ComputeServers'][server_name]
    faas_type = server_config['FaaSType'].lower()
    
    print(f"Triggering function '{function_invoke}' on {faas_type}...")
    
    # Trigger based on FaaS type
    if faas_type == 'githubactions':
        trigger_github_actions(workflow_data, function_invoke)
    elif faas_type == 'lambda':
        trigger_lambda(workflow_data, function_invoke)
    elif faas_type == 'openwhisk':
        trigger_openwhisk(workflow_data, function_invoke)
    else:
        print(f"Error: Unsupported FaaS type: {faas_type}")
        sys.exit(1)
    
    print("Function trigger completed successfully!")

if __name__ == '__main__':
    main() 