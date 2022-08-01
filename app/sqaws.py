from dataclasses import dataclass

import boto3
from .pricing import PricingData
import abc
from datetime import datetime, timedelta

from . import parsing

TERMINATION_WARNING_DAYS = 3

TODAY = datetime.today()
TODAY_YYYY_MM_DD = TODAY.strftime('%Y-%m-%d')
TODAY_IS_WEEKEND = TODAY.weekday() >= 4  # Days are 0-6. 4=Friday, 5=Saturday, 6=Sunday, 0=Monday
YESTERDAY_YYYY_MM_DD = (TODAY - timedelta(days=1)).strftime('%Y-%m-%d')
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


# Parent class representing any EC2 resource shows basic shared interface amongst all EC2 resources NagBot deals with
class Resource(abc.ABC):
    def __init__(self, r_name, r_id, state, r_type, name, os, t_after, contact, m_price, t_after_tag):
        self.region_name = r_name
        self.resource_id = r_id
        self.state = state
        self.resource_type = r_type
        self.name = name
        self.operating_system = os
        self.terminate_after = t_after
        self.contact = contact
        self.monthly_price = m_price
        self.terminate_after_tag_name = t_after_tag

    @abc.abstractmethod
    def list_resources(self, pricing: PricingData):
        print('This method gets a list of model classes representing important properties of EC2 resources.')

    @abc.abstractmethod
    def build_model(self, region_name: str, pricing: PricingData, resource_dict: dict):
        print('This method gets the info about a single EC2 resource.')

    @abc.abstractmethod
    def terminate_resource(self, region_name: str, resource_id: str, dryrun: bool):
        print('This method terminates/deletes an EC2 resource.')

    @abc.abstractmethod
    def get_terminatable_resources(self, resources):
        print('This method returns a list of terminatable/deletable EC2 resources.')

    @abc.abstractmethod
    def is_terminatable(self, resource):
        print('This method returns True if a resource is terminatable/deletable and False if not.')

    @abc.abstractmethod
    def is_safe_to_terminate(self, resource):
        print('This method returns True if a resource can be safely terminated/deleted and False if it cannot.')

    @abc.abstractmethod
    def make_resource_summary(self, resource):
        print('This method creates a summary of the given EC2 resource.')

    @abc.abstractmethod
    def url_from_id(self, region_name, resource_id):
        print('This method returns the URL of the given EC2 resource using its id.')


# Child class representing EC2 instances
class Instance(Resource):
    def __init__(self, r_name, r_id, state, reason, r_type, name, eks_name, os, s_after, t_after, n_state, contact,
                 m_price, m_server_price, m_storage_price, s_after_tag, t_after_tag, n_state_tag):
        super().__init__(r_name, r_id, state, r_type, name, os, t_after, contact, m_price, t_after_tag)
        self.reason = reason
        self.eks_nodegroup_name = eks_name
        self.stop_after = s_after
        self.nagbot_state = n_state
        self.monthly_server_price = m_server_price
        self.monthly_storage_price = m_storage_price
        self.stop_after_tag_name = s_after_tag
        self.nagbot_state_tag_name = n_state_tag

    @dataclass
    class Instance:
        region_name: str
        instance_id: str
        state: str
        reason: str
        instance_type: str
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
            return [self.instance_id,
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
                    self.instance_type,
                    self.reason,
                    self.operating_system,
                    self.eks_nodegroup_name]

    # Get a list of model classes representing important properties of EC2 instances
    def list_resources(self, pricing: PricingData):
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
                    instance = self.build_model(region_name, pricing, instance_dict)
                    instances.append(instance)

        return instances

    # Get the info about a single EC2 instance
    def build_model(self, region_name: str, pricing: PricingData, resource_dict: dict):
        tags = make_tags_dict(resource_dict.get('Tags', []))

        resource_id = resource_dict['InstanceId']
        state = resource_dict['State']['Name']
        reason = resource_dict.get('StateTransitionReason', '')
        resource_type = resource_dict['InstanceType']
        eks_nodegroup_name = tags.get('eks:nodegroup-name', '')
        name = tags.get('Name', eks_nodegroup_name)
        platform = resource_dict.get('Platform', '')
        operating_system = ('Windows' if platform == 'windows' else 'Linux')

        monthly_server_price = pricing.lookup_monthly_price(region_name, resource_type, operating_system)
        monthly_storage_price = estimate_monthly_ebs_storage_price(region_name, resource_id, 'none', 0, 0, 0)
        monthly_price = (monthly_server_price + monthly_storage_price) if state == 'running' else monthly_storage_price

        stop_after_tag_name, terminate_after_tag_name, nagbot_state_tag_name = get_tag_names(tags)
        stop_after = tags.get(stop_after_tag_name, '')
        terminate_after = tags.get(terminate_after_tag_name, '')
        nagbot_state = tags.get(nagbot_state_tag_name, '')
        contact = tags.get('Contact', '')

        self.region_name = region_name
        self.resource_id = resource_id
        self.state = state
        self.reason = reason
        self.resource_type = resource_type
        self.name = name
        self.eks_nodegroup_name = eks_nodegroup_name
        self.operating_system = operating_system
        self.stop_after = stop_after
        self.terminate_after = terminate_after
        self.nagbot_state = nagbot_state
        self.contact = contact
        self.monthly_price = monthly_price
        self.monthly_server_price = monthly_server_price
        self.monthly_storage_price = monthly_storage_price
        self.stop_after_tag_name = stop_after_tag_name
        self.terminate_after_tag_name = terminate_after_tag_name
        self.nagbot_state_tag_name = nagbot_state_tag_name

        return self.Instance(region_name=region_name,
                             instance_id=resource_id,
                             state=state,
                             reason=reason,
                             instance_type=resource_type,
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
                             nagbot_state_tag_name=nagbot_state_tag_name)

    # Stop an EC2 instance
    @staticmethod
    def stop_instance(region_name: str, instance_id: str, dryrun: bool) -> bool:
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

    # Terminate an EC2 instance
    def terminate_resource(self, region_name: str, resource_id: str, dryrun: bool) -> bool:
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

    # Create a list of all stoppable instances
    def get_stoppable_resources(self, instances):
        return list(i for i in instances if self.is_stoppable(i))

    # Create a list of all terminatable instances
    def get_terminatable_resources(self, resources):
        return list(i for i in resources if self.is_terminatable(i))

    # Check if an instance is stoppable
    @staticmethod
    def is_stoppable(instance, is_weekend=TODAY_IS_WEEKEND):
        parsed_date: parsing.ParsedDate = parsing.parse_date_tag(instance.stop_after)

        return instance.state == 'running' and (
            # Treat unspecified "Stop after" dates as being in the past
            (parsed_date.expiry_date is None and not parsed_date.on_weekends)
            or (parsed_date.on_weekends and is_weekend)
            or (parsed_date.expiry_date is not None and TODAY_YYYY_MM_DD >= parsed_date.expiry_date))

    # Check if an instance is terminatable
    def is_terminatable(self, resource):
        parsed_date: parsing.ParsedDate = parsing.parse_date_tag(resource.terminate_after)

        # For now, we'll only terminate instances which have an explicit 'Terminate after' tag
        return resource.state == 'stopped' and (
            (parsed_date.expiry_date is not None and TODAY_YYYY_MM_DD >= parsed_date.expiry_date))

    # Check if an instance is safe to stop
    def is_safe_to_stop(self, instance, is_weekend=TODAY_IS_WEEKEND):
        warning_date = parsing.parse_date_tag(instance.stop_after).warning_date
        return self.is_stoppable(instance, is_weekend=is_weekend) \
            and warning_date is not None and warning_date <= TODAY_YYYY_MM_DD

    # Check if an instance is safe to terminate
    def is_safe_to_terminate(self, resource):
        warning_date = parsing.parse_date_tag(resource.terminate_after).warning_date
        return self.is_terminatable(resource) and warning_date is not None and warning_date <= \
            MIN_TERMINATION_WARNING_YYYY_MM_DD

    # Create instance summary
    def make_resource_summary(self, resource):
        instance_id = resource.resource_id
        instance_url = self.url_from_id(resource.region_name, instance_id)
        link = '<{}|{}>'.format(instance_url, resource.name)
        if resource.reason:
            state = 'State=({}, "{}")'.format(resource.state, resource.reason)
        else:
            state = 'State={}'.format(resource.state)
        line = '{}, {}, Type={}'.format(link, state, resource.resource_type)
        return line

    # Create instance url
    def url_from_id(self, region_name, resource_id):
        return 'https://{}.console.aws.amazon.com/ec2/v2/home?region={}#Instances:search={}'.format(region_name,
                                                                                                    region_name,
                                                                                                    resource_id)


# Child class representing EBS volumes
class Volume(Resource):
    def __init__(self, r_name, r_id, state, r_type, size, iops, throughput, name, os, t_after, contact, m_price,
                 t_after_tag):
        super().__init__(r_name, r_id, state, r_type, name, os, t_after, contact, m_price, t_after_tag)
        self.size = size
        self.iops = iops
        self.throughput = throughput

    @dataclass
    class Volume:
        region_name: str
        volume_id: str
        state: str
        volume_type: str
        size: float
        iops: float
        throughput: float
        name: str
        operating_system: str
        terminate_after: str
        contact: str
        monthly_price: float
        terminate_after_tag_name: str

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
            return [self.volume_id,
                    self.name,
                    self.state,
                    self.terminate_after,
                    self.contact,
                    self.monthly_price,
                    self.region_name,
                    self.volume_type,
                    self.operating_system,
                    self.size,
                    self.iops,
                    self.throughput]

    # Get a list of model classes representing important properties of EBS volumes
    def list_resources(self, pricing: PricingData):
        ec2 = boto3.client('ec2', region_name='us-west-2')

        describe_regions_response = ec2.describe_regions()
        volumes = []

        print('Checking all AWS regions...')
        for region in describe_regions_response['Regions']:
            region_name = region['RegionName']
            ec2 = boto3.client('ec2', region_name=region_name)

            describe_volumes_response = ec2.describe_volumes()

            for volume_dict in describe_volumes_response['Volumes']:
                volume = self.build_model(region_name, pricing, volume_dict)
                volumes.append(volume)

        return volumes

    # Get the info about a single EBS volume
    def build_model(self, region_name: str, pricing: PricingData, resource_dict: dict) -> Volume:
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

        self.region_name = region_name
        self.resource_id = resource_id
        self.state = state
        self.resource_type = resource_type
        self.size = size
        self.iops = iops
        self.throughput = throughput
        self.name = name
        self.operating_system = operating_system
        self.terminate_after = terminate_after
        self.contact = contact
        self.monthly_price = monthly_price
        self.terminate_after_tag_name = terminate_after_tag_name

        return self.Volume(region_name=region_name,
                           volume_id=resource_id,
                           state=state,
                           volume_type=resource_type,
                           name=name,
                           operating_system=operating_system,
                           monthly_price=monthly_price,
                           terminate_after=terminate_after,
                           contact=contact,
                           terminate_after_tag_name=terminate_after_tag_name,
                           size=size,
                           iops=iops,
                           throughput=throughput)

    # Delete an EBS volume
    def terminate_resource(self, region_name: str, resource_id: str, dryrun: bool) -> bool:
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

    # Create a list of all deletable volumes
    def get_terminatable_resources(self, resources):
        return list(v for v in resources if self.is_terminatable(v))

    # Check if a volume is deletable
    def is_terminatable(self, resource):
        parsed_date: parsing.ParsedDate = parsing.parse_date_tag(resource.terminate_after)

        # For now, we'll only terminate volumes which have an explicit 'Terminate after' tag
        return resource.state == 'available' and (
            (parsed_date.expiry_date is not None and TODAY_YYYY_MM_DD >= parsed_date.expiry_date))

    # Check if a volume is safe to delete
    def is_safe_to_terminate(self, resource):
        warning_date = parsing.parse_date_tag(resource.terminate_after).warning_date
        return self.is_terminatable(resource) and warning_date is not None and warning_date <= \
            MIN_TERMINATION_WARNING_YYYY_MM_DD

    # Create volume summary
    def make_resource_summary(self, resource):
        volume_id = resource.volume_id
        volume_url = self.url_from_id(resource.region_name, volume_id)
        link = '<{}|{}>'.format(volume_url, resource.name)
        state = 'State={}'.format(resource.state)
        line = '{}, {}, Type={}'.format(link, state, resource.volume_type)
        return line

    # Create volume url
    def url_from_id(self, region_name, resource_id):
        return 'https://{}.console.aws.amazon.com/ec2/v2/home?region={}#Volumes:search={}'.format(region_name,
                                                                                                  region_name,
                                                                                                  resource_id)
