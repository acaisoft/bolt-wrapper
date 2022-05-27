# Copyright (c) 2022 Acaisoft
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

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
                    break
            finally:
                time.sleep(7)

    def run(self):
        logger.info('Starting supervisor ...')
        t = threading.Thread(target=self.loop)
        t.daemon = True
        t.start()
