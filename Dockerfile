FROM ubuntu:latest

RUN apt-get update -y
RUN apt-get install -y python-pip python-dev build-essential python3-pip tree

RUN pip3 install -U pip

WORKDIR /app

COPY . .
RUN ls
RUN tree

COPY src/_local_packages/* /tmp/_local_packages/
COPY src/requirements.bolt.txt /tmp/requirements.bolt.txt
RUN pip3 install -r /tmp/requirements.bolt.txt

COPY ./src .
RUN pip3 install -r /tmp/requirements.txt

CMD ["./tests/run.sh"]
