#!/bin/bash

apt install python3
python3 docker_setup.py -p $1 -t $2
