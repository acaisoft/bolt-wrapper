class StatusCodeException(Exception):
    pass


class TimeException(Exception):
    pass


class BodyTextEqualException(Exception):
    pass


class BodyTextContainsException(Exception):
    pass


class MonitoringError(Exception):
    pass


class MonitoringWaitingExpired(Exception):
    pass
