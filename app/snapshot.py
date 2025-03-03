from dataclasses import dataclass

from app import util
from typing import Union
from .resource import Resource

import boto3


@dataclass
class Snapshot(Resource):
    state: str
    ec2_type: str
    monthly_price: float
    size: float
    is_ami_snapshot: bool
    is_aws_backup_snapshot: bool
    creation_timestamp: str

    # Return the type and state of the Snapshot
    @staticmethod
    def to_string():
        return 'snapshot', 'completed'

    @staticmethod
    def to_header() -> [str]:
        return ['Snapshot ID',
                'Name',
                'State',
                'Creation Timestamp',
                'Terminate After',
                'Contact',
                'Monthly Price',
                'Region Name',
                'Snapshot Type',
                'Size',
                'Is Ami Snapshot',
                'Is AWS Backup Snapshot']

    def to_list(self) -> [str]:
        return [self.resource_id,
                self.name,
                self.state,
                self.creation_timestamp,
                self.terminate_after,
                self.contact,
                self.monthly_price,
                self.region_name,
                self.resource_type,
                self.size,
                self.is_ami_snapshot,
                self.is_aws_backup_snapshot]

    # Get a list of model classes representing important properties of snapshots
    @staticmethod
    def list_resources():
        describe_regions_response = Resource.generic_list_resources()

        snapshots = []

        for region in describe_regions_response['Regions']:
            region_name = region['RegionName']
            ec2 = boto3.client('ec2', region_name=region_name)
            describe_snapshots_response = ec2.describe_snapshots(OwnerIds=["self"])

            # Get a list of registered amis for use later when checking
            # if Snapshot's AMI is registered rather than making expensive API call for AMI Snapshot
            describe_amis_response = ec2.describe_images(Owners=['self'])
            registered_amis = [ami_dictionary["ImageId"] for ami_dictionary in describe_amis_response['Images']]

            for snapshot_dict in describe_snapshots_response['Snapshots']:
                snapshot = Snapshot.build_model(region_name, snapshot_dict, registered_amis)
                snapshots.append(snapshot)
        return snapshots

    @staticmethod
    def build_model(region_name: str, resource_dict: dict, registered_amis: list):
        tags = util.make_tags_dict(resource_dict.get('Tags', []))
        state = resource_dict['State']
        ec2_type = 'snapshot'
        size = resource_dict['VolumeSize']
        snapshot_type = resource_dict['StorageTier']
        resource_id_tag = 'SnapshotId'
        resource_type_tag = 'StorageTier'

        monthly_price = estimate_monthly_snapshot_price(snapshot_type, size)

        snapshot = Resource.build_generic_model(tags, resource_dict, region_name, resource_id_tag, resource_type_tag)
        is_aws_backup_snapshot, is_ami_snapshot = \
            util.is_backup_or_ami_snapshot(resource_dict['Description'], registered_amis)

        return Snapshot(region_name=region_name,
                        resource_id=snapshot.resource_id,
                        state=state,
                        creation_timestamp=str(resource_dict['StartTime']),
                        reason=snapshot.reason,
                        resource_type=snapshot.resource_type,
                        ec2_type=ec2_type,
                        eks_nodegroup_name=snapshot.eks_nodegroup_name,
                        name=snapshot.name,
                        operating_system=snapshot.operating_system,
                        monthly_price=monthly_price,
                        stop_after=snapshot.stop_after,
                        terminate_after=snapshot.terminate_after,
                        nagbot_state=snapshot.nagbot_state,
                        contact=snapshot.contact,
                        stop_after_tag_name=snapshot.stop_after_tag_name,
                        terminate_after_tag_name=snapshot.terminate_after_tag_name,
                        nagbot_state_tag_name=snapshot.nagbot_state_tag_name,
                        size=size,
                        iops=snapshot.iops,
                        throughput=snapshot.throughput,
                        is_ami_snapshot=is_ami_snapshot,
                        is_aws_backup_snapshot=is_aws_backup_snapshot)

    def terminate_resource(self, dryrun: bool) -> Union[None, str]:
        print(f'Deleting snapshot: {str(self.resource_id)}...')
        ec2 = boto3.resource('ec2', region_name=self.region_name)
        snapshot = ec2.Snapshot(self.resource_id)
        try:
            if not dryrun:
                snapshot.delete()  # delete() returns None
            return None
        except Exception as e:
            print(f'Failure when calling snapshot.delete(): {str(e)}')
            return str(e)

    # Check if a snapshot is deletable/terminatable
    def can_be_terminated(self, today_date=util.TODAY_YYYY_MM_DD):
        if self.is_ami_snapshot or self.is_aws_backup_snapshot:
            return False
        return self.state == 'completed' and super().can_be_terminated(today_date)

    # Check if a snapshot is safe to delete/terminate
    def is_safe_to_terminate_after_warning(self, today_date=util.TODAY_YYYY_MM_DD):
        return self.state == 'completed' and super().is_safe_to_terminate_after_warning(today_date)

    # Check if a snapshot is active
    def is_active(self):
        return True if self.state == 'completed' else False

    def get_resource_url(self):
        return util.generic_url_from_id(self.region_name, self.resource_id, 'Snapshots')

    # Create snapshot summary
    def make_resource_summary(self):
        resource_url = self.get_resource_url()
        link = f'<{resource_url}|{self.name}>'
        state = f'State={self.state}'
        line = f'{link}, {state}, Type={self.resource_type}'
        return line

    # Include snapshot in monthly price calculation if available
    def included_in_monthly_price(self):
        if self.state == 'completed' and not self.is_ami_snapshot:
            return True
        else:
            return False


def estimate_monthly_snapshot_price(snapshot_type: str, size: float) -> float:
    standard_monthly_cost = .0525
    archive_monthly_cost = .0131
    return standard_monthly_cost*size if snapshot_type == "standard" else archive_monthly_cost*size
