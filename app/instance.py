from dataclasses import dataclass

from app import parsing
from app import util
from .resource import Resource
from .volume import estimate_monthly_ebs_storage_price
import boto3
from .pricing import PricingData


@dataclass
class Instance(Resource):
    state: str
    ec2_type: str
    monthly_price: float
    monthly_server_price: float
    monthly_storage_price: float
    size: float

    # Return the type and state of the EC2 resource being examined ('instance' and 'running')
    @staticmethod
    def to_string():
        return 'instance', 'running'

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
                util.money_to_string(self.monthly_price),
                util.money_to_string(self.monthly_server_price),
                util.money_to_string(self.monthly_storage_price),
                self.region_name,
                self.resource_type,
                self.reason,
                self.operating_system,
                self.eks_nodegroup_name]

    # Get a list of model classes representing important properties of EC2 instances
    @staticmethod
    def list_resources():
        describe_regions_response = Resource.generic_list_resources()
        instances = []

        for region in describe_regions_response['Regions']:
            region_name = region['RegionName']
            ec2 = boto3.client('ec2', region_name=region_name)
            describe_instances_response = ec2.describe_instances()

            for reservation in describe_instances_response['Reservations']:
                for instance_dict in reservation['Instances']:
                    instance = Instance.build_model(region_name, instance_dict)
                    instances.append(instance)
        return instances

    # Get the info about a single EC2 instance
    @staticmethod
    def build_model(region_name: str, resource_dict: dict):
        tags = util.make_tags_dict(resource_dict.get('Tags', []))

        state = resource_dict['State']['Name']
        ec2_type = 'instance'

        resource_id_tag = 'InstanceId'
        resource_type_tag = 'InstanceType'
        instance = Resource.build_generic_model(tags, resource_dict, region_name, resource_id_tag, resource_type_tag)

        pricing = PricingData()
        monthly_server_price = pricing.lookup_monthly_price(region_name, instance.resource_type,
                                                            instance.operating_system)
        monthly_storage_price = estimate_monthly_ebs_storage_price(region_name,
                                                                   instance.resource_id, 'none', 0, 0, 0)
        monthly_price = (monthly_server_price + monthly_storage_price) if state == 'running' else monthly_storage_price

        size = 0

        return Instance(region_name=region_name,
                        resource_id=instance.resource_id,
                        state=state,
                        reason=instance.reason,
                        resource_type=instance.resource_type,
                        ec2_type=ec2_type,
                        eks_nodegroup_name=instance.eks_nodegroup_name,
                        name=instance.name,
                        operating_system=instance.operating_system,
                        monthly_price=monthly_price,
                        monthly_server_price=monthly_server_price,
                        monthly_storage_price=monthly_storage_price,
                        stop_after=instance.stop_after,
                        terminate_after=instance.terminate_after,
                        nagbot_state=instance.nagbot_state,
                        contact=instance.contact,
                        stop_after_tag_name=instance.stop_after_tag_name,
                        terminate_after_tag_name=instance.terminate_after_tag_name,
                        nagbot_state_tag_name=instance.nagbot_state_tag_name,
                        size=size,
                        iops=instance.iops,
                        throughput=instance.throughput)

    # Terminate an EC2 instance
    def terminate_resource(self, dryrun: bool) -> bool:
        print(f'Terminating instance: {str(self.resource_id)}...')
        ec2 = boto3.client('ec2', region_name=self.region_name)
        try:
            if not dryrun:
                response = ec2.terminate_instances(InstanceIds=[self.resource_id])
                print(f'Response from terminate_instances: {str(response)}')
            return True
        except Exception as e:
            print(f'Failure when calling terminate_instances: {str(e)}')
            return False

    # Instance with no stop after tag should be stopped immediately
    def is_stoppable_without_warning(self, is_weekend):
        parsed_date: parsing.ParsedDate = parsing.parse_date_tag(self.stop_after)
        return self.state == 'running' and parsed_date.expiry_date is None and \
            ((not parsed_date.on_weekends) or (parsed_date.on_weekends and is_weekend))

    def is_stoppable(self, today_date, is_weekend):
        parsed_date: parsing.ParsedDate = parsing.parse_date_tag(self.stop_after)
        return self.state == 'running' and (
            # Treat unspecified "Stop after" dates as being in the past
            (parsed_date.expiry_date is None and not parsed_date.on_weekends)
            or (parsed_date.on_weekends and is_weekend)
            or (parsed_date.expiry_date is not None and today_date >= parsed_date.expiry_date))

    def can_be_stopped(self, today_date=util.TODAY_YYYY_MM_DD, is_weekend=util.TODAY_IS_WEEKEND):
        return not (len(self.eks_nodegroup_name) > 0) and (
                self.is_stoppable(today_date, is_weekend) or self.is_stoppable_without_warning(is_weekend))

    # Check if an instance is stoppable after warning
    def is_safe_to_stop(self, today_date=util.TODAY_YYYY_MM_DD, is_weekend=util.TODAY_IS_WEEKEND):
        warning_date = parsing.parse_date_tag(self.stop_after).warning_date
        return not (len(self.eks_nodegroup_name) > 0) and (
                (self.is_stoppable_without_warning(is_weekend)) or
                (self.is_stoppable(today_date, is_weekend) and util.has_date_passed(warning_date)))

    # Check if an instance is terminatable
    def can_be_terminated(self, today_date=util.TODAY_YYYY_MM_DD):
        return self.state == 'stopped' and not (len(self.eks_nodegroup_name) > 0) and \
               super().can_be_terminated(today_date)

    # Check if an instance is safe to terminate as warning period is passed too
    def is_safe_to_terminate_after_warning(self, today_date=util.TODAY_YYYY_MM_DD):
        return self.state == 'stopped' and not (len(self.eks_nodegroup_name) > 0) and \
               super().is_safe_to_terminate_after_warning(today_date)

    # Check if an instance is active
    def is_active(self):
        return self.state == 'running'

    # Create instance summary
    def make_resource_summary(self):
        resource_url = util.generic_url_from_id(self.region_name, self.resource_id, 'Instances')
        link = f'<{resource_url}|{self.name}>'
        if self.reason:
            state = f'State=({self.state}, "{self.reason}")'
        else:
            state = f'State={self.state}'
        line = f'{link}, {state}, Type={self.resource_type}'
        return line

    # Include all instances in monthly price calculation
    @staticmethod
    def included_in_monthly_price():
        return True

    @staticmethod
    def has_stop_status():
        return True
