import enum


class Status(enum.Enum):
    ERROR = 'ERROR'
    FAILED = 'FAILED'
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    SUCCEEDED = 'SUCCEEDED'
    TERMINATED = 'TERMINATED'
    FINISHED = 'FINISHED'