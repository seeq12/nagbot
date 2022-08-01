import unittest

from app import new_sqaws
from app.new_sqaws import Instance, Volume


class TestNewNagbot(unittest.TestCase):
    @staticmethod
    def setup_instance(state: str, stop_after: str = '', terminate_after: str = '',
                       stop_after_tag_name: str = '', terminate_after_tag_name: str = ''):
        return Instance.Instance(region_name='us-east-1',
                                 instance_id='abc123',
                                 state=state,
                                 reason='',
                                 instance_type='m4.xlarge',
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
                                 nagbot_state_tag_name='NagbotState')

    @staticmethod
    def setup_volume(state: str, terminate_after: str = '', terminate_after_tag_name: str = ''):
        return Volume.Volume(region_name='us-east-1',
                             volume_id='def456',
                             state=state,
                             volume_type='gp2',
                             name='Quinn',
                             operating_system='Windows',
                             monthly_price=1,
                             terminate_after=terminate_after,
                             contact='quinn',
                             terminate_after_tag_name=terminate_after_tag_name,
                             size=1,
                             iops=1,
                             throughput=125)

    def test_stoppable(self):
        past_date = self.setup_instance(state='running', stop_after='2019-01-01')
        today_date = self.setup_instance(state='running', stop_after=new_sqaws.TODAY_YYYY_MM_DD)
        on_weekends = self.setup_instance(state='running', stop_after='On Weekends')

        warning_str = ' (Nagbot: Warned on ' + new_sqaws.TODAY_YYYY_MM_DD + ')'
        past_date_warned = self.setup_instance(state='running', stop_after='2019-01-01' + warning_str)
        today_date_warned = self.setup_instance(state='running', stop_after=new_sqaws.TODAY_YYYY_MM_DD + warning_str)
        anything_warned = self.setup_instance(state='running', stop_after='Yummy Udon Noodles' + warning_str)
        on_weekends_warned = self.setup_instance(state='running', stop_after='On Weekends' + warning_str)

        wrong_state = self.setup_instance(state='stopped', stop_after='2019-01-01')
        future_date = self.setup_instance(state='running', stop_after='2050-01-01')
        unknown_date = self.setup_instance(state='running', stop_after='TBD')

        blank_instance = new_sqaws.Instance(r_name='', r_id='', state='', reason='', r_type='', name='', eks_name='',
                                            os='', s_after='', t_after='', n_state='', contact='', m_price='',
                                            m_server_price='', m_storage_price='', s_after_tag='', t_after_tag='',
                                            n_state_tag='')

        # These instances should get a stop warning
        assert new_sqaws.Instance.is_stoppable(past_date) is True
        assert new_sqaws.Instance.is_stoppable(today_date) is True
        assert new_sqaws.Instance.is_stoppable(on_weekends, is_weekend=True) is True
        assert new_sqaws.Instance.is_stoppable(unknown_date) is True
        assert new_sqaws.Instance.is_stoppable(past_date_warned) is True
        assert new_sqaws.Instance.is_stoppable(today_date_warned) is True
        assert new_sqaws.Instance.is_stoppable(anything_warned) is True
        assert new_sqaws.Instance.is_stoppable(on_weekends_warned, is_weekend=True) is True

        # These instances should NOT get a stop warning
        assert new_sqaws.Instance.is_stoppable(on_weekends, is_weekend=False) is False
        assert new_sqaws.Instance.is_stoppable(on_weekends_warned, is_weekend=False) is False
        assert new_sqaws.Instance.is_stoppable(wrong_state) is False
        assert new_sqaws.Instance.is_stoppable(future_date) is False

        # These instances don't have a warning, so they shouldn't be stopped yet
        assert new_sqaws.Instance.is_safe_to_stop(blank_instance, past_date) is False
        assert new_sqaws.Instance.is_safe_to_stop(blank_instance, today_date) is False
        assert new_sqaws.Instance.is_safe_to_stop(blank_instance, on_weekends, is_weekend=True) is False
        assert new_sqaws.Instance.is_safe_to_stop(blank_instance, unknown_date) is False
        assert new_sqaws.Instance.is_safe_to_stop(blank_instance, wrong_state) is False
        assert new_sqaws.Instance.is_safe_to_stop(blank_instance, future_date) is False

        # These instances can be stopped right away
        assert new_sqaws.Instance.is_safe_to_stop(blank_instance, past_date_warned) is True
        assert new_sqaws.Instance.is_safe_to_stop(blank_instance, today_date_warned) is True
        assert new_sqaws.Instance.is_safe_to_stop(blank_instance, on_weekends_warned, is_weekend=True) is True
        assert new_sqaws.Instance.is_safe_to_stop(blank_instance, anything_warned) is True

    def test_terminatable(self):
        past_date = self.setup_instance(state='stopped', terminate_after='2019-01-01')
        today_date = self.setup_instance(state='stopped', terminate_after=new_sqaws.TODAY_YYYY_MM_DD)

        today_warning_str = ' (Nagbot: Warned on ' + new_sqaws.TODAY_YYYY_MM_DD + ')'
        past_date_warned = self.setup_instance(state='stopped', terminate_after='2019-01-01' + today_warning_str)
        today_date_warned = self.setup_instance(state='stopped',
                                                terminate_after=new_sqaws.TODAY_YYYY_MM_DD + today_warning_str)
        anything_warned = self.setup_instance(state='stopped', terminate_after='Yummy Udon Noodles' + today_warning_str)

        old_warning_str = ' (Nagbot: Warned on ' + new_sqaws.MIN_TERMINATION_WARNING_YYYY_MM_DD + ')'
        past_date_warned_days_ago = self.setup_instance(state='stopped', terminate_after='2019-01-01' + old_warning_str)
        anything_warned_days_ago = self.setup_instance(state='stopped',
                                                       terminate_after='Yummy Udon Noodles' + old_warning_str)

        wrong_state = self.setup_instance(state='running', terminate_after='2019-01-01')
        future_date = self.setup_instance(state='stopped', terminate_after='2050-01-01')
        unknown_date = self.setup_instance(state='stopped', terminate_after='TBD')

        blank_instance = new_sqaws.Instance(r_name='', r_id='', state='', reason='', r_type='', name='', eks_name='',
                                            os='', s_after='', t_after='', n_state='', contact='', m_price='',
                                            m_server_price='', m_storage_price='', s_after_tag='', t_after_tag='',
                                            n_state_tag='')

        # These instances should get a termination warning
        assert new_sqaws.Instance.is_terminatable(blank_instance, past_date) is True
        assert new_sqaws.Instance.is_terminatable(blank_instance, today_date) is True
        assert new_sqaws.Instance.is_terminatable(blank_instance, past_date_warned) is True
        assert new_sqaws.Instance.is_terminatable(blank_instance, today_date_warned) is True

        # These instances should NOT get a termination warning
        assert new_sqaws.Instance.is_terminatable(blank_instance, wrong_state) is False
        assert new_sqaws.Instance.is_terminatable(blank_instance, future_date) is False
        assert new_sqaws.Instance.is_terminatable(blank_instance, unknown_date) is False
        assert new_sqaws.Instance.is_terminatable(blank_instance, anything_warned) is False

        # These instances don't have a warning, so they shouldn't be terminated yet
        assert new_sqaws.Instance.is_safe_to_terminate(blank_instance, past_date) is False
        assert new_sqaws.Instance.is_safe_to_terminate(blank_instance, today_date) is False
        assert new_sqaws.Instance.is_safe_to_terminate(blank_instance, unknown_date) is False
        assert new_sqaws.Instance.is_safe_to_terminate(blank_instance, wrong_state) is False
        assert new_sqaws.Instance.is_safe_to_terminate(blank_instance, future_date) is False
        assert new_sqaws.Instance.is_safe_to_terminate(blank_instance, anything_warned) is False

        # These instances can be terminated, but not yet
        assert new_sqaws.Instance.is_safe_to_terminate(blank_instance, past_date_warned) is False
        assert new_sqaws.Instance.is_safe_to_terminate(blank_instance, today_date_warned) is False

        # These instances have a warning, but are not eligible to add a warning, so we don't terminate
        assert new_sqaws.Instance.is_safe_to_terminate(blank_instance, anything_warned_days_ago) is False

        # These instances can be terminated now
        assert new_sqaws.Instance.is_safe_to_terminate(blank_instance, past_date_warned_days_ago) is True

    def test_deletable(self):
        past_date = self.setup_volume(state='available', terminate_after='2019-01-01')
        today_date = self.setup_volume(state='available', terminate_after=new_sqaws.TODAY_YYYY_MM_DD)

        today_warning_str = ' (Nagbot: Warned on ' + new_sqaws.TODAY_YYYY_MM_DD + ')'
        past_date_warned = self.setup_volume(state='available', terminate_after='2019-01-01' + today_warning_str)
        today_date_warned = self.setup_volume(state='available',
                                              terminate_after=new_sqaws.TODAY_YYYY_MM_DD + today_warning_str)
        anything_warned = self.setup_volume(state='available', terminate_after='I Like Pie' + today_warning_str)

        old_warning_str = ' (Nagbot: Warned on ' + new_sqaws.MIN_TERMINATION_WARNING_YYYY_MM_DD + ')'
        past_date_warned_days_ago = self.setup_volume(state='available', terminate_after='2019-01-01' +
                                                                                         old_warning_str)
        anything_warned_days_ago = self.setup_volume(state='available', terminate_after='I Like Pie' +
                                                                                        old_warning_str)

        wrong_state = self.setup_volume(state='in-use', terminate_after='2019-01-01')
        future_date = self.setup_volume(state='available', terminate_after='2050-01-01')
        unknown_date = self.setup_volume(state='available', terminate_after='TBD')

        blank_volume = new_sqaws.Volume(r_name='', r_id='', state='', r_type='', size='', iops='', throughput='',
                                        name='', os='', t_after='', contact='', m_price='', t_after_tag='')

        # These volumes should get a deletion warning
        assert new_sqaws.Volume.is_terminatable(blank_volume, past_date) is True
        assert new_sqaws.Volume.is_terminatable(blank_volume, today_date) is True
        assert new_sqaws.Volume.is_terminatable(blank_volume, past_date_warned) is True
        assert new_sqaws.Volume.is_terminatable(blank_volume, today_date_warned) is True

        # These volumes should NOT get a deletion warning
        assert new_sqaws.Volume.is_terminatable(blank_volume, wrong_state) is False
        assert new_sqaws.Volume.is_terminatable(blank_volume, future_date) is False
        assert new_sqaws.Volume.is_terminatable(blank_volume, unknown_date) is False
        assert new_sqaws.Volume.is_terminatable(blank_volume, anything_warned) is False

        # These volumes don't have a warning, so they shouldn't be deleted yet
        assert new_sqaws.Volume.is_safe_to_terminate(blank_volume, past_date) is False
        assert new_sqaws.Volume.is_safe_to_terminate(blank_volume, today_date) is False
        assert new_sqaws.Volume.is_safe_to_terminate(blank_volume, unknown_date) is False
        assert new_sqaws.Volume.is_safe_to_terminate(blank_volume, wrong_state) is False
        assert new_sqaws.Volume.is_safe_to_terminate(blank_volume, future_date) is False
        assert new_sqaws.Volume.is_safe_to_terminate(blank_volume, anything_warned) is False

        # These volumes can be deleted, but not yet
        assert new_sqaws.Volume.is_safe_to_terminate(blank_volume, past_date_warned) is False
        assert new_sqaws.Volume.is_safe_to_terminate(blank_volume, today_date_warned) is False

        # These volumes have a warning, but are not eligible to add a warning, so we don't delete
        assert new_sqaws.Volume.is_safe_to_terminate(blank_volume, anything_warned_days_ago) is False

        # These volumes can be deleted now
        assert new_sqaws.Volume.is_safe_to_terminate(blank_volume, past_date_warned_days_ago) is True

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
