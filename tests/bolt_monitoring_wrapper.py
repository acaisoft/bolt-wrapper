import os
import threading
import importlib
import datetime
import time

from bolt_api_client import BoltAPIClient
from bolt_exceptions import MonitoringExit
from bolt_logger import setup_custom_logger

# envs
BOLT_DEADLINE = os.getenv('BOLT_DEADLINE')
MONITORING_SENDING_INTERVAL = os.getenv('MONITORING_SENDING_INTERVAL')
DURING_TEST_INTERVAL = os.getenv('DURING_TEST_INTERVAL')

monitoring_module = importlib.import_module('bolt_monitoring.monitoring')
monitoring_func = getattr(monitoring_module, 'monitoring')
monitoring_deadline = datetime.datetime.fromisoformat(BOLT_DEADLINE).timestamp()

logger = setup_custom_logger(__name__)
bolt_api_client = BoltAPIClient()


def run_monitoring(stop_during_test_func=None):
    """
    Execute monitoring function every X sec
    """
    try:
        json_data = monitoring_func()
        if json_data is not None:
            bolt_api_client.insert_execution_metrics_data({
                'timestamp': datetime.datetime.now().isoformat(), 'data': json_data})
    except Exception as e:
        # try to stop during test
        if stop_during_test_func is not None:
            stop_during_test_func()
        raise MonitoringExit(e)
    else:
        time.sleep(int(MONITORING_SENDING_INTERVAL))
        if time.time() > monitoring_deadline:
            # try to stop during test
            if stop_during_test_func is not None:
                stop_during_test_func()
            return
        else:
            run_monitoring(stop_during_test_func)


def run_during_test():
    """
    Execute during test function every X sec using threading (background)
    """
    during_test_func = getattr(monitoring_module, 'during_test', None)
    if during_test_func is not None:
        stop_func = threading.Event()

        def loop():
            while not stop_func.wait(int(DURING_TEST_INTERVAL)):
                during_test_func()

        threading.Thread(target=loop).start()
        return stop_func.set
    else:
        return None


def main():
    logger.info('Start executing monitoring/during_test')
    stop_during_test_func = run_during_test()
    run_monitoring(stop_during_test_func)
