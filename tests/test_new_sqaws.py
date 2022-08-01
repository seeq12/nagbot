from unittest.mock import patch

import app.new_sqaws

import pytest


def test_make_tags_dict():
    tags_list = [{'Key': 'Contact', 'Value': 'stephen.rosenthal@seeq.com'},
                 {'Key': 'Stop after', 'Value': '2020-01-01'},
                 {'Key': 'Terminate after', 'Value': '2021-01-01'},
                 {'Key': 'Name', 'Value': 'super-cool-server.seeq.com'}]

    tags_dict = app.new_sqaws.make_tags_dict(tags_list)

    assert tags_dict == {'Contact': 'stephen.rosenthal@seeq.com',
                         'Stop after': '2020-01-01',
                         'Terminate after': '2021-01-01',
                         'Name': 'super-cool-server.seeq.com'}


@patch('app.new_sqaws.boto3.client')
def test_set_tag(mock_client):
    region_name = 'us-east-1'
    instance_id = 'i-0f06b49c1f16dcfde'
    tag_name = 'Stop after'
    tag_value = '2019-12-25'
    ec2_type = 'instance'
    mock_ec2 = mock_client.return_value

    app.new_sqaws.set_tag(region_name, ec2_type, instance_id, tag_name, tag_value, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.create_tags.assert_called_once_with(Resources=[instance_id], Tags=[{
        'Key': tag_name,
        'Value': tag_value
    }])


@patch('app.new_sqaws.boto3.client')
def test_stop_instance(mock_client):
    region_name = 'us-east-1'
    instance_id = 'i-0f06b49c1f16dcfde'
    mock_ec2 = mock_client.return_value

    assert app.new_sqaws.Instance.stop_instance(region_name, instance_id, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.stop_instances.assert_called_once_with(InstanceIds=[instance_id])


@patch('app.new_sqaws.boto3.client')
def test_stop_instance_exception(mock_client):
    # Note: I haven't seen the call to stop_instance fail, but it certainly could.
    def raise_error():
        raise RuntimeError('An error occurred (OperationNotPermitted)...')

    region_name = 'us-east-1'
    instance_id = 'i-0f06b49c1f16dcfde'
    mock_ec2 = mock_client.return_value
    mock_ec2.stop_instances.side_effect = lambda *args, **kw: raise_error()

    assert not app.new_sqaws.Instance.stop_instance(region_name, instance_id, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.stop_instances.assert_called_once_with(InstanceIds=[instance_id])


@patch('app.new_sqaws.boto3.client')
def test_terminate_instance(mock_client):
    region_name = 'us-east-1'
    instance_id = 'i-0f06b49c1f16dcfde'
    mock_ec2 = mock_client.return_value
    blank_instance = app.new_sqaws.Instance(r_name='', r_id='', state='', reason='', r_type='', name='', eks_name='',
                                            os='', s_after='', t_after='', n_state='', contact='', m_price='',
                                            m_server_price='', m_storage_price='', s_after_tag='', t_after_tag='',
                                            n_state_tag='')

    assert app.new_sqaws.Instance.terminate_resource(blank_instance, region_name, instance_id, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.terminate_instances.assert_called_once_with(InstanceIds=[instance_id])


@patch('app.new_sqaws.boto3.client')
def test_terminate_instance_exception(mock_client):
    # Note: I've seen the call to terminate_instance fail when termination protection is enabled
    def raise_error():
        # The real Boto SDK raises botocore.exceptions.ClientError, but this is close enough
        raise RuntimeError('An error occurred (OperationNotPermitted)...')

    region_name = 'us-east-1'
    instance_id = 'i-0f06b49c1f16dcfde'
    mock_ec2 = mock_client.return_value
    mock_ec2.terminate_instances.side_effect = lambda *args, **kw: raise_error()
    blank_instance = app.new_sqaws.Instance(r_name='', r_id='', state='', reason='', r_type='', name='', eks_name='',
                                            os='', s_after='', t_after='', n_state='', contact='', m_price='',
                                            m_server_price='', m_storage_price='', s_after_tag='', t_after_tag='',
                                            n_state_tag='')

    assert not app.new_sqaws.Instance.terminate_resource(blank_instance, region_name, instance_id, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.terminate_instances.assert_called_once_with(InstanceIds=[instance_id])


@patch('app.new_sqaws.boto3.client')
def test_delete_volume(mock_client):
    region_name = 'us-east-1'
    volume_id = 'vol-091303dbe44e6914d'
    mock_ec2 = mock_client.return_value
    blank_volume = app.new_sqaws.Volume(r_name='', r_id='', state='', r_type='', size='', iops='', throughput='',
                                        name='', os='', t_after='', contact='', m_price='', t_after_tag='')

    assert app.new_sqaws.Volume.terminate_resource(blank_volume, region_name, volume_id, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.delete_volume.assert_called_once_with(VolumeId=volume_id)


@patch('app.new_sqaws.boto3.client')
def test_delete_volume_exception(mock_client):
    def raise_error():
        raise RuntimeError('An error occurred (OperationNotPermitted)...')

    region_name = 'us-east-1'
    volume_id = 'vol-091303dbe44e6914d'
    mock_ec2 = mock_client.return_value
    mock_ec2.delete_volume.side_effect = lambda *args, **kw: raise_error()
    blank_volume = app.new_sqaws.Volume(r_name='', r_id='', state='', r_type='', size='', iops='', throughput='',
                                        name='', os='', t_after='', contact='', m_price='', t_after_tag='')

    assert not app.new_sqaws.Volume.terminate_resource(blank_volume, region_name, volume_id, dryrun=False)

    mock_client.assert_called_once_with('ec2', region_name=region_name)
    mock_ec2.delete_volume.assert_called_once_with(VolumeId=volume_id)


@pytest.mark.parametrize('test_dict, expected_stop_result, expected_terminate_result, expected_nagbot_state, '
                         'expected_stop_tag_name, expected_terminate_tag_name, expected_nagbot_state_tag_name', [
                             ({'stop after': '2022-05-10', 'terminate after': '2022-05-11', 'nagbot state': 'running'},
                              '2022-05-10', '2022-05-11', 'running', 'stop after', 'terminate after', 'nagbot state'),
                             ({'Stop After': '2030-07-23', 'Terminate After': '2050-08-10', 'Nagbot State': 'running'},
                              '2030-07-23', '2050-08-10', 'running', 'Stop After', 'Terminate After', 'Nagbot State'),
                             ({'STOP AFTER': '2021-03-04', 'TERMINATE AFTER': '2022-09-12', 'NAGBOT STATE': 'running'},
                              '2021-03-04', '2022-09-12', 'running', 'STOP AFTER', 'TERMINATE AFTER', 'NAGBOT STATE'),
                             ({'stop_after': '2022-05-10', 'terminate_after': '2022-05-11', 'nagbot_state': 'running'},
                              '2022-05-10', '2022-05-11', 'running', 'stop_after', 'terminate_after', 'nagbot_state'),
                             ({'Stop_After': '2030-07-23', 'Terminate_After': '2050-08-10', 'Nagbot_State': 'running'},
                              '2030-07-23', '2050-08-10', 'running', 'Stop_After', 'Terminate_After', 'Nagbot_State'),
                             ({'STOP_AFTER': '2021-03-04', 'TERMINATE_AFTER': '2022-09-12', 'NAGBOT_STATE': 'running'},
                              '2021-03-04', '2022-09-12', 'running', 'STOP_AFTER', 'TERMINATE_AFTER', 'NAGBOT_STATE'),
                             ({'stopafter': '2022-05-10', 'terminateafter': '2022-05-11', 'nagbotstate': 'running'},
                              '2022-05-10', '2022-05-11', 'running', 'stopafter', 'terminateafter', 'nagbotstate'),
                             ({'StopAfter': '2030-07-23', 'TerminateAfter': '2050-08-10', 'NagbotState': 'running'},
                              '2030-07-23', '2050-08-10', 'running', 'StopAfter', 'TerminateAfter', 'NagbotState'),
                             ({'STOPAFTER': '2021-03-04', 'TERMINATEAFTER': '2022-09-12', 'NAGBOTSTATE': 'running'},
                              '2021-03-04', '2022-09-12', 'running', 'STOPAFTER', 'TERMINATEAFTER', 'NAGBOTSTATE'),
                             ({'TerminateAfter': '2022-09-12', 'NagbotState': 'running'}, '', '2022-09-12', 'running',
                              'StopAfter', 'TerminateAfter', 'NagbotState'),
                             ({'StopAfter': '2021-03-04', 'NagbotState': 'running'}, '2021-03-04', '', 'running',
                              'StopAfter', 'TerminateAfter', 'NagbotState'),
                             ({'StopAfter': '2021-03-04', 'TerminateAfter': '2022-09-12'}, '2021-03-04', '2022-09-12',
                              '', 'StopAfter', 'TerminateAfter', 'NagbotState')
                         ])
def test_get_tag_names(test_dict, expected_stop_result, expected_terminate_result, expected_nagbot_state,
                       expected_stop_tag_name, expected_terminate_tag_name, expected_nagbot_state_tag_name):
    stop_after_tag_name, terminate_after_tag_name, nagbot_state_tag_name = \
        app.new_sqaws.get_tag_names(test_dict)
    stop_after = test_dict.get(stop_after_tag_name, '')
    terminate_after = test_dict.get(terminate_after_tag_name, '')
    nagbot_state = test_dict.get(nagbot_state_tag_name, '')

    # Ensure tag value is correct
    assert stop_after == expected_stop_result
    assert terminate_after == expected_terminate_result
    assert nagbot_state == expected_nagbot_state

    # Ensure tag name is set to default if empty string is passed in, otherwise should be the specified tag name
    assert stop_after_tag_name == expected_stop_tag_name
    assert terminate_after_tag_name == expected_terminate_tag_name
    assert nagbot_state_tag_name == expected_nagbot_state_tag_name
