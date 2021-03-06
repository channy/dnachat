# -*-coding:utf8-*-
import boto
import json

from boto import sqs, sns

from .logger import logger
from .models import ChannelJoinInfo
from .settings import conf


class NotificationSender(object):
    def __init__(self):
        sqs_conn = sqs.connect_to_region('ap-northeast-1')
        self.queue = sqs_conn.get_queue(conf['NOTIFICATION_QUEUE_NAME'])
        self.sns_conn = sns.connect_to_region('ap-northeast-1')

    def start(self):
        """
        SQS message has to have key 'message', 'writer', 'channel', 'published_at'
        """

        task = self.publish()
        task.next()
        while True:
            queue_message = self.queue.read(wait_time_seconds=5)
            if not queue_message:
                continue
            task.send(queue_message)

    def publish(self):
        try:
            while True:
                queue_message = (yield)
                message = json.loads(queue_message.get_body())
                logger.debug('Received: %s' % message)
                for join_info in ChannelJoinInfo.by_channel(message['channel']):
                    endpoint_arn = conf['PROTOCOL'].get_user_by_id(join_info.user_id).endpoint_arn
                    if endpoint_arn:
                        self.send_via_gcm(endpoint_arn, message)
                    elif callable(conf['SMS_SENDER']) and join_info.user_id != message['writer']:
                        logger.info('Send sms: {0} {1}'.format(join_info.user_id, message['published_at']))
                        conf['SMS_SENDER'](join_info, message)
                self.queue.delete_message(queue_message)
        except GeneratorExit:
            pass

    def send_via_gcm(self, endpoint_arn, message):
        message['gcm_type'] = 'chat'
        gcm_json = json.dumps(dict(data=message), ensure_ascii=False)
        data = dict(default='default message', GCM=gcm_json)
        try:
            result = self.sns_conn.publish(
                message=json.dumps(data, ensure_ascii=False),
                target_arn=endpoint_arn,
                message_structure='json'
            )
        except boto.exception.BotoServerError, e:
            print e
            logger.error('BotoError', exc_info=True)
        else:
            logger.debug('\tGCM: %s' % str(result))
