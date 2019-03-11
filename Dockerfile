FROM ubuntu:latest

RUN apt-get update -y && apt-get install -y \
    python-pip \
	python-dev \
	build-essential \
	python3-pip \
	&& pip3 install -U pip \
	&& mkdir -p /app/tests

WORKDIR /app/tests

COPY ./src/requirements.txt /app/requirements.txt
RUN pip3 install -r /app/requirements.txt

COPY ./src/requirements.txt /app/requirements.bolt.txt
RUN pip3 install -r /app/requirements.bolt.txt

COPY ./src/ /app/

CMD ["python3", "-m", "run"]
