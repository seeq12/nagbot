__author__ = "Stephen Rosenthal"
__version__ = "1.8.0"
__license__ = "MIT"

import argparse
import re
import sys
from datetime import datetime, timedelta

from . import gdocs
from . import parsing
from . import new_sqaws
from . import sqslack
from .new_sqaws import money_to_string
from .pricing import PricingData

TERMINATION_WARNING_DAYS = 3

TODAY = datetime.today()
TODAY_YYYY_MM_DD = TODAY.strftime('%Y-%m-%d')
TODAY_IS_WEEKEND = TODAY.weekday() >= 4  # Days are 0-6. 4=Friday, 5=Saturday, 6=Sunday, 0=Monday
YESTERDAY_YYYY_MM_DD = (TODAY - timedelta(days=1)).strftime('%Y-%m-%d')
MIN_TERMINATION_WARNING_YYYY_MM_DD = (TODAY - timedelta(days=3)).strftime('%Y-%m-%d')

"""
PREREQUISITES:
1. An AWS account with credentials set up in a standard place (environment variables, home directory, etc.)
2. The AWS credentials must have access to the EC2 APIs "describe_regions" and "describe_instances"
3. PIP dependencies specified in requirements.txt.
4. Environment variables
   * "SLACK_BOT_TOKEN" containing a token allowing messages to be posted to Slack.
   * "GDOCS_SERVICE_ACCOUNT_FILENAME" containing the name of the google sheet
"""


class Nagbot(object):
    @staticmethod
    def notify_internal(channel, dryrun):
        pricing = PricingData()
        blank_instance = new_sqaws.Instance(r_name='', r_id='', state='', reason='', r_type='', name='', eks_name='',
                                            os='', s_after='', t_after='', n_state='', contact='', m_price='',
                                            m_server_price='', m_storage_price='', s_after_tag='', t_after_tag='',
                                            n_state_tag='')
        blank_volume = new_sqaws.Volume(r_name='', r_id='', state='', r_type='', size='', iops='', throughput='',
                                        name='', os='', t_after='', contact='', m_price='', t_after_tag='')

        instances = new_sqaws.Instance.list_resources(blank_instance, pricing=pricing)
        volumes = new_sqaws.Volume.list_resources(blank_volume, pricing=pricing)

        num_running_instances = sum(1 for i in instances if i.state == 'running')
        num_total_instances = len(instances)
        running_monthly_cost = money_to_string(sum(i.monthly_price for i in instances))

        num_running_volumes = sum(1 for v in volumes if v.state == 'available')
        num_total_volumes = len(volumes)
        running_volumes_monthly_cost = money_to_string(sum(v.monthly_price for v in volumes if v.state == 'available'))

        summary_msg = "Hi, I'm Nagbot v{} :wink: ".format(__version__)
        summary_msg += "My job is to make sure we don't forget about unwanted AWS resources and waste money!\n"
        summary_msg += "We have {} running EC2 instances right now and {} total.\n".format(num_running_instances,
                                                                                           num_total_instances)
        summary_msg += "If we continue to run these instances all month, it would cost {}.\n" \
            .format(running_monthly_cost)
        summary_msg += "We also have {} unattached EBS volumes right now and {} total.\n".format(num_running_volumes,
                                                                                                 num_total_volumes)
        summary_msg += "If we continue to run the unattached volumes all month, it would cost {}.\n" \
            .format(running_volumes_monthly_cost)

        # Collect all the data to a Google Sheet
        try:
            header = instances[0].to_header()
            body = [i.to_list() for i in instances]
            spreadsheet_url = gdocs.write_to_spreadsheet([header] + body)
            summary_msg += '\nIf you want to see all the details, I wrote them to a spreadsheet at ' + spreadsheet_url
            print('Wrote data to Google sheet at URL ' + spreadsheet_url)
        except Exception as e:
            print('Failed to write data to Google sheet: ' + str(e))

        sqslack.send_message(channel, summary_msg)

        # First, sort and investigate instances
        instances = sorted((i for i in instances if len(i.eks_nodegroup_name) < 0), key=lambda i: i.name)

        instances_to_terminate = new_sqaws.Instance.get_terminatable_resources(blank_instance, instances)
        if len(instances_to_terminate) > 0:
            terminate_msg = 'The following %d _stopped_ instances are due to be *TERMINATED*, ' \
                            'based on the "Terminate after" tag:\n' % len(instances_to_terminate)
            for i in instances_to_terminate:
                contact = sqslack.lookup_user_by_email(i.contact)
                terminate_msg += new_sqaws.Instance.make_resource_summary(i, i) + \
                    ', "Terminate after"={}, "Monthly Price"={}, Contact={}\n' \
                    .format(i.terminate_after, money_to_string(i.monthly_price), contact)
                new_sqaws.set_tag(i.region_name, 'instance', i.instance_id, i.terminate_after_tag_name,
                                  parsing.add_warning_to_tag(i.terminate_after, TODAY_YYYY_MM_DD), dryrun=dryrun)
        else:
            terminate_msg = 'No instances are due to be terminated at this time.\n'
        sqslack.send_message(channel, terminate_msg)

        instances_to_stop = new_sqaws.Instance.get_stoppable_resources(blank_instance, instances)
        if len(instances_to_stop) > 0:
            stop_msg = 'The following %d _running_ instances are due to be *STOPPED*, ' \
                       'based on the "Stop after" tag:\n' % len(instances_to_stop)
            for i in instances_to_stop:
                contact = sqslack.lookup_user_by_email(i.contact)
                stop_msg += new_sqaws.Instance.make_resource_summary(i, i) + \
                    ', "Stop after"={}, "Monthly Price"={}, Contact={}\n' \
                    .format(i.stop_after, money_to_string(i.monthly_price), contact)
                new_sqaws.set_tag(i.region_name, 'instance', i.instance_id, i.stop_after_tag_name,
                                  parsing.add_warning_to_tag(i.stop_after, TODAY_YYYY_MM_DD, replace=True),
                                  dryrun=dryrun)
        else:
            stop_msg = 'No instances are due to be stopped at this time.\n'
        sqslack.send_message(channel, stop_msg)

        # Then, sort and investigate EBS volumes
        volumes = sorted((v for v in volumes), key=lambda v: v.name)

        volumes_to_delete = new_sqaws.Volume.get_terminatable_resources(blank_volume, volumes)
        if len(volumes_to_delete) > 0:
            delete_msg = 'The following %d volumes are due to be *DELETED*, ' \
                         'based on the "Terminate after" tag:\n' % len(volumes_to_delete)
            for v in volumes_to_delete:
                contact = sqslack.lookup_user_by_email(v.contact)
                delete_msg += new_sqaws.Volume.make_resource_summary(blank_volume, v) + \
                    ', "Terminate after"={}, "Monthly Price"={}, Contact={}\n' \
                    .format(v.terminate_after, money_to_string(v.monthly_price), contact)
                new_sqaws.set_tag(v.region_name, 'volume', v.volume_id, v.terminate_after_tag_name,
                                  parsing.add_warning_to_tag(v.terminate_after, TODAY_YYYY_MM_DD, replace=True),
                                  dryrun=dryrun)
        else:
            delete_msg = 'No volumes are due to be deleted at this time.\n'
        sqslack.send_message(channel, delete_msg)

    def notify(self, channel, dryrun):
        try:
            self.notify_internal(channel, dryrun)
        except Exception as e:
            sqslack.send_message(channel, "Nagbot failed to run the 'notify' command: " + str(e))
            raise e

    @staticmethod
    def execute_internal(channel, dryrun):
        pricing = PricingData()
        blank_instance = new_sqaws.Instance(r_name='', r_id='', state='', reason='', r_type='', name='', eks_name='',
                                            os='', s_after='', t_after='', n_state='', contact='', m_price='',
                                            m_server_price='', m_storage_price='', s_after_tag='', t_after_tag='',
                                            n_state_tag='')
        blank_volume = new_sqaws.Volume(r_name='', r_id='', state='', r_type='', size='', iops='', throughput='',
                                        name='', os='', t_after='', contact='', m_price='', t_after_tag='')

        instances = new_sqaws.Instance.list_resources(blank_instance, pricing=pricing)
        volumes = new_sqaws.Volume.list_resources(blank_volume, pricing=pricing)

        # Only terminate instances which still meet the criteria for terminating, AND were warned several times
        instances_to_terminate = new_sqaws.Instance.get_terminatable_resources(instances, instances)
        instances_to_terminate = [i for i in instances_to_terminate if
                                  new_sqaws.Instance.is_safe_to_terminate(blank_instance, i)]

        # Only delete volumes which still meet the criteria for deleting, AND were warned several times
        volumes_to_delete = new_sqaws.Volume.get_terminatable_resources(volumes, volumes)
        volumes_to_delete = [v for v in volumes_to_delete if new_sqaws.Volume.is_safe_to_terminate(blank_volume, v)]

        # Only stop instances which still meet the criteria for stopping, AND were warned recently
        instances_to_stop = new_sqaws.Instance.get_stoppable_resources(instances, instances)
        instances_to_stop = [i for i in instances_to_stop if new_sqaws.Instance.is_safe_to_stop(blank_instance, i)]

        if len(instances_to_terminate) > 0:
            message = 'I terminated the following instances: '
            for i in instances_to_terminate:
                contact = sqslack.lookup_user_by_email(i.contact)
                message = message + new_sqaws.Instance.make_resource_summary(blank_instance, i) \
                    + ', "Terminate after"={}, "Monthly Price"={}, Contact={}\n' \
                    .format(i.terminate_after, money_to_string(i.monthly_price), contact)
                new_sqaws.Instance.terminate_resource(i, i.region_name, i.instance_id, dryrun=dryrun)
            sqslack.send_message(channel, message)
        else:
            sqslack.send_message(channel, 'No instances were terminated today.')

        if len(volumes_to_delete) > 0:
            message = 'I deleted the following volumes: '
            for v in volumes_to_delete:
                contact = sqslack.lookup_user_by_email(v.contact)
                message = message + new_sqaws.Volume.make_resource_summary(blank_volume, v) \
                    + ', "Terminate after"={}, "Monthly Price"={}, Contact={}\n' \
                    .format(v.terminate_after, money_to_string(v.monthly_price), contact)
                new_sqaws.Volume.terminate_resource(v, v.region_name, v.volume_id, dryrun=dryrun)
            sqslack.send_message(channel, message)
        else:
            sqslack.send_message(channel, 'No volumes were deleted today.')

        if len(instances_to_stop) > 0:
            message = 'I stopped the following instances: '
            for i in instances_to_stop:
                contact = sqslack.lookup_user_by_email(i.contact)
                message = message + new_sqaws.Instance.make_resource_summary(blank_instance, i) \
                    + ', "Stop after"={}, "Monthly Price"={}, Contact={}\n' \
                    .format(i.stop_after, money_to_string(i.monthly_price), contact)
                new_sqaws.Instance.stop_instance(i.region_name, i.instance_id, dryrun=dryrun)
                new_sqaws.set_tag(i.region_name, 'instance', i.instance_id, i.nagbot_state_tag_name, 'Stopped on ' +
                                  TODAY_YYYY_MM_DD, dryrun=dryrun)
            sqslack.send_message(channel, message)
        else:
            sqslack.send_message(channel, 'No instances were stopped today.')

    def execute(self, channel, dryrun):
        try:
            self.execute_internal(channel, dryrun)
        except Exception as e:
            sqslack.send_message(channel, "Nagbot failed to run the 'execute' command: " + str(e))
            raise e


def main(args):
    """
    Entry point for the application
    """
    channel = args.channel
    mode = args.mode
    dryrun = args.dryrun

    if re.fullmatch(r'#[A-Za-z\d-]+', channel) is None:
        print('Unexpected channel format "%s", should look like #random or #testing' % channel)
        sys.exit(1)
    print('Destination Slack channel is: ' + channel)

    nagbot = Nagbot()

    if mode.lower() == 'notify':
        nagbot.notify(channel, dryrun)
    elif mode.lower() == 'execute':
        nagbot.execute(channel, dryrun)
    else:
        print('Unexpected mode "%s", should be "notify" or "execute"' % mode)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", help="Mode, either 'notify' or 'execute'. "
                     "In 'notify' mode, a notification is posted to Slack. "
                     "In 'execute' mode, instances are stopped or terminated and volumes are deleted.")

    parser.add_argument(
        "-c",
        "--channel",
        action="store",
        default='#nagbot-testing',
        help="Which Slack channel to publish to")

    parser.add_argument(
        "--dryrun",
        action="store_true",
        default=False,
        help="If specified, don't actually take the specified actions")

    parsed_args = parser.parse_args()
    main(parsed_args)
