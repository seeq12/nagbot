from dataclasses import dataclass

import boto3
from .pricing import PricingData
from datetime import datetime, timedelta

from . import parsing

TODAY = datetime.today()
TODAY_IS_WEEKEND = TODAY.weekday() >= 4  # Days are 0-6. 4=Friday, 5=Saturday, 6=Sunday, 0=Monday
MIN_TERMINATION_WARNING_YYYY_MM_DD = (TODAY - timedelta(days=3)).strftime('%Y-%m-%d')


# Convert floating point dollars to a readable string
def money_to_string(amount):
    return '${:.2f}'.format(amount)


# Quote a string
def quote(value):
    return '"' + value + '"'


# Convert the tags list returned from the EC2 API to a dictionary from tag name to tag value
def make_tags_dict(tags_list: list) -> dict:
    tags = dict()
    for tag in tags_list:
        tags[tag['Key']] = tag['Value']
    return tags


# Set a tag on an EC2 resource
def set_tag(region_name: str, type_ec2: str, id_name: str, tag_name: str, tag_value: str, dryrun: bool) -> None:
    ec2 = boto3.client('ec2', region_name=region_name)
    print(f'Setting tag {tag_value} on {type_ec2}: {id_name} in region {region_name}')
    if not dryrun:
        response = ec2.create_tags(Resources=[id_name], Tags=[{
            'Key': tag_name,
            'Value': tag_value
        }])
        print(f'Response from create_tags: {str(response)}')


# Get 'stop after', 'terminate after', and 'Nagbot state' tag names in an EC2 instance, regardless of formatting
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


# Estimate the monthly cost of an EBS storage volume; pricing estimations based on region us-east-1
def estimate_monthly_ebs_storage_price(region_name: str, instance_id: str, volume_type: str, size: float, iops: float,
                                       throughput: float) -> float:
    if instance_id.startswith('i'):
        ec2_resource = boto3.resource('ec2', region_name=region_name)
        total_gb = sum([v.size for v in ec2_resource.Instance(instance_id).volumes.all()])
        return total_gb * 0.1  # Assume EBS costs $0.1/GB/month when calculating for attached volumes

    if 'gp3' in volume_type:  # gp3 type storage depends on storage, IOPS, and throughput
        cost = size * 0.08
        if iops > 3000:
            provisioned_iops = iops - 3000
            cost = cost + (provisioned_iops * 0.005)
        if throughput > 125:
            provisioned_throughput = throughput - 125
            cost = cost + (provisioned_throughput * 0.04)
        return cost
    else:  # Assume EBS costs $0.1/GB/month, true as of Dec 2021 for gp2 type storage
        return size * 0.1


# Stop an EC2 resource - currently, only instances should be able to be stopped
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


# Check if a resource is stoppable - currently, only instances should be stoppable
def is_stoppable(resource, ec2_type, today_date, is_weekend=TODAY_IS_WEEKEND):
    if not ec2_type == 'instance':
        return False

    parsed_date: parsing.ParsedDate = parsing.parse_date_tag(resource.stop_after)
    return resource.state == 'running' and (
        # Treat unspecified "Stop after" dates as being in the past
        (parsed_date.expiry_date is None and not parsed_date.on_weekends)
        or (parsed_date.on_weekends and is_weekend)
        or (parsed_date.expiry_date is not None and today_date >= parsed_date.expiry_date))


# Check if a resource is safe to stop - currently, only instances should be safe to stop
def is_safe_to_stop(resource, ec2_type, today_date, is_weekend=TODAY_IS_WEEKEND):
    if not ec2_type == 'instance':
        return False

    warning_date = parsing.parse_date_tag(resource.stop_after).warning_date
    return is_stoppable(resource, ec2_type, today_date, is_weekend=is_weekend) \
        and warning_date is not None and warning_date <= today_date


# Class representing generic EC2 instances
class Instances:
    # Return the type of EC2 resource being examined ('instance')
    @staticmethod
    def to_string() -> str:
        return 'instance'

    # Get a list of model classes representing important properties of EC2 instances
    @staticmethod
    def list_resources():
        ec2 = boto3.client('ec2', region_name='us-west-2')

        describe_regions_response = ec2.describe_regions()
        instances = []

        print('Checking all AWS regions...')
        for region in describe_regions_response['Regions']:
            region_name = region['RegionName']
            ec2 = boto3.client('ec2', region_name=region_name)

            describe_instances_response = ec2.describe_instances()

            for reservation in describe_instances_response['Reservations']:
                for instance_dict in reservation['Instances']:
                    instance = Instances.build_model(region_name, instance_dict)
                    instances.append(instance)

        return instances

    # Get the info about a single EC2 instance
    @staticmethod
    def build_model(region_name: str, resource_dict: dict):
        tags = make_tags_dict(resource_dict.get('Tags', []))

        resource_id = resource_dict['InstanceId']
        state = resource_dict['State']['Name']
        reason = resource_dict.get('StateTransitionReason', '')
        resource_type = resource_dict['InstanceType']
        eks_nodegroup_name = tags.get('eks:nodegroup-name', '')
        name = tags.get('Name', eks_nodegroup_name)
        platform = resource_dict.get('Platform', '')
        operating_system = ('Windows' if platform == 'windows' else 'Linux')

        pricing = PricingData()
        monthly_server_price = pricing.lookup_monthly_price(region_name, resource_type, operating_system)
        monthly_storage_price = estimate_monthly_ebs_storage_price(region_name, resource_id, 'none', 0, 0, 0)
        monthly_price = (monthly_server_price + monthly_storage_price) if state == 'running' else monthly_storage_price

        stop_after_tag_name, terminate_after_tag_name, nagbot_state_tag_name = get_tag_names(tags)
        stop_after = tags.get(stop_after_tag_name, '')
        terminate_after = tags.get(terminate_after_tag_name, '')
        nagbot_state = tags.get(nagbot_state_tag_name, '')
        contact = tags.get('Contact', '')

        return Instance(region_name=region_name,
                        resource_id=resource_id,
                        state=state,
                        reason=reason,
                        resource_type=resource_type,
                        eks_nodegroup_name=eks_nodegroup_name,
                        name=name,
                        operating_system=operating_system,
                        monthly_price=monthly_price,
                        monthly_server_price=monthly_server_price,
                        monthly_storage_price=monthly_storage_price,
                        stop_after=stop_after,
                        terminate_after=terminate_after,
                        nagbot_state=nagbot_state,
                        contact=contact,
                        stop_after_tag_name=stop_after_tag_name,
                        terminate_after_tag_name=terminate_after_tag_name,
                        nagbot_state_tag_name=nagbot_state_tag_name,
                        size=0,
                        iops=0,
                        throughput=0)


# Class representing a single EC2 instance
@dataclass
class Instance:
    region_name: str
    resource_id: str
    state: str
    reason: str
    resource_type: str
    name: str
    eks_nodegroup_name: str
    operating_system: str
    stop_after: str
    terminate_after: str
    nagbot_state: str
    contact: str
    monthly_price: float
    monthly_server_price: float
    monthly_storage_price: float
    stop_after_tag_name: str
    terminate_after_tag_name: str
    nagbot_state_tag_name: str
    size: float
    iops: float
    throughput: float

    @staticmethod
    def to_header() -> [str]:
        return ['Instance ID',
                'Name',
                'State',
                'Stop After',
                'Terminate After',
                'Contact',
                'Nagbot State',
                'Monthly Price',
                'Monthly Server Price',
                'Monthly Storage Price',
                'Region Name',
                'Instance Type',
                'Reason',
                'OS',
                'EKS Nodegroup']

    def to_list(self) -> [str]:
        return [self.resource_id,
                self.name,
                self.state,
                self.stop_after,
                self.terminate_after,
                self.contact,
                self.nagbot_state,
                money_to_string(self.monthly_price),
                money_to_string(self.monthly_server_price),
                money_to_string(self.monthly_storage_price),
                self.region_name,
                self.resource_type,
                self.reason,
                self.operating_system,
                self.eks_nodegroup_name]

    # Terminate an EC2 instance
    @staticmethod
    def terminate_resource(region_name: str, resource_id: str, dryrun: bool) -> bool:
        print(f'Terminating instance: {str(resource_id)}...')
        ec2 = boto3.client('ec2', region_name=region_name)
        try:
            if not dryrun:
                response = ec2.terminate_instances(InstanceIds=[resource_id])
                print(f'Response from terminate_instances: {str(response)}')
            return True
        except Exception as e:
            print(f'Failure when calling terminate_instances: {str(e)}')
            return False

    # Check if an instance is terminatable
    @staticmethod
    def is_terminatable(resource, today_date):
        parsed_date: parsing.ParsedDate = parsing.parse_date_tag(resource.terminate_after)

        # For now, we'll only terminate instances which have an explicit 'Terminate after' tag
        return resource.state == 'stopped' and (
            (parsed_date.expiry_date is not None and today_date >= parsed_date.expiry_date))

    # Check if an instance is safe to terminate
    @staticmethod
    def is_safe_to_terminate(resource, today_date):
        warning_date = parsing.parse_date_tag(resource.terminate_after).warning_date
        return Instance.is_terminatable(resource, today_date) and warning_date is not None and warning_date <= \
            MIN_TERMINATION_WARNING_YYYY_MM_DD

    # Create instance summary
    @staticmethod
    def make_resource_summary(resource):
        instance_id = resource.resource_id
        instance_url = Instance.url_from_id(resource.region_name, instance_id)
        link = '<{}|{}>'.format(instance_url, resource.name)
        if resource.reason:
            state = 'State=({}, "{}")'.format(resource.state, resource.reason)
        else:
            state = 'State={}'.format(resource.state)
        line = '{}, {}, Type={}'.format(link, state, resource.resource_type)
        return line

    # Create instance url
    @staticmethod
    def url_from_id(region_name, resource_id):
        return 'https://{}.console.aws.amazon.com/ec2/v2/home?region={}#Instances:search={}'.format(region_name,
                                                                                                    region_name,
                                                                                                    resource_id)


# Class representing generic EBS volumes
class Volumes:
    # Return the type of EC2 resource being examined ('volume')
    @staticmethod
    def to_string() -> str:
        return 'volume'

    # Get a list of model classes representing important properties of EBS volumes
    @staticmethod
    def list_resources():
        ec2 = boto3.client('ec2', region_name='us-west-2')

        describe_regions_response = ec2.describe_regions()
        volumes = []

        print('Checking all AWS regions...')
        for region in describe_regions_response['Regions']:
            region_name = region['RegionName']
            ec2 = boto3.client('ec2', region_name=region_name)

            describe_volumes_response = ec2.describe_volumes()

            for volume_dict in describe_volumes_response['Volumes']:
                volume = Volumes.build_model(region_name, volume_dict)
                volumes.append(volume)

        return volumes

    # Get the info about a single EBS volume
    @staticmethod
    def build_model(region_name: str, resource_dict: dict):
        tags = make_tags_dict(resource_dict.get('Tags', []))

        resource_id = resource_dict['VolumeId']
        state = resource_dict['State']
        resource_type = resource_dict['VolumeType']
        name = tags.get('Name', '')
        platform = resource_dict.get('Platform', '')
        operating_system = ('Windows' if platform == 'windows' else 'Linux')
        size = resource_dict['Size']
        iops = resource_dict.get('Iops', '')
        throughput = resource_dict.get('Throughput', '')

        monthly_price = estimate_monthly_ebs_storage_price(region_name, resource_id, resource_type, size, iops,
                                                           throughput)

        terminate_after_tag_name = 'TerminateAfter'
        for key, value in tags.items():
            if (key.lower()).startswith('terminate') and 'after' in (key.lower()):
                terminate_after_tag_name = key
        terminate_after = tags.get(terminate_after_tag_name, '')
        contact = tags.get('Contact', '')

        return Volume(region_name=region_name,
                      resource_id=resource_id,
                      state=state,
                      reason='',
                      resource_type=resource_type,
                      eks_nodegroup_name='',
                      name=name,
                      operating_system=operating_system,
                      monthly_price=monthly_price,
                      monthly_server_price=0,
                      monthly_storage_price=0,
                      stop_after='',
                      terminate_after=terminate_after,
                      nagbot_state='',
                      contact=contact,
                      stop_after_tag_name='',
                      terminate_after_tag_name=terminate_after_tag_name,
                      nagbot_state_tag_name='',
                      size=size,
                      iops=iops,
                      throughput=throughput)


# Class representing a single EBS volume
@dataclass
class Volume:
    region_name: str
    resource_id: str
    state: str
    reason: str
    resource_type: str
    name: str
    eks_nodegroup_name: str
    operating_system: str
    stop_after: str
    terminate_after: str
    nagbot_state: str
    contact: str
    monthly_price: float
    monthly_server_price: float
    monthly_storage_price: float
    stop_after_tag_name: str
    terminate_after_tag_name: str
    nagbot_state_tag_name: str
    size: float
    iops: float
    throughput: float

    @staticmethod
    def to_header() -> [str]:
        return ['Volume ID',
                'Name',
                'State',
                'Terminate After',
                'Contact',
                'Monthly Price',
                'Region Name',
                'Volume Type',
                'OS'
                'Size',
                'IOPS',
                'Throughput']

    def to_list(self) -> [str]:
        return [self.resource_id,
                self.name,
                self.state,
                self.terminate_after,
                self.contact,
                self.monthly_price,
                self.region_name,
                self.resource_type,
                self.operating_system,
                self.size,
                self.iops,
                self.throughput]

    # Delete/terminate an EBS volume
    @staticmethod
    def terminate_resource(region_name: str, resource_id: str, dryrun: bool) -> bool:
        print(f'Deleting volume: {str(resource_id)}...')
        ec2 = boto3.client('ec2', region_name=region_name)
        try:
            if not dryrun:
                response = ec2.delete_volume(VolumeId=resource_id)
                print(f'Response from delete_volumes: {str(response)}')
            return True
        except Exception as e:
            print(f'Failure when calling delete_volumes: {str(e)}')
            return False

    # Check if a volume is deletable/terminatable
    @staticmethod
    def is_terminatable(resource, today_date):
        parsed_date: parsing.ParsedDate = parsing.parse_date_tag(resource.terminate_after)

        # For now, we'll only terminate volumes which have an explicit 'Terminate after' tag
        return resource.state == 'available' and (
            (parsed_date.expiry_date is not None and today_date >= parsed_date.expiry_date))

    # Check if a volume is safe to delete/terminate
    @staticmethod
    def is_safe_to_terminate(resource, today_date):
        warning_date = parsing.parse_date_tag(resource.terminate_after).warning_date
        return Volume.is_terminatable(resource, today_date) and warning_date is not None and warning_date <= \
            MIN_TERMINATION_WARNING_YYYY_MM_DD

    # Create volume summary
    @staticmethod
    def make_resource_summary(resource):
        volume_id = resource.volume_id
        volume_url = Volume.url_from_id(resource.region_name, volume_id)
        link = '<{}|{}>'.format(volume_url, resource.name)
        state = 'State={}'.format(resource.state)
        line = '{}, {}, Type={}'.format(link, state, resource.volume_type)
        return line

    # Create volume url
    @staticmethod
    def url_from_id(region_name, resource_id):
        return 'https://{}.console.aws.amazon.com/ec2/v2/home?region={}#Volumes:search={}'.format(region_name,
                                                                                                  region_name,
                                                                                                  resource_id)
