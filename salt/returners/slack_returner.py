# -*- coding: utf-8 -*-
'''
Return salt data via slack

.. versionadded:: 2015.5.0

The following fields can be set in the minion conf file::

    slack.channel (required)
    slack.api_key (required)
    slack.username (required)
    slack.as_user (required to see the profile picture of your bot)
    slack.profile (optional)

Alternative configuration values can be used by prefacing the configuration.
Any values not found in the alternative configuration will be pulled from
the default location::

    slack.channel
    slack.api_key
    slack.username
    slack.as_user

Slack settings may also be configured as::

    slack:
        channel: RoomName
        api_key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        username: user
        as_user: true

    alternative.slack:
        room_id: RoomName
        api_key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        from_name: user@email.com

    slack_profile:
        api_key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        from_name: user@email.com

    slack:
        profile: slack_profile
        channel: RoomName

    alternative.slack:
        profile: slack_profile
        channel: RoomName

To use the Slack returner, append '--return slack' to the salt command.

.. code-block:: bash

    salt '*' test.ping --return slack

To use the alternative configuration, append '--return_config alternative' to the salt command.

.. code-block:: bash

    salt '*' test.ping --return slack --return_config alternative
'''
from __future__ import absolute_import

# Import Python libs
import pprint
import logging

# Import 3rd-party libs
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from requests.exceptions import ConnectionError
# pylint: disable=import-error,no-name-in-module,redefined-builtin
from salt.ext.six.moves.urllib.parse import urljoin as _urljoin  # pylint: disable=import-error,no-name-in-module
import salt.ext.six.moves.http_client
# pylint: enable=import-error,no-name-in-module,redefined-builtin

# Import Salt Libs
import salt.returners

log = logging.getLogger(__name__)

__virtualname__ = 'slack'


def _get_options(ret=None):
    '''
    Get the slack options from salt.
    '''

    defaults = {'channel': '#general'}

    attrs = {'slack_profile': 'profile',
             'channel': 'channel',
             'username': 'username',
             'as_user': 'as_user',
             'api_key': 'api_key',
             }

    profile_attr = 'slack_profile'

    profile_attrs = {'from_jid': 'from_jid',
                     'api_key': 'api_key',
                     'api_version': 'api_key'
                     }

    _options = salt.returners.get_returner_options(__virtualname__,
                                                   ret,
                                                   attrs,
                                                   profile_attr=profile_attr,
                                                   profile_attrs=profile_attrs,
                                                   __salt__=__salt__,
                                                   __opts__=__opts__,
                                                   defaults=defaults)
    return _options


def __virtual__():
    '''
    Return virtual name of the module.

    :return: The virtual name of the module.
    '''
    if not HAS_REQUESTS:
        return False

    return __virtualname__


def _query(function, api_key=None, method='GET', data=None):
    '''
    Slack object method function to construct and execute on the API URL.

    :param api_key:     The Slack api key.
    :param function:    The Slack api function to perform.
    :param method:      The HTTP method, e.g. GET or POST.
    :param data:        The data to be sent for POST method.
    :return:            The json response from the API call or False.
    '''
    headers = {}
    query_params = {}

    if data is None:
        data = {}

    ret = {'message': '',
           'res': True}

    slack_functions = {
        'rooms': {
            'request': 'channels.list',
            'response': 'channels',
        },
        'users': {
            'request': 'users.list',
            'response': 'members',
        },
        'message': {
            'request': 'chat.postMessage',
            'response': 'channel',
        },
    }

    if not api_key:
        try:
            options = __salt__['config.option']('slack')
            if not api_key:
                api_key = options.get('api_key')
        except (NameError, KeyError, AttributeError):
            log.error('No Slack api key found.')
            ret['message'] = 'No Slack api key found.'
            ret['res'] = False
            return ret

    api_url = 'https://slack.com'
    base_url = _urljoin(api_url, '/api/')
    path = slack_functions.get(function).get('request')
    url = _urljoin(base_url, path, False)
    query_params['token'] = api_key

    try:
        result = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=query_params,
            data=data,
            verify=True,
        )
    except ConnectionError as e:
        ret['message'] = e
        ret['res'] = False
        return ret

    if result.status_code == salt.ext.six.moves.http_client.OK:
        result = result.json()
        response = slack_functions.get(function).get('response')
        if 'error' in result:
            ret['message'] = result['error']
            ret['res'] = False
            return ret
        ret['message'] = result.get(response)
        return ret
    elif result.status_code == salt.ext.six.moves.http_client.NO_CONTENT:
        return True
    else:
        log.debug(url)
        log.debug(query_params)
        log.debug(data)
        log.debug(result)
        if 'error' in result:
            ret['message'] = result['error']
            ret['res'] = False
            return ret
        ret['message'] = result
        return ret


def _post_message(channel,
                  message,
                  username,
                  as_user,
                  api_key=None):
    '''
    Send a message to a Slack room.
    :param channel:     The room name.
    :param message:     The message to send to the Slack room.
    :param username:    Specify who the message is from.
    :param as_user:     Sets the profile picture which have been added through Slack itself.
    :param api_key:     The Slack api key, if not specified in the configuration.
    :param api_version: The Slack api version, if not specified in the configuration.
    :return:            Boolean if message was sent successfully.
    '''

    parameters = dict()
    parameters['channel'] = channel
    parameters['username'] = username
    parameters['as_user'] = as_user
    parameters['text'] = '```' + message + '```'  # pre-formatted, fixed-width text

    result = _query(function='message',
                    api_key=api_key,
                    method='POST',
                    data=parameters)

    log.debug('result {0}'.format(result))
    if result:
        return True
    else:
        return False


def returner(ret):
    '''
    Send an slack message with the data
    '''

    _options = _get_options(ret)

    channel = _options.get('channel')
    username = _options.get('username')
    as_user = _options.get('as_user')
    api_key = _options.get('api_key')

    if not channel:
        log.error('slack.channel not defined in salt config')
        return

    if not username:
        log.error('slack.username not defined in salt config')
        return

    if not as_user:
        log.error('slack.as_user not defined in salt config')
        return

    if not api_key:
        log.error('slack.api_key not defined in salt config')
        return

    message = ('id: {0}\r\n'
               'function: {1}\r\n'
               'function args: {2}\r\n'
               'jid: {3}\r\n'
               'return: {4}\r\n').format(
                    ret.get('id'),
                    ret.get('fun'),
                    ret.get('fun_args'),
                    ret.get('jid'),
                    pprint.pformat(ret.get('return')))

    slack = _post_message(channel,
                          message,
                          username,
                          as_user,
                          api_key)
    return slack
