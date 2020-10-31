import sys
import unittest

import app
from app import nagbot
from app import parsing
from app.sqaws import Instance


class TestNagbot(unittest.TestCase):
    def setup_instance(self, state: str = 'running', stop_after: str = '', terminate_after: str = ''):
        return Instance(region_name='us-east-1',
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
                        nagbot_state='')

    def test_tags_missing(self):
        valid_date = '2019-01-01'
        fully_tagged = self.setup_instance(stop_after=valid_date, terminate_after=valid_date)
        warning_terminate = self.setup_instance(stop_after=valid_date,
                                                terminate_after='Frigid froyo feeds Flo (Nagbot: Warned on 2019-01-01)')
        unknown_stop = self.setup_instance(stop_after='Wonderful Willamette wombats', terminate_after=valid_date)
        empty_stop = self.setup_instance(terminate_after=valid_date)
        empty_terminate = self.setup_instance(stop_after=valid_date)
        empty_stop_and_terminate = self.setup_instance()
        unknown_terminate = self.setup_instance(stop_after=valid_date,
                                                terminate_after='Pope Paul pleases proletariat people')

        # These have something in stop_after and some kind of date for terminate_after
        assert fully_tagged.is_stop_after_tag_missing() is False
        assert fully_tagged.is_terminate_after_tag_missing() is False
        assert fully_tagged.is_terminate_after_tag_missing() is False

        assert warning_terminate.is_stop_after_tag_missing() is False
        assert warning_terminate.is_terminate_after_tag_missing() is False
        # This one will get stopped due to the warning system
        assert unknown_stop.is_stop_after_tag_missing() is False
        assert unknown_stop.is_terminate_after_tag_missing() is False

        # stop_after should be filled in if it's not present
        assert empty_stop.is_stop_after_tag_missing() is True
        assert empty_stop.is_terminate_after_tag_missing() is False

        # terminate_after should be filled in if it's not present
        assert empty_terminate.is_stop_after_tag_missing() is False
        assert empty_terminate.is_terminate_after_tag_missing() is True

        # stop_after and terminate_after should be filled in if they're not present
        assert empty_stop_and_terminate.is_stop_after_tag_missing() is True
        assert empty_stop_and_terminate.is_terminate_after_tag_missing() is True

        # terminate_after must have some kind of date in it
        assert unknown_terminate.is_stop_after_tag_missing() is False
        assert unknown_terminate.is_terminate_after_tag_missing() is True

        # Test the get_taggable_instances() only returns the instances that result in True above
        all_instances = [fully_tagged, warning_terminate, unknown_stop, empty_stop, empty_terminate,
                         empty_stop_and_terminate, unknown_terminate]
        taggable_instances = [empty_stop, empty_terminate, empty_stop_and_terminate, unknown_terminate]
        self.assertListEqual(nagbot.get_taggable_instances(all_instances), taggable_instances)

    def test_stoppable(self):
        past_date = self.setup_instance(state='running', stop_after='2019-01-01')
        today_date = self.setup_instance(state='running', stop_after=nagbot.TODAY_YYYY_MM_DD)

        warning_str = ' (Nagbot: Warned on ' + nagbot.TODAY_YYYY_MM_DD + ')'
        past_date_warned = self.setup_instance(state='running', stop_after='2019-01-01' + warning_str)
        today_date_warned = self.setup_instance(state='running', stop_after=nagbot.TODAY_YYYY_MM_DD + warning_str)
        anything_warned = self.setup_instance(state='running', stop_after='Yummy Udon Noodles' + warning_str)

        wrong_state = self.setup_instance(state='stopped', stop_after='2019-01-01')
        future_date = self.setup_instance(state='running', stop_after='2050-01-01')
        unknown_date = self.setup_instance(state='running', stop_after='TBD')

        # These instances should get a stop warning
        assert nagbot.is_stoppable(past_date) is True
        assert nagbot.is_stoppable(today_date) is True
        assert nagbot.is_stoppable(unknown_date) is True
        assert nagbot.is_stoppable(past_date_warned) is True
        assert nagbot.is_stoppable(today_date_warned) is True
        assert nagbot.is_stoppable(anything_warned) is True

        # These instances should NOT get a stop warning
        assert nagbot.is_stoppable(wrong_state) is False
        assert nagbot.is_stoppable(future_date) is False

        # These instances don't have a warning, so they shouldn't be stopped yet
        assert nagbot.is_safe_to_stop(past_date) is False
        assert nagbot.is_safe_to_stop(today_date) is False
        assert nagbot.is_safe_to_stop(unknown_date) is False
        assert nagbot.is_safe_to_stop(wrong_state) is False
        assert nagbot.is_safe_to_stop(future_date) is False

        # These instances can be stopped right away
        assert nagbot.is_safe_to_stop(past_date_warned) is True
        assert nagbot.is_safe_to_stop(today_date_warned) is True
        assert nagbot.is_safe_to_stop(anything_warned) is True

    def test_terminatable(self):
        past_date = self.setup_instance(state='stopped', terminate_after='2019-01-01')
        today_date = self.setup_instance(state='stopped', terminate_after=nagbot.TODAY_YYYY_MM_DD)

        today_warning_str = ' (Nagbot: Warned on ' + nagbot.TODAY_YYYY_MM_DD + ')'
        past_date_warned = self.setup_instance(state='stopped', terminate_after='2019-01-01' + today_warning_str)
        today_date_warned = self.setup_instance(state='stopped',
                                                terminate_after=nagbot.TODAY_YYYY_MM_DD + today_warning_str)
        anything_warned = self.setup_instance(state='stopped', terminate_after='Yummy Udon Noodles' + today_warning_str)

        old_warning_str = ' (Nagbot: Warned on ' + nagbot.MIN_TERMINATION_WARNING_YYYY_MM_DD + ')'
        past_date_warned_days_ago = self.setup_instance(state='stopped', terminate_after='2019-01-01' + old_warning_str)
        anything_warned_days_ago = self.setup_instance(state='stopped',
                                                       terminate_after='Yummy Udon Noodles' + old_warning_str)

        wrong_state = self.setup_instance(state='running', terminate_after='2019-01-01')
        future_date = self.setup_instance(state='stopped', terminate_after='2050-01-01')
        unknown_date = self.setup_instance(state='stopped', terminate_after='TBD')

        # These instances should get a termination warning
        assert nagbot.is_terminatable(past_date) is True
        assert nagbot.is_terminatable(today_date) is True
        assert nagbot.is_terminatable(past_date_warned) is True
        assert nagbot.is_terminatable(today_date_warned) is True

        # These instances should NOT get a termination warning
        assert nagbot.is_terminatable(wrong_state) is False
        assert nagbot.is_terminatable(future_date) is False
        assert nagbot.is_terminatable(unknown_date) is False
        assert nagbot.is_terminatable(anything_warned) is False

        # These instances don't have a warning, so they shouldn't be terminated yet
        assert nagbot.is_safe_to_terminate(past_date) is False
        assert nagbot.is_safe_to_terminate(today_date) is False
        assert nagbot.is_safe_to_terminate(unknown_date) is False
        assert nagbot.is_safe_to_terminate(wrong_state) is False
        assert nagbot.is_safe_to_terminate(future_date) is False
        assert nagbot.is_safe_to_terminate(anything_warned) is False

        # These instances can be terminated, but not yet
        assert nagbot.is_safe_to_terminate(past_date_warned) is False
        assert nagbot.is_safe_to_terminate(today_date_warned) is False

        # These instances have a warning, but are not eligible to add a warning, so we don't terminate
        assert nagbot.is_safe_to_terminate(anything_warned_days_ago) is False

        # These instances can be terminated now
        assert nagbot.is_safe_to_terminate(past_date_warned_days_ago) is True


if __name__ == '__main__':
    unittest.main()
