import os
import signal
import time
import threading

from bolt_api_client import BoltAPIClient
from bolt_enums import Status
from bolt_logger import setup_custom_logger


EXECUTION_ID = os.getenv('BOLT_EXECUTION_ID')

bolt_api_client = BoltAPIClient()
logger = setup_custom_logger(__name__)


class Supervisor(object):
    @staticmethod
    def loop():
        while True:
            try:
                execution = bolt_api_client.get_execution(EXECUTION_ID)
                status = execution['execution'][0]['status']
            except Exception as ex:
                logger.info(f'Supervisor exception. Cannot execute status for execution | {ex}')
            else:
                logger.info(f'Supervisor. Status of flow is {status}')
                if status in (Status.FAILED.value, Status.ERROR.value, Status.TERMINATED.value):
                    logger.info('Supervisor. Flow crashed/terminated. Call signal SIGTERM and exit')
                    os.kill(os.getpid(), signal.SIGTERM)
                    raise SystemExit('Exit from interpreter')
            finally:
                time.sleep(7)

    def run(self):
        logger.info('Starting supervisor ...')
        t = threading.Thread(target=self.loop)
        t.daemon = True
        t.start()
