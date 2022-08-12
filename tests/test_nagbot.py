import unittest

from app import sqaws
from app import nagbot
from app.sqaws import Instance, Volume


class TestNewNagbot(unittest.TestCase):
    @staticmethod
    def setup_instance(state: str, stop_after: str = '', terminate_after: str = '',
                       stop_after_tag_name: str = '', terminate_after_tag_name: str = ''):
        return Instance(region_name='us-east-1',
                        resource_id='abc123',
                        state=state,
                        reason='',
                        resource_type='m4.xlarge',
                        ec2_type='instance',
                        name='Stephen',
                        operating_system='linux',
                        monthly_price=1,
                        monthly_server_price=2,
                        monthly_storage_price=3,
                        stop_after=stop_after,
                        terminate_after=terminate_after,
                        contact='stephen',
                        nagbot_state='',
                        eks_nodegroup_name='',
                        stop_after_tag_name=stop_after_tag_name,
                        terminate_after_tag_name=terminate_after_tag_name,
                        nagbot_state_tag_name='NagbotState',
                        size=0,
                        iops=0,
                        throughput=0)

    @staticmethod
    def setup_volume(state: str, terminate_after: str = '', terminate_after_tag_name: str = ''):
        return Volume(region_name='us-east-1',
                      resource_id='def456',
                      state=state,
                      reason='',
                      resource_type='gp2',
                      ec2_type='volume',
                      name='Quinn',
                      operating_system='Windows',
                      monthly_server_price=0,
                      monthly_storage_price=0,
                      monthly_price=1,
                      stop_after='',
                      terminate_after=terminate_after,
                      contact='quinn',
                      nagbot_state='',
                      eks_nodegroup_name='',
                      stop_after_tag_name='',
                      terminate_after_tag_name=terminate_after_tag_name,
                      nagbot_state_tag_name='',
                      size=1,
                      iops=1,
                      throughput=125)

    def test_stoppable(self):
        past_date = self.setup_instance(state='running', stop_after='2019-01-01')
        today_date = self.setup_instance(state='running', stop_after=nagbot.TODAY_YYYY_MM_DD)
        on_weekends = self.setup_instance(state='running', stop_after='On Weekends')

        warning_str = ' (Nagbot: Warned on ' + nagbot.TODAY_YYYY_MM_DD + ')'
        past_date_warned = self.setup_instance(state='running', stop_after='2019-01-01' + warning_str)
        today_date_warned = self.setup_instance(state='running', stop_after=nagbot.TODAY_YYYY_MM_DD + warning_str)
        anything_warned = self.setup_instance(state='running', stop_after='Yummy Udon Noodles' + warning_str)
        on_weekends_warned = self.setup_instance(state='running', stop_after='On Weekends' + warning_str)

        wrong_state = self.setup_instance(state='stopped', stop_after='2019-01-01')
        future_date = self.setup_instance(state='running', stop_after='2050-01-01')
        unknown_date = self.setup_instance(state='running', stop_after='TBD')

        todays_date = nagbot.TODAY_YYYY_MM_DD

        # These instances should get a stop warning
        assert Instance.is_stoppable(past_date, todays_date) is True
        assert Instance.is_stoppable(today_date, todays_date) is True
        assert Instance.is_stoppable(on_weekends, todays_date, is_weekend=True) is True
        assert Instance.is_stoppable(unknown_date, todays_date) is True
        assert Instance.is_stoppable(past_date_warned, todays_date) is True
        assert Instance.is_stoppable(today_date_warned, todays_date) is True
        assert Instance.is_stoppable(anything_warned, todays_date) is True
        assert Instance.is_stoppable(on_weekends_warned, todays_date, is_weekend=True) is True

        # These instances should NOT get a stop warning
        assert Instance.is_stoppable(on_weekends, todays_date, is_weekend=False) is False
        assert Instance.is_stoppable(on_weekends_warned, todays_date, is_weekend=False) is False
        assert Instance.is_stoppable(wrong_state, todays_date) is False
        assert Instance.is_stoppable(future_date, todays_date) is False

        # These instances don't have a warning, so they shouldn't be stopped yet
        assert Instance.is_safe_to_stop(past_date, todays_date) is False
        assert Instance.is_safe_to_stop(today_date, todays_date) is False
        assert Instance.is_safe_to_stop(on_weekends, todays_date, is_weekend=True) is False
        assert Instance.is_safe_to_stop(unknown_date, todays_date) is False
        assert Instance.is_safe_to_stop(wrong_state, todays_date) is False
        assert Instance.is_safe_to_stop(future_date, todays_date) is False

        # These instances can be stopped right away
        assert Instance.is_safe_to_stop(past_date_warned, todays_date) is True
        assert Instance.is_safe_to_stop(today_date_warned, todays_date) is True
        assert Instance.is_safe_to_stop(on_weekends_warned, todays_date, is_weekend=True) is True
        assert Instance.is_safe_to_stop(anything_warned, todays_date) is True

    def test_terminatable(self):
        todays_date = nagbot.TODAY_YYYY_MM_DD
        past_date = self.setup_instance(state='stopped', terminate_after='2019-01-01')
        today_date = self.setup_instance(state='stopped', terminate_after=todays_date)

        today_warning_str = ' (Nagbot: Warned on ' + todays_date + ')'
        past_date_warned = self.setup_instance(state='stopped', terminate_after='2019-01-01' + today_warning_str)
        today_date_warned = self.setup_instance(state='stopped',
                                                terminate_after=todays_date + today_warning_str)
        anything_warned = self.setup_instance(state='stopped', terminate_after='Yummy Udon Noodles' + today_warning_str)

        old_warning_str = ' (Nagbot: Warned on ' + sqaws.MIN_TERMINATION_WARNING_YYYY_MM_DD + ')'
        past_date_warned_days_ago = self.setup_instance(state='stopped', terminate_after='2019-01-01' + old_warning_str)
        anything_warned_days_ago = self.setup_instance(state='stopped',
                                                       terminate_after='Yummy Udon Noodles' + old_warning_str)

        wrong_state = self.setup_instance(state='running', terminate_after='2019-01-01')
        future_date = self.setup_instance(state='stopped', terminate_after='2050-01-01')
        unknown_date = self.setup_instance(state='stopped', terminate_after='TBD')

        # These instances should get a termination warning
        assert Instance.is_terminatable(past_date, todays_date) is True
        assert Instance.is_terminatable(today_date, todays_date) is True
        assert Instance.is_terminatable(past_date_warned, todays_date) is True
        assert Instance.is_terminatable(today_date_warned, todays_date) is True

        # These instances should NOT get a termination warning
        assert Instance.is_terminatable(wrong_state, todays_date) is False
        assert Instance.is_terminatable(future_date, todays_date) is False
        assert Instance.is_terminatable(unknown_date, todays_date) is False
        assert Instance.is_terminatable(anything_warned, todays_date) is False

        # These instances don't have a warning, so they shouldn't be terminated yet
        assert Instance.is_safe_to_terminate(past_date, todays_date) is False
        assert Instance.is_safe_to_terminate(today_date, todays_date) is False
        assert Instance.is_safe_to_terminate(unknown_date, todays_date) is False
        assert Instance.is_safe_to_terminate(wrong_state, todays_date) is False
        assert Instance.is_safe_to_terminate(future_date, todays_date) is False
        assert Instance.is_safe_to_terminate(anything_warned, todays_date) is False

        # These instances can be terminated, but not yet
        assert Instance.is_safe_to_terminate(past_date_warned, todays_date) is False
        assert Instance.is_safe_to_terminate(today_date_warned, todays_date) is False

        # These instances have a warning, but are not eligible to add a warning, so we don't terminate
        assert Instance.is_safe_to_terminate(anything_warned_days_ago, todays_date) is False

        # These instances can be terminated now
        assert Instance.is_safe_to_terminate(past_date_warned_days_ago, todays_date) is True

    def test_deletable(self):
        todays_date = nagbot.TODAY_YYYY_MM_DD
        past_date = self.setup_volume(state='available', terminate_after='2019-01-01')
        today_date = self.setup_volume(state='available', terminate_after=todays_date)

        today_warning_str = ' (Nagbot: Warned on ' + todays_date + ')'
        past_date_warned = self.setup_volume(state='available', terminate_after='2019-01-01' + today_warning_str)
        today_date_warned = self.setup_volume(state='available',
                                              terminate_after=todays_date + today_warning_str)
        anything_warned = self.setup_volume(state='available', terminate_after='I Like Pie' + today_warning_str)

        old_warning_str = ' (Nagbot: Warned on ' + sqaws.MIN_TERMINATION_WARNING_YYYY_MM_DD + ')'
        past_date_warned_days_ago = self.setup_volume(state='available', terminate_after='2019-01-01' +
                                                                                         old_warning_str)
        anything_warned_days_ago = self.setup_volume(state='available', terminate_after='I Like Pie' +
                                                                                        old_warning_str)

        wrong_state = self.setup_volume(state='in-use', terminate_after='2019-01-01')
        future_date = self.setup_volume(state='available', terminate_after='2050-01-01')
        unknown_date = self.setup_volume(state='available', terminate_after='TBD')

        # These volumes should get a deletion warning
        assert Volume.is_terminatable(past_date, todays_date) is True
        assert Volume.is_terminatable(today_date, todays_date) is True
        assert Volume.is_terminatable(past_date_warned, todays_date) is True
        assert Volume.is_terminatable(today_date_warned, todays_date) is True

        # These volumes should NOT get a deletion warning
        assert Volume.is_terminatable(wrong_state, todays_date) is False
        assert Volume.is_terminatable(future_date, todays_date) is False
        assert Volume.is_terminatable(unknown_date, todays_date) is False
        assert Volume.is_terminatable(anything_warned, todays_date) is False

        # These volumes don't have a warning, so they shouldn't be deleted yet
        assert Volume.is_safe_to_terminate(past_date, todays_date) is False
        assert Volume.is_safe_to_terminate(today_date, todays_date) is False
        assert Volume.is_safe_to_terminate(unknown_date, todays_date) is False
        assert Volume.is_safe_to_terminate(wrong_state, todays_date) is False
        assert Volume.is_safe_to_terminate(future_date, todays_date) is False
        assert Volume.is_safe_to_terminate(anything_warned, todays_date) is False

        # These volumes can be deleted, but not yet
        assert Volume.is_safe_to_terminate(past_date_warned, todays_date) is False
        assert Volume.is_safe_to_terminate(today_date_warned, todays_date) is False

        # These volumes have a warning, but are not eligible to add a warning, so we don't delete
        assert Volume.is_safe_to_terminate(anything_warned_days_ago, todays_date) is False

        # These volumes can be deleted now
        assert Volume.is_safe_to_terminate(past_date_warned_days_ago, todays_date) is True

    def test_instance_stop_terminate_str(self):
        lowercase_instance = self.setup_instance(state='running', stop_after_tag_name='stopafter',
                                                 terminate_after_tag_name='terminateafter')
        uppercase_instance = self.setup_instance(state='running', stop_after_tag_name='STOPAFTER',
                                                 terminate_after_tag_name='TERMINATEAFTER')
        mixed_case_instance = self.setup_instance(state='running', stop_after_tag_name='StopAfter',
                                                  terminate_after_tag_name='TerminateAfter')

        # Ensure stop_after_str and terminate_after_str fields are correct in each instance
        assert lowercase_instance.stop_after_tag_name == 'stopafter'
        assert lowercase_instance.terminate_after_tag_name == 'terminateafter'
        assert uppercase_instance.stop_after_tag_name == 'STOPAFTER'
        assert uppercase_instance.terminate_after_tag_name == 'TERMINATEAFTER'
        assert mixed_case_instance.stop_after_tag_name == 'StopAfter'
        assert mixed_case_instance.terminate_after_tag_name == 'TerminateAfter'


if __name__ == '__main__':
    unittest.main()
