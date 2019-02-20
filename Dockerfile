FROM ubuntu:latest

RUN apt-get update -y
RUN apt-get install -y python-pip python-dev build-essential python3-pip tree

RUN pip3 install -U pip

WORKDIR /app

COPY . .

RUN tree

# COPY requirements.bolt.txt /tmp/requirements.bolt.txt
# RUN pip3 install -r /tmp/requirements.bolt.txt
RUN pip3 install -r requirements.bolt.txt

# COPY _local_packages/* /tmp/_local_packages/
# COPY requirements.txt /tmp/requirements.txt
# RUN pip3 install -r /tmp/requirements.txt
RUN pip3 install -r requirements.txt

# RUN rm /tmp/requirements.txt /tmp/requirements.bolt.txt

# COPY . .
CMD ["./tests/run.sh"]
