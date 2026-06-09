import boto3
import json
from functools import lru_cache
import os

@lru_cache(maxsize=None)
def get_aws_session():
    """
    Creates and returns a boto3 session.
    It automatically searches for credentials in the following order:
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    - Shared credential file (~/.aws/credentials)
    - IAM role for Amazon EC2 instances
    """
    try:
        return boto3.Session()
    except Exception as e:
        print(f"Error creating boto3 session: {e}")
        return None

@lru_cache(maxsize=None)
def get_aws_client(service_name, region_name=None):
    """Creates and returns a boto3 client, caching clients per region."""
    session = get_aws_session()
    if not session:
        return None
    try:
        return session.client(service_name, region_name=region_name)
    except Exception as e:
        print(f"Error creating boto3 client for {service_name} in {region_name}: {e}")
        return None

def load_aws_credentials():
    """
    Loads AWS credentials using the boto3 session's credential provider chain.
    This will check environment variables before falling back to the default profile.
    """
    session = get_aws_session()
    if not session:
        return None
    try:
        credentials = session.get_credentials()
        return credentials.get_frozen_credentials()
    except Exception as e:
        print(f"Error loading AWS credentials: {e}")
        return None

def list_all_rds_dbs(region_name=None):
    """Lists all RDS databases in the account across regions (or a specific region if provided) and saves them to a file."""
    try:
        if region_name:
            all_regions = [region_name]
            print(f"Scanning for RDS instances in specific region: {region_name}...")
        else:
            ec2_client = get_aws_client('ec2', region_name='us-east-1')
            if not ec2_client:
                return []
            all_regions = [region['RegionName'] for region in ec2_client.describe_regions()['Regions']]
            print(f"Scanning for RDS instances across all available AWS regions...")

        db_list = []
        for r_name in all_regions:
            try:
                print(f"Checking region: {r_name}...")
                rds_client = get_aws_client('rds', region_name=r_name)
                if not rds_client:
                    print(f"Skipping region {r_name} due to client creation error.")
                    continue
                
                paginator = rds_client.get_paginator('describe_db_instances')
                for page in paginator.paginate():
                    for instance in page['DBInstances']:
                        db_list.append({
                            'DBInstanceIdentifier': instance.get('DBInstanceIdentifier'),
                            'Engine': instance.get('Engine'),
                            'Region': r_name,
                            'DBParameterGroups': [group['DBParameterGroupName'] for group in instance.get('DBParameterGroups', [])]
                        })
            except Exception as region_error:
                if "AccessDenied" in str(region_error) or "UnauthorizedOperation" in str(region_error):
                    print(f"Skipping region {r_name} due to a permissions error.")
                    continue
                else:
                    print(f"An unexpected error occurred in region {r_name}, skipping: {region_error}")
                    continue

        with open('db_list.txt', 'w') as f:
            json.dump(db_list, f, indent=4)
            
        return db_list
    except Exception as e:
        import traceback
        print(f"Error listing RDS databases: {e}")
        print(traceback.format_exc())
        return []

def get_rds_metadata(instance_id, region_name='us-east-1'):
    """Fetches RDS instance metadata."""
    rds_client = get_aws_client('rds', region_name=region_name)
    if not rds_client:
        return None
    try:
        response = rds_client.describe_db_instances(DBInstanceIdentifier=instance_id)
        
        if 'DBInstances' in response and len(response['DBInstances']) > 0:
            return response['DBInstances'][0]
        else:
            return None
    except Exception as e:
        print(f"Error fetching RDS metadata for instance {instance_id}: {e}")
        return None

def get_parameter_group_settings(group_name, region_name='us-east-1'):
    """Fetches all parameters of a given DB parameter group."""
    rds_client = get_aws_client('rds', region_name=region_name)
    if not rds_client:
        return None
    try:
        paginator = rds_client.get_paginator('describe_db_parameters')
        parameters = []
        for page in paginator.paginate(DBParameterGroupName=group_name):
            parameters.extend(page['Parameters'])
        return parameters
    except Exception as e:
        print(f"Error fetching parameters for group {group_name}: {e}")
        return None

def get_specific_db_parameter(group_name, region_name, parameter_name):
    """Fetches a specific parameter's value from a DB parameter group."""
    rds_client = get_aws_client('rds', region_name=region_name)
    if not rds_client:
        return None
    try:
        # describe_db_parameters can filter by parameter name
        response = rds_client.describe_db_parameters(
            DBParameterGroupName=group_name,
            Source='user' # We only care about user-modified parameters for this
        )
        for param in response.get('Parameters', []):
            if param.get('ParameterName') == parameter_name:
                return param
        # If not found in user-modified, check the system defaults
        response = rds_client.describe_db_parameters(
            DBParameterGroupName=group_name,
            Source='system'
        )
        for param in response.get('Parameters', []):
            if param.get('ParameterName') == parameter_name:
                return param
        return None
    except Exception as e:
        print(f"Error fetching parameter {parameter_name} for group {group_name}: {e}")
        return None