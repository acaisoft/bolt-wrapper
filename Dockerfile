FROM python:3.7-slim as base

RUN apt-get update -y

RUN ln -fs /usr/share/zoneinfo/Europe/Warsaw /etc/localtime
RUN export DEBIAN_FRONTEND=noninteractive
RUN apt-get install -y tzdata
RUN apt-get install -y libzmq3-dev

RUN apt-get install -y python-dev build-essential python3-pip libtool pkg-config autoconf automake gcc g++ musl-dev postgresql postgresql-contrib curl libnfs-dev libffi-dev libevent-dev

RUN addgroup bolt
RUN adduser --system bolt
RUN adduser bolt bolt
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
