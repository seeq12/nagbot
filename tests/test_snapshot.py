import unittest
from unittest.mock import patch
from unittest.mock import MagicMock

from app import util
from app.snapshot import Snapshot


class TestSnapshot(unittest.TestCase):
    @staticmethod
    def setup_snapshot(state: str, terminate_after: str = '', terminate_after_tag_name: str = ''):
        return Snapshot(region_name='us-east-1',
                        resource_id='def456',
                        state=state,
                        reason='',
                        resource_type='standard',
                        ec2_type='snapshot',
                        name='Ali',
                        operating_system='Windows',
                        monthly_price=1,
                        stop_after='',
                        terminate_after=terminate_after,
                        contact='Ali',
                        nagbot_state='',
                        eks_nodegroup_name='',
                        stop_after_tag_name='',
                        terminate_after_tag_name=terminate_after_tag_name,
                        nagbot_state_tag_name='',
                        size=1,
                        iops=1,
                        throughput=125,
                        is_ami_snapshot=False,
                        is_aws_backup_snapshot=False)

    def test_can_be_stopped(self):
        completed_no_stop_after = self.setup_snapshot(state='completed')
        pending_no_stop_after = self.setup_snapshot(state='pending')

        assert completed_no_stop_after.can_be_stopped(is_weekend=False) is False
        assert pending_no_stop_after.can_be_stopped(is_weekend=False) is False

    def test_is_safe_to_stop(self):
        todays_date = util.TODAY_YYYY_MM_DD
        past_date = self.setup_snapshot(state='completed', terminate_after='2019-01-01')
        today_date = self.setup_snapshot(state='completed', terminate_after=todays_date)

        today_warning_str = ' (Nagbot: Warned on ' + todays_date + ')'
        past_date_warned = self.setup_snapshot(state='completed', terminate_after='2019-01-01' + today_warning_str)
        today_date_warned = self.setup_snapshot(state='completed',
                                                terminate_after=todays_date + today_warning_str)
        anything_warned = self.setup_snapshot(state='completed', terminate_after='I Like Pie' + today_warning_str)

        old_warning_str = ' (Nagbot: Warned on ' + util.MIN_TERMINATION_WARNING_YYYY_MM_DD + ')'
        past_date_warned_days_ago = self.setup_snapshot(state='completed', terminate_after='2019-01-01' +
                                                                                           old_warning_str)
        anything_warned_days_ago = self.setup_snapshot(state='completed', terminate_after='I Like Pie' +
                                                                                          old_warning_str)

        wrong_state = self.setup_snapshot(state='pending', terminate_after='2019-01-01')
        future_date = self.setup_snapshot(state='completed', terminate_after='2050-01-01')
        unknown_date = self.setup_snapshot(state='completed', terminate_after='TBD')

        assert past_date.is_safe_to_stop(todays_date) is False
        assert today_date.is_safe_to_stop(todays_date) is False
        assert past_date_warned.is_safe_to_stop(todays_date) is False
        assert today_date_warned.is_safe_to_stop(todays_date) is False
        assert anything_warned.is_safe_to_stop(todays_date) is False
        assert past_date_warned_days_ago.is_safe_to_stop(todays_date) is False
        assert anything_warned_days_ago.is_safe_to_stop(todays_date) is False
        assert wrong_state.is_safe_to_stop(todays_date) is False
        assert future_date.is_safe_to_stop(todays_date) is False
        assert unknown_date.is_safe_to_stop(todays_date) is False

    def test_deletable(self):
        todays_date = util.TODAY_YYYY_MM_DD
        past_date = self.setup_snapshot(state='completed', terminate_after='2019-01-01')
        today_date = self.setup_snapshot(state='completed', terminate_after=todays_date)

        today_warning_str = ' (Nagbot: Warned on ' + todays_date + ')'
        past_date_warned = self.setup_snapshot(state='completed', terminate_after='2019-01-01' + today_warning_str)
        today_date_warned = self.setup_snapshot(state='completed',
                                                terminate_after=todays_date + today_warning_str)
        anything_warned = self.setup_snapshot(state='completed', terminate_after='I Like Pie' + today_warning_str)

        old_warning_str = ' (Nagbot: Warned on ' + util.MIN_TERMINATION_WARNING_YYYY_MM_DD + ')'
        past_date_warned_days_ago = self.setup_snapshot(state='completed', terminate_after='2019-01-01' +
                                                                                           old_warning_str)
        anything_warned_days_ago = self.setup_snapshot(state='completed', terminate_after='I Like Pie' +
                                                                                          old_warning_str)

        wrong_state = self.setup_snapshot(state='pending', terminate_after='2019-01-01')
        future_date = self.setup_snapshot(state='completed', terminate_after='2050-01-01')
        unknown_date = self.setup_snapshot(state='completed', terminate_after='TBD')

        ami_snapshot = self.setup_snapshot(state='completed', terminate_after='2019-01-01')
        ami_snapshot.__setattr__('is_ami_snapshot', True)
        aws_backup_snapshot = self.setup_snapshot(state='completed', terminate_after='2019-01-01')
        aws_backup_snapshot.__setattr__('is_aws_backup_snapshot', True)

        # These snapshots should get a deletion warning
        assert past_date.can_be_terminated(todays_date) is True
        assert today_date.can_be_terminated(todays_date) is True
        assert past_date_warned.can_be_terminated(todays_date) is True
        assert today_date_warned.can_be_terminated(todays_date) is True

        # These snapshots should NOT get a deletion warning
        assert wrong_state.can_be_terminated(todays_date) is False
        assert future_date.can_be_terminated(todays_date) is False
        assert unknown_date.can_be_terminated(todays_date) is False
        assert anything_warned.can_be_terminated(todays_date) is False

        # These snapshots should not be deleted since they are aws backup or ami snapshots
        assert ami_snapshot.can_be_terminated(todays_date) is False
        assert aws_backup_snapshot.can_be_terminated(todays_date) is False

        # These snapshots don't have a warning, so they shouldn't be deleted yet
        assert past_date.is_safe_to_terminate_after_warning(todays_date) is False
        assert today_date.is_safe_to_terminate_after_warning(todays_date) is False
        assert unknown_date.is_safe_to_terminate_after_warning(todays_date) is False
        assert wrong_state.is_safe_to_terminate_after_warning(todays_date) is False
        assert future_date.is_safe_to_terminate_after_warning(todays_date) is False
        assert anything_warned.is_safe_to_terminate_after_warning(todays_date) is False

        # These snapshots can be deleted, but not yet
        assert past_date_warned.is_safe_to_terminate_after_warning(todays_date) is False
        assert today_date_warned.is_safe_to_terminate_after_warning(todays_date) is False

        # These snapshots have a warning, but are not eligible to add a warning, so we don't delete
        assert anything_warned_days_ago.is_safe_to_terminate_after_warning(todays_date) is False

        # These snapshots can be deleted now
        assert past_date_warned_days_ago.is_safe_to_terminate_after_warning(todays_date) is True

    @staticmethod
    @patch('app.snapshot.boto3.resource')
    def test_delete_snapshot(mock_resource):
        mock_snapshot = TestSnapshot.setup_snapshot(state='completed')

        mock_ec2 = mock_resource.return_value
        # _aws is included in variable name to differentiate between Snapshot class of NagBot and Snapshot class of AWS
        mock_snapshot_aws = MagicMock()
        mock_ec2.Snapshot.return_value = mock_snapshot_aws

        assert mock_snapshot.terminate_resource(dryrun=False)

        mock_resource.assert_called_once_with('ec2', region_name=mock_snapshot.region_name)
        mock_snapshot_aws.delete.assert_called_once()

    @staticmethod
    @patch('app.snapshot.boto3.resource')
    def test_delete_snapshot_exception(mock_resource):
        def raise_error():
            raise RuntimeError('An error occurred (OperationNotPermitted)...')

        mock_snapshot = TestSnapshot.setup_snapshot(state='completed')

        mock_ec2 = mock_resource.return_value
        mock_snapshot_aws = MagicMock()
        mock_ec2.Snapshot.return_value = mock_snapshot_aws
        mock_snapshot_aws.delete.side_effect = lambda *args, **kw: raise_error()

        assert not mock_snapshot.terminate_resource(dryrun=False)

        mock_resource.assert_called_once_with('ec2', region_name=mock_snapshot.region_name)
        mock_snapshot_aws.delete.assert_called_once()


if __name__ == '__main__':
    unittest.main()
