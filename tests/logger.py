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
            logger.info(f'Function {func.__name__} ran in {round(end - start, 2)}s. Args: {args}. Kwargs: {kwargs}')
            return result
        return wrapper
    return decorator
