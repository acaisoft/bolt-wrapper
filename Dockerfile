FROM python:3.7-alpine as base

RUN apk add --no-cache -U zeromq-dev postgresql-libs gcc g++ musl-dev postgresql-dev curl libnfs-dev nfs-utils
RUN addgroup -S bolt
RUN adduser -D -S bolt -G bolt
RUN chown -R bolt:bolt /home/bolt/

FROM base as builder

# install wrapper/locust requirements
COPY requirements.bolt.txt /home/bolt/requirements.bolt.txt
COPY local_packages/bolt-locust-clients-0.2.tar.gz /home/bolt
RUN pip install -r /home/bolt/requirements.bolt.txt
RUN pip install /home/bolt/bolt-locust-clients-0.2.tar.gz
FROM builder

WORKDIR /home/bolt/tests
COPY . /home/bolt/
RUN chown -R bolt:bolt /home/bolt
# install user-supplied requirements, these will be inserted by packer
RUN pip install -r /home/bolt/requirements.txt
USER bolt
ENV PATH="/home/bolt/.local/bin:${PATH}"

CMD ["python", "-m", "bolt_run"]
