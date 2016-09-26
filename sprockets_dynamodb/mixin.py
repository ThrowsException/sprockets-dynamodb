import os

from tornado import web

try:
    import sprockets_influxdb as influxdb
except ImportError:
    influxdb = None

from sprockets_dynamodb import exceptions

INFLUXDB_DATABASE = 'dynamodb'
INFLUXDB_MEASUREMENT = os.getenv('SERVICE', 'DynamoDB')


class DynamoDBMixin(object):
    """The DynamoDBMixin is an opinionated :class:`~tornado.web.RequestHandler`
    mixin class that

    """
    def initialize(self):
        super(DynamoDBMixin, self).initialize()
        self.application.dynamodb.set_error_callback(
            self._on_dynamodb_exception)
        if influxdb:
            self.application.dynamodb.set_instrumentation_callback(
                self._record_dynamodb_execution)

    @staticmethod
    def _on_dynamodb_exception(error):
        """Dynamically handle DynamoDB exceptions, returning HTTP error
        responses.

        :param exceptions.DynamoDBException error:

        """
        if isinstance(error, exceptions.ConditionalCheckFailedException):
            raise web.HTTPError(409, reason='Condition Check Failure')
        elif isinstance(error, (exceptions.ThroughputExceeded,
                                exceptions.ThrottlingException)):
            raise web.HTTPError(429, reason='Too Many Requests')
        raise web.HTTPError(500, reason=str(error))

    def _record_dynamodb_execution(self, measurements):
        for row in measurements:
            measurement = influxdb.Measurement(INFLUXDB_DATABASE,
                                               INFLUXDB_MEASUREMENT)
            measurement.set_timestamp('timestamp', row.timestamp)
            measurement.set_tag('action', row.action)
            measurement.set_tag('table', row.table)
            measurement.set_tag('attempt', row.attempt)
            for key in {'SERVICE', 'ENVIRONMENT'}:
                if os.environ.get(key):
                    measurement.set_tag(key.lower(), os.environ[key])
            if row.error:
                measurement.set_tag('error', row.error)
            if hasattr(self, 'correlation_id'):
                measurement.set_field('correlation_id', self.correlation_id)
            measurement.set_field('duration', row.duration)
            influxdb.add_measurement(measurement)
