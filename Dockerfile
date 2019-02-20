FROM ubuntu:latest

RUN apt-get update -y
RUN apt-get install -y python-pip python-dev build-essential python3-pip tree

RUN pip3 install -U pip

WORKDIR /app

COPY . .
RUN pip3 install -r requirements.txt
RUN pip3 install -r requirements.bolt.txt

CMD ["./tests/run.sh"]
