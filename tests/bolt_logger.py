import logging
import time

from functools import wraps


def setup_custom_logger(name=None):
    formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger


def log_time_execution(logger):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            end = time.time()
            gql_summary = []
            if type(result) is dict:
                for k, v in result.items():
                    if type(v) is dict:
                        affected_rows = v.get('affected_rows', None)
                        if affected_rows is not None:
                            gql_summary.append(f'affected {affected_rows} rows in {k}')
            logger.info(f'Function {func.__name__} ran in {round(end - start, 2)}s {", ".join(gql_summary)}.')
            return result
        return wrapper
    return decorator
