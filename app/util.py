import json
import re
from datetime import datetime, timedelta

import boto3
import botocore
import pytz as pytz

TODAY = datetime.now(pytz.timezone('US/Pacific'))
TODAY_YYYY_MM_DD = TODAY.strftime('%Y-%m-%d')
TODAY_IS_WEEKEND = TODAY.weekday() >= 4  # Days are 0-6. 4=Friday, 5=Saturday, 6=Sunday, 0=Monday
MIN_TERMINATION_WARNING_YYYY_MM_DD = (TODAY - timedelta(days=3)).strftime('%Y-%m-%d')


def money_to_string(amount):
    return '${:.2f}'.format(amount)


def quote(value):
    return json.dumps(value)


def make_tags_dict(tags_list: list) -> dict:
    return {tag['Key']: tag['Value'] for tag in tags_list}


def set_tag(region_name: str, type_ec2: str, id_name: str, tag_name: str, tag_value: str, dryrun: bool) -> None:
    ec2 = boto3.client('ec2', region_name=region_name)
    print(f'Setting tag {tag_value} on {type_ec2}: {id_name} in region {region_name}')
    if not dryrun:
        response = ec2.create_tags(Resources=[id_name], Tags=[{
            'Key': tag_name,
            'Value': tag_value
        }])
        print(f'Response from create_tags: {str(response)}')


def get_tag_names(tags: dict) -> tuple:
    stop_after_tag_name, terminate_after_tag_name, nagbot_state_tag_name = 'StopAfter', 'TerminateAfter', 'NagbotState'
    for key, value in tags.items():
        if (key.lower()).startswith('stop') and 'after' in (key.lower()):
            stop_after_tag_name = key
        if (key.lower()).startswith('terminate') and 'after' in (key.lower()):
            terminate_after_tag_name = key
        if (key.lower()).startswith('nagbot') and 'state' in (key.lower()):
            nagbot_state_tag_name = key
    return stop_after_tag_name, terminate_after_tag_name, nagbot_state_tag_name


def stop_resource(region_name: str, instance_id: str, dryrun: bool) -> bool:
    print(f'Stopping instance: {str(instance_id)}...')
    ec2 = boto3.client('ec2', region_name=region_name)
    try:
        if not dryrun:
            response = ec2.stop_instances(InstanceIds=[instance_id])
            print(f'Response from stop_instances: {str(response)}')
        return True
    except Exception as e:
        print(f'Failure when calling stop_instances: {str(e)}')
        return False


def has_date_passed(date_to_check, today_date=TODAY_YYYY_MM_DD):
    return date_to_check is not None and date_to_check <= today_date


def generic_url_from_id(region_name, resource_id, resource_type):
    return f'https://{region_name}.console.aws.amazon.com/ec2/v2/home?region={region_name}#{resource_type}:' \
           f'search={resource_id}'


# Checks the snapshot description to see if the snapshot is part of an AMI or AWS backup.
# If the snapshot is part of an AMI, but the AMI has been deregistered, then this function will return False
# for is_ami_snapshot so the remaining snapshot can be cleaned up.
def is_backup_or_ami_snapshot(description: str, registered_amis: list) -> bool:
    is_aws_backup_snapshot = False
    is_ami_snapshot = False
    if "AWS Backup service" in description:
        is_aws_backup_snapshot = True
    elif "Copied for DestinationAmi" in description or "Created by CreateImage" in description:
        # regex matches the first occurrence of ami in the description.
        ami_id = re.search(r'ami-\S*', description).group()
        if ami_id in registered_amis:
            is_ami_snapshot = True

    return is_aws_backup_snapshot, is_ami_snapshot


def is_ami_registered(ami_id: str, region_name: str) -> bool:
    ec2 = boto3.resource('ec2', region_name=region_name)
    is_registered = True
    # Retrieve name of AMI, if ClientError or AttributeError is thrown, the AMI does not exist
    try:
        ec2.Image(ami_id).name
    except (botocore.exceptions.ClientError, AttributeError):
        is_registered = False
    return is_registered
