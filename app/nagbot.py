__author__ = "Stephen Rosenthal"
__version__ = "1.7.0"
__license__ = "MIT"

import argparse
import re
import sys
from datetime import datetime, timedelta

from . import gdocs
from . import parsing
from . import sqaws
from . import sqslack

TODAY = datetime.today()
TODAY_YYYY_MM_DD = TODAY.strftime('%Y-%m-%d')
TODAY_IS_WEEKEND = TODAY.weekday() >= 4  # Days are 0-6. 4=Friday, 5=Saturday, 6=Sunday, 0=Monday
YESTERDAY_YYYY_MM_DD = (TODAY - timedelta(days=1)).strftime('%Y-%m-%d')
MIN_TERMINATION_WARNING_YYYY_MM_DD = (TODAY - timedelta(days=3)).strftime('%Y-%m-%d')

AUTO_STOP_AFTER_DAYS = 3
AUTO_STOP_AFTER_DAY_YYYY_MM_DD = (TODAY + timedelta(days=AUTO_STOP_AFTER_DAYS)).strftime('%Y-%m-%d')
AUTO_TERMINATE_AFTER_DAYS = 14
AUTO_TERMINATE_AFTER_DAY_YYYY_MM_DD = (TODAY + timedelta(days=AUTO_TERMINATE_AFTER_DAYS)).strftime('%Y-%m-%d')

"""
PREREQUISITES:
1. An AWS account with credentials set up in a standard place (environment variables, home directory, etc.)
2. The AWS credentials must have access to the EC2 APIs "describe_regions" and "describe_instances"
3. PIP dependencies specified in requirements.txt.
4. Environment variable "SLACK_BOT_TOKEN" containing a token allowing messages to be posted to Slack.
"""


class Nagbot(object):

    def _tag_instances_internal(self, channel):
        instances = sqaws.list_ec2_instances()
        instances_to_tag = get_taggable_instances(instances)

        if len(instances_to_tag) > 0:
            message = 'I tagged the following instances to be stopped or terminated: '
            for i in instances_to_tag:
                contact = sqslack.lookup_user_by_email(i.contact)
                message += f'\n{make_instance_summary(i)}, Contact={contact}'
                tag_instance(i)
            sqslack.send_message(channel, message)
        else:
            sqslack.send_message(channel, 'No instances were tagged today.')

    def tag_instances(self, channel):
        try:
            self._tag_instances_internal(channel)
        except Exception as e:
            sqslack.send_message(channel, f"Nagbot failed to run the 'tag_instances' command: {str(e)}")
            raise e

    def _notify_internal(self, channel):
        instances = sqaws.list_ec2_instances()

        num_running_instances = sum(1 for i in instances if i.state == 'running')
        num_total_instances = sum(1 for i in instances)
        running_monthly_cost = money_to_string(sum(i.monthly_price for i in instances))

        summary_msg = f"Hi, I'm Nagbot v{__version__} :wink: My job is to make sure we don't forget " \
                      f"about unwanted AWS servers and waste money!\n"
        summary_msg += f"We have {num_running_instances} running EC2 instances right now " \
                       f"and {num_total_instances} total.\n"
        summary_msg += f"If we continue to run these instances all month, it would cost {running_monthly_cost}.\n"

        # Collect all of the data to a Google Sheet
        try:
            header = instances[0].to_header()
            body = [i.to_list() for i in instances]
            spreadsheet_url = gdocs.write_to_spreadsheet([header] + body)
            summary_msg += f'\nIf you want to see all the details, I wrote them to a spreadsheet at {spreadsheet_url}'
            print('Wrote data to Google sheet at URL ' + spreadsheet_url)
        except Exception as e:
            print(f'Failed to write data to Google sheet: {str(e)}')

        sqslack.send_message(channel, summary_msg)

        # From here on, exclude "whitelisted" instances
        all_instances = instances
        instances = sorted((i for i in instances if not is_whitelisted(i)), key=lambda i: i.name)

        instances_to_terminate = get_terminatable_instances(instances)
        if len(instances_to_terminate) > 0:
            terminate_msg = f'The following {len(instances_to_terminate)} _stopped_ instances are due to ' \
                            f'be *TERMINATED*, based on the "Terminate after" tag:\n'
            for i in instances_to_terminate:
                contact = sqslack.lookup_user_by_email(i.contact)
                terminate_msg += f'{make_instance_summary(i)}, ' \
                                 f'"Terminate after"={i.terminate_after}, ' \
                                 f'Monthly Price={money_to_string(i.monthly_price)}, ' \
                                 f'Contact={contact}\n'
                sqaws.set_tag(i.region_name, i.instance_id, 'Terminate after',
                              parsing.add_warning_to_tag(i.terminate_after, TODAY_YYYY_MM_DD))
        else:
            terminate_msg = 'No instances are due to be terminated at this time.\n'
        sqslack.send_message(channel, terminate_msg)

        instances_to_stop = get_stoppable_instances(instances)
        if len(instances_to_stop) > 0:
            stop_msg = f'The following {len(instances_to_stop)} _running_ instances are due to be *STOPPED*, ' \
                       f'based on the "Stop after" tag:\n'
            for i in instances_to_stop:
                contact = sqslack.lookup_user_by_email(i.contact)
                stop_msg += f'{make_instance_summary(i)}, ' \
                            f'"Stop after"={i.stop_after}, ' \
                            f'Monthly Price={money_to_string(i.monthly_price)}, ' \
                            f'Contact={contact}\n'
                sqaws.set_tag(i.region_name, i.instance_id, 'Stop after',
                              parsing.add_warning_to_tag(i.stop_after, TODAY_YYYY_MM_DD, replace=True))
        else:
            stop_msg = 'No instances are due to be stopped at this time.\n'
        sqslack.send_message(channel, stop_msg)

    def notify(self, channel):
        try:
            self._notify_internal(channel)
        except Exception as e:
            sqslack.send_message(channel, f"Nagbot failed to run the 'notify' command: {str(e)}")
            raise e

    def _execute_internal(self, channel):
        instances = sqaws.list_ec2_instances()

        # Only terminate instances which still meet the criteria for terminating, AND were warned several times
        instances_to_terminate = get_terminatable_instances(instances)
        instances_to_terminate = [i for i in instances_to_terminate if is_safe_to_terminate(i)]

        # Only stop instances which still meet the criteria for stopping, AND were warned recently
        instances_to_stop = get_stoppable_instances(instances)
        instances_to_stop = [i for i in instances_to_stop if is_safe_to_stop(i)]

        if len(instances_to_terminate) > 0:
            message = 'I terminated the following instances: '
            for i in instances_to_terminate:
                contact = sqslack.lookup_user_by_email(i.contact)
                message += f'{make_instance_summary(i)}, ' \
                           f'"Terminate after"={i.terminate_after}, ' \
                           f'Monthly Price={money_to_string(i.monthly_price)}, ' \
                           f'Contact={contact}\n'
                sqaws.terminate_instance(i.region_name, i.instance_id)
            sqslack.send_message(channel, message)
        else:
            sqslack.send_message(channel, 'No instances were terminated today.')

        if len(instances_to_stop) > 0:
            message = 'I stopped the following instances: '
            for i in instances_to_stop:
                contact = sqslack.lookup_user_by_email(i.contact)
                message += f'{make_instance_summary(i)}, ' \
                           f'"Stop after"={i.stop_after}, ' \
                           f'Monthly Price={money_to_string(i.monthly_price)}, ' \
                           f'Contact={contact}\n'
                sqaws.stop_instance(i.region_name, i.instance_id)
                sqaws.set_tag(i.region_name, i.instance_id, 'Nagbot State', f'Stopped on {TODAY_YYYY_MM_DD}')
            sqslack.send_message(channel, message)
        else:
            sqslack.send_message(channel, 'No instances were stopped today.')

    def execute(self, channel):
        try:
            self._execute_internal(channel)
        except Exception as e:
            sqslack.send_message(channel, f"Nagbot failed to run the 'execute' command: {str(e)}")
            raise e


def get_taggable_instances(instances):
    return list(i for i in instances if
                (not is_whitelisted(i) and (i.is_stop_after_tag_missing() or i.is_terminate_after_tag_missing())))


def tag_instance(instance):
    if instance.is_stop_after_tag_missing():
        sqaws.set_tag(instance.region_name, instance.instance_id, 'Stop after',
                      AUTO_STOP_AFTER_DAY_YYYY_MM_DD)
    if instance.is_terminate_after_tag_missing():
        sqaws.set_tag(instance.region_name, instance.instance_id, 'Terminate after',
                      AUTO_TERMINATE_AFTER_DAY_YYYY_MM_DD)


def get_stoppable_instances(instances):
    return list(i for i in instances if is_stoppable(i))


def is_stoppable(instance):
    parsed_date: parsing.ParsedDate = parsing.parse_date_tag(instance.stop_after)

    return instance.state == 'running' and (
            (parsed_date.expiry_date is None)  # Treat unspecified "Stop after" dates as being in the past
            or (TODAY_IS_WEEKEND and parsed_date.on_weekends)
            or (TODAY_YYYY_MM_DD >= parsed_date.expiry_date))


def get_terminatable_instances(instances):
    return list(i for i in instances if is_terminatable(i))


def is_terminatable(instance):
    parsed_date: parsing.ParsedDate = parsing.parse_date_tag(instance.terminate_after)

    # We'll only terminate instances which have an explicit 'Terminate after' tag. That will only be automatically
    # added if the tag_instances stage has been run.
    return instance.state == 'stopped' and (
        (parsed_date.expiry_date is not None and TODAY_YYYY_MM_DD >= parsed_date.expiry_date))


# Some instances are whitelisted from stop or terminate actions. These won't show up as recommended to stop/terminate.
def is_whitelisted(instance):
    for regex in [r'bam::.*bamboo']:
        if re.fullmatch(regex, instance.name) is not None:
            return True
    return False


# Convert floating point dollars to a readable string
def money_to_string(str):
    return '${:.2f}'.format(str)


def is_safe_to_stop(instance):
    warning_date = parsing.parse_date_tag(instance.stop_after).warning_date
    return is_stoppable(instance) and warning_date is not None and warning_date <= TODAY_YYYY_MM_DD


def is_safe_to_terminate(instance):
    warning_date = parsing.parse_date_tag(instance.terminate_after).warning_date
    return is_terminatable(instance) and warning_date is not None and warning_date <= MIN_TERMINATION_WARNING_YYYY_MM_DD


def make_instance_summary(instance):
    instance_id = instance.instance_id
    instance_url = url_from_instance_id(instance.region_name, instance_id)
    link = f'<{instance_url}|{instance.name}>'
    if instance.reason:
        state = f'State=({instance.state}, "{instance.reason}")'
    else:
        state = f'State={instance.state}'
    line = f'{link}, {state}, Type={instance.instance_type}'
    return line


def url_from_instance_id(region_name, instance_id):
    return f'https://{region_name}.console.aws.amazon.com/ec2/v2/home' \
           f'?region={region_name}#Instances:search={instance_id}'


def main(args):
    """
    Entry point for the application
    """
    channel = args.channel
    mode = args.mode

    if re.fullmatch(r'#[A-Za-z0-9-]+', channel) is None:
        print('Unexpected channel format "%s", should look like #random or #testing' % channel)
        sys.exit(1)
    print('Destination Slack channel is: ' + channel)

    nagbot = Nagbot()

    if mode.lower() == 'tag_instances':
        nagbot.tag_instances(channel)
    if mode.lower() == 'notify':
        nagbot.notify(channel)
    elif mode.lower() == 'execute':
        nagbot.execute(channel)
    else:
        print(f'Unexpected mode "{mode}", should be "tag_instances", "notify", or "execute"')
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", help="Mode, either 'tag_instances', 'notify', or 'execute'. "
                     "In 'tag_instances' mode, instances are auto-marked with a stop and terminate date. "
                     "In 'notify' mode, a notification is posted to Slack. "
                     "In 'execute' mode, instances are stopped or terminated.")

    parser.add_argument(
        "-c",
        "--channel",
        action="store",
        default='#nagbot-testing',
        help="Which Slack channel to publish to")

    args = parser.parse_args()
    main(args)
