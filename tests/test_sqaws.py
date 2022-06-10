import unittest
from unittest.mock import patch

import app.sqaws

import pytest


def test_make_tags_dict():
    tags_list = [{'Key': 'Contact', 'Value': 'stephen.rosenthal@seeq.com'},
                 {'Key': 'Stop after', 'Value': '2020-01-01'},
                 {'Key': 'Terminate after', 'Value': '2021-01-01'},
                 {'Key': 'Name', 'Value': 'super-cool-server.seeq.com'}]

    tags_dict = app.sqaws.make_tags_dict(tags_list)

    assert tags_dict == {'Contact': 'stephen.rosenthal@seeq.com',
                         'Stop after': '2020-01-01',
                         'Terminate after': '2021-01-01',
                         'Name': 'super-cool-server.seeq.com'}


@patch('app.sqaws.boto3.client')
def test_set_tag(mock_client):
    region_name = 'us-east-1'
    instance_id = 'i-0f06b49c1f16dcfde'
    tag_name = 'Stop after'
    tag_value = '2019-12-25'
    mock_ec2 = mock_client.return_value

    app.sqaws.set_tag(region_name, instance_id, tag_name, tag_value, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.create_tags.assert_called_once_with(Resources=[instance_id], Tags=[{
        'Key': tag_name,
        'Value': tag_value
    }])


@patch('app.sqaws.boto3.client')
def test_stop_instance(mock_client):
    region_name = 'us-east-1'
    instance_id = 'i-0f06b49c1f16dcfde'
    mock_ec2 = mock_client.return_value

    assert app.sqaws.stop_instance(region_name, instance_id, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.stop_instances.assert_called_once_with(InstanceIds=[instance_id])


@patch('app.sqaws.boto3.client')
def test_stop_instance_exception(mock_client):
    # Note: I haven't seen the call to stop_instance fail, but it certainly could.
    def raise_error():
        raise RuntimeError('An error occurred (OperationNotPermitted)...')

    region_name = 'us-east-1'
    instance_id = 'i-0f06b49c1f16dcfde'
    mock_ec2 = mock_client.return_value
    mock_ec2.stop_instances.side_effect = lambda *args, **kw: raise_error()

    assert not app.sqaws.stop_instance(region_name, instance_id, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.stop_instances.assert_called_once_with(InstanceIds=[instance_id])


@patch('app.sqaws.boto3.client')
def test_terminate_instance(mock_client):
    region_name = 'us-east-1'
    instance_id = 'i-0f06b49c1f16dcfde'
    mock_ec2 = mock_client.return_value

    assert app.sqaws.terminate_instance(region_name, instance_id, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.terminate_instances.assert_called_once_with(InstanceIds=[instance_id])


@patch('app.sqaws.boto3.client')
def test_terminate_instance_exception(mock_client):
    # Note: I've seen the call to terminate_instance fail when termination protection is enabled
    def raise_error():
        # The real Boto SDK raises botocore.exceptions.ClientError, but this is close enough
        raise RuntimeError('An error occurred (OperationNotPermitted)...')

    region_name = 'us-east-1'
    instance_id = 'i-0f06b49c1f16dcfde'
    mock_ec2 = mock_client.return_value
    mock_ec2.terminate_instances.side_effect = lambda *args, **kw: raise_error()

    assert not app.sqaws.terminate_instance(region_name, instance_id, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.terminate_instances.assert_called_once_with(InstanceIds=[instance_id])


@pytest.mark.parametrize('stop_terminate_dict, expected_stop_result, expected_terminate_result', [
    ({'stop after': '2022-05-10', 'terminate after': '2022-05-11'}, '2022-05-10', '2022-05-11'),
    ({'Stop After': '2030-07-23', 'Terminate After': '2050-08-10'}, '2030-07-23', '2050-08-10'),
    ({'STOP AFTER': '2021-03-04', 'TERMINATE AFTER': '2022-09-12'}, '2021-03-04', '2022-09-12'),
    ({'stop_after': '2022-05-10', 'terminate_after': '2022-05-11'}, '2022-05-10', '2022-05-11'),
    ({'Stop_After': '2030-07-23', 'Terminate_After': '2050-08-10'}, '2030-07-23', '2050-08-10'),
    ({'STOP_AFTER': '2021-03-04', 'TERMINATE_AFTER': '2022-09-12'}, '2021-03-04', '2022-09-12'),
    ({'stopafter': '2022-05-10', 'terminateafter': '2022-05-11'}, '2022-05-10', '2022-05-11'),
    ({'StopAfter': '2030-07-23', 'TerminateAfter': '2050-08-10'}, '2030-07-23', '2050-08-10'),
    ({'STOPAFTER': '2021-03-04', 'TERMINATEAFTER': '2022-09-12'}, '2021-03-04', '2022-09-12'),
    ({'': '2021-03-04', 'terminate.after': '2022-09-12'}, '', '2022-09-12'),
    ({'stop.after': '2021-03-04', '': '2022-09-12'}, '2021-03-04', '')
])
def test_stop_and_terminate_after(stop_terminate_dict, expected_stop_result,
                                  expected_terminate_result):
    stop_terminate = app.sqaws.get_stop_and_terminate_after(stop_terminate_dict)
    assert(stop_terminate[0] == expected_stop_result)
    assert(stop_terminate[1] == expected_terminate_result)


if __name__ == '__main__':
    unittest.main()
