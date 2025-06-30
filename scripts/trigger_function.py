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
    
    # Get the JSON file prefix for workflow name
    workflow_file = workflow_data.get('_workflow_file', 'workflow.json')
    json_prefix = os.path.splitext(os.path.basename(workflow_file))[0]
    workflow_name = f"{json_prefix}_{function_name}.yml"

    
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
    
    # Get the JSON file prefix for function name
    workflow_file = workflow_data.get('_workflow_file', 'workflow.json')
    json_prefix = os.path.splitext(os.path.basename(workflow_file))[0]
    lambda_function_name = f"{json_prefix}_{function_name}"
    
    # Debug output
    print(f"Debug: JSON file: {workflow_file}")
    print(f"Debug: JSON prefix: {json_prefix}")
    print(f"Debug: Function name: {function_name}")
    print(f"Debug: Lambda function name: {lambda_function_name}")
    print(f"Debug: AWS Region: {aws_region}")
    print(f"Debug: AWS Access Key: {aws_access_key[:8] if aws_access_key else 'None'}...")
    
    # Validate credentials
    if not aws_access_key or not aws_secret_key:
        print("Error: AWS credentials not found in environment variables")
        print("Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables")
        sys.exit(1)
    
    # Create payload with credentials
    payload = workflow_data.copy()
    if '_workflow_file' in payload:
        del payload['_workflow_file']
    payload.update(get_credentials())
    
    # Create Lambda client
    try:
        lambda_client = boto3.client(
            'lambda',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region
        )
        print(f"Debug: Lambda client created successfully")
    except Exception as e:
        print(f"Error creating Lambda client: {str(e)}")
        sys.exit(1)
    
    # Invoke function
    try:
        print(f"Debug: Invoking Lambda function: {lambda_function_name}")
        response = lambda_client.invoke(
            FunctionName=lambda_function_name,
            InvocationType='Event',  # Async invocation
            Payload=json.dumps(payload)
        )
        
        print(f"Debug: Lambda response status: {response.get('StatusCode')}")
        print(f"Debug: Lambda response: {response}")
        
        if response['StatusCode'] == 202:
            print(f"Successfully triggered Lambda function: {lambda_function_name}")
        else:
            print(f"Error triggering Lambda function: {response['StatusCode']}")
            if 'FunctionError' in response:
                print(f"Function error: {response['FunctionError']}")
            sys.exit(1)
    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"Error: Lambda function '{lambda_function_name}' not found")
        print(f"Make sure the function exists in region '{aws_region}'")
        print(f"You can deploy it using: python scripts/deploy_functions.py --workflow-file {workflow_file}")
        sys.exit(1)
    except lambda_client.exceptions.InvalidParameterValueException as e:
        print(f"Error: Invalid parameter - {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"Error triggering Lambda function: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        sys.exit(1)

def trigger_openwhisk(workflow_data, function_name):
    """Trigger an OpenWhisk action."""
    # Get function data
    func_data = workflow_data['FunctionList'][function_name]
    server_name = func_data['FaaSServer']
    server_config = workflow_data['ComputeServers'][server_name]
    
    # Get OpenWhisk configuration
    endpoint = server_config['Endpoint']
    namespace = server_config['Namespace']
    ssl = server_config.get('SSL', 'True').lower() == 'true'
    
    # Get the JSON file prefix for action name
    workflow_file = workflow_data.get('_workflow_file', 'workflow.json')
    json_prefix = os.path.splitext(os.path.basename(workflow_file))[0]
    action_name = f"{json_prefix}_{function_name}"
    
    # Create payload with credentials
    payload = workflow_data.copy()
    if '_workflow_file' in payload:
        del payload['_workflow_file']
    payload.update(get_credentials())
    
    # Prepare URL
    if not endpoint.startswith(('http://', 'https://')):
        endpoint = f"https://{endpoint}"
    url = f"{endpoint}/api/v1/namespaces/{namespace}/actions/{action_name}?blocking=false&result=false"
    
    # Send request
    try:
        response = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            verify=ssl
        )
        if response.status_code in [200, 202]:
            print(f"Successfully triggered OpenWhisk action: {action_name}")
        else:
            print(f"Error triggering OpenWhisk action: {response.status_code} - {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"Error triggering OpenWhisk action: {str(e)}")
        sys.exit(1)

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