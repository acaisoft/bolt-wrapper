FROM python:3.7-alpine

RUN apk add --no-cache -U zeromq-dev \
    && apk add --no-cache -U --virtual build-deps g++ \
    && addgroup -S bolt \
    && adduser -D -S bolt -G bolt \
    && pip install gevent \
    && chown -R bolt:bolt /home/bolt/

WORKDIR /home/bolt/tests

COPY ./src/requirements.bolt.txt /home/bolt/requirements.bolt.txt
RUN pip install -r /home/bolt/requirements.bolt.txt

COPY ./src/ /home/bolt/
RUN chown -R bolt:bolt /home/bolt
USER bolt
ENV PATH="/home/bolt/.local/bin:${PATH}"

RUN pip install -r /home/bolt/requirements.txt

CMD ["python", "-m", "run"]
