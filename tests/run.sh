#!/usr/bin/env bash

set -e
set +x

locust -f wrapper.py -c ${NUMBER_OF_USERS:=1000} -r ${HATCH_RATE:=1000} --no-web --run-time ${RUN_TIME:=600} --csv=test_report
