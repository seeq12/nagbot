__author__ = "Stephen Rosenthal"
__version__ = "1.8.0"
__license__ = "MIT"

import argparse
import re
import sys
from datetime import datetime

from . import gdocs
from . import parsing
from . import sqaws
from . import sqslack
from .sqaws import money_to_string, Instances, Volumes

TODAY = datetime.today()
TODAY_YYYY_MM_DD = TODAY.strftime('%Y-%m-%d')

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
        instances = Instances.list_resources()
        volumes = Volumes.list_resources()

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

        resource_types = [Instances, Volumes]
        for resource_type in resource_types:
            ec2_type = resource_type.to_string()
            resources = resource_type.list_resources()
            resources_to_terminate = sorted(list(r for r in resources if r.is_terminatable(r, TODAY_YYYY_MM_DD) and
                                                 (len(r.eks_nodegroup_name) < 0)), key=lambda r: r.name)
            resources_to_stop = list(r for r in resources if sqaws.is_stoppable(r, ec2_type, TODAY_YYYY_MM_DD))

            if len(resources_to_terminate) > 0:
                terminate_msg = 'The following %d _stopped_ {}s are due to be *TERMINATED*, ' \
                                'based on the "Terminate after" tag:\n'.format(ec2_type) \
                                % len(resources_to_terminate)
                for r in resources_to_terminate:
                    contact = sqslack.lookup_user_by_email(r.contact)
                    terminate_msg += r.make_resource_summmary(r) + \
                        ', "Terminate after"={}, "Monthly Price"={}, Contact={}\n'\
                        .format(r.terminate_after, money_to_string(r.monthly_price), contact)
                    sqaws.set_tag(r.region_name, ec2_type, r.resource_id, r.terminate_after_tag_name,
                                  parsing.add_warning_to_tag(r.terminate_after, TODAY_YYYY_MM_DD), dryrun=dryrun)
            else:
                terminate_msg = 'No {}s are due to be terminated at this time.\n'\
                    .format(ec2_type)
            sqslack.send_message(channel, terminate_msg)

            if len(resources_to_stop) > 0:
                stop_msg = 'The following %d _running_ {}s are due to be *STOPPED*, ' \
                           'based on the "Stop after" tag:\n'.format(ec2_type) \
                           % len(resources_to_stop)
                for r in resources_to_stop:
                    contact = sqslack.lookup_user_by_email(r.contact)
                    stop_msg += r.make_resource_summary(r) + \
                        ', "Stop after"={}, "Monthly Price"={}, Contact={}\n' \
                        .format(r.stop_after, money_to_string(r.monthly_price), contact)
                    sqaws.set_tag(r.region_name, ec2_type, r.resource_id, r.stop_after_tag_name,
                                  parsing.add_warning_to_tag(r.stop_after, TODAY_YYYY_MM_DD, replace=True),
                                  dryrun=dryrun)
            else:
                stop_msg = 'No {}s are due to be stopped at this time.\n'.format(ec2_type)
            sqslack.send_message(channel, stop_msg)

    def notify(self, channel, dryrun):
        try:
            self.notify_internal(channel, dryrun)
        except Exception as e:
            sqslack.send_message(channel, "Nagbot failed to run the 'notify' command: " + str(e))
            raise e

    @staticmethod
    def execute_internal(channel, dryrun):
        resource_types = [Instances, Volumes]
        for resource_type in resource_types:
            ec2_type = resource_type.to_string()
            resources = resource_type.list_resources()

            # Only terminate resources which still meet the criteria for terminating, AND were warned several times
            resources_to_terminate = list(r for r in resources if r.is_terminatable(r, TODAY_YYYY_MM_DD) and
                                          r.is_safe_to_terminate(r, TODAY_YYYY_MM_DD))

            # Only stop resources which still meet the criteria for stopping, AND were warned recently
            resources_to_stop = list(r for r in resources if sqaws.is_stoppable(r, ec2_type, TODAY_YYYY_MM_DD) and
                                     sqaws.is_safe_to_stop(r, ec2_type, TODAY_YYYY_MM_DD))

            if len(resources_to_terminate) > 0:
                message = 'I terminated the following {}s: '.format(ec2_type)
                for r in resources_to_terminate:
                    contact = sqslack.lookup_user_by_email(r.contact)
                    message = message + r.make_resource_summary(r) + \
                        ', "Terminate after"={}, "Monthly Price"={}, Contact={}\n'\
                        .format(r.terminate_after, money_to_string(r.monthly_price), contact)
                    r.terminate_resource(r.region_name, r.resource_id, dryrun=dryrun)
                sqslack.send_message(channel, message)
            else:
                sqslack.send_message(channel, 'No {}s were terminated today.'
                                     .format(ec2_type))

            if len(resources_to_stop) > 0:
                message = 'I stopped the following {}s: '.format(ec2_type)
                for r in resources_to_stop:
                    contact = sqslack.lookup_user_by_email(r.contact)
                    message = message + r.make_resource_summary(r) \
                        + ', "Stop after"={}, "Monthly Price"={}, Contact={}\n' \
                        .format(r.stop_after, money_to_string(r.monthly_price), contact)
                    sqaws.stop_resource(r.region_name, r.resource_id, dryrun=dryrun)
                    sqaws.set_tag(r.region_name, ec2_type, r.resource_id, r.nagbot_state_tag_name, 'Stopped on '
                                  + TODAY_YYYY_MM_DD, dryrun=dryrun)
                sqslack.send_message(channel, message)
            else:
                sqslack.send_message(channel, 'No {}s were stopped today.'.format(ec2_type))

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
