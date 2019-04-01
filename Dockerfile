FROM python:3.7-alpine as base

RUN addgroup -S bolt
RUN adduser -D -S bolt -G bolt
RUN chown -R bolt:bolt /home/bolt/

FROM base as builder

RUN apk add --no-cache -U zeromq-dev
RUN apk add --no-cache -U --virtual build-deps g++
COPY tests/requirements.txt /home/bolt/requirements.txt
RUN pip install --install-option="--prefix=/install" -r /home/bolt/requirements.txt
RUN apk del build-deps

FROM base
COPY --from=builder /install /usr/local

WORKDIR /home/bolt/tests
COPY . /home/bolt/
RUN chown -R bolt:bolt /home/bolt
USER bolt
ENV PATH="/home/bolt/.local/bin:${PATH}"

CMD ["python", "-m", "run"]
