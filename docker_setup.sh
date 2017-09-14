#!/bin/bash

apt install python3
python3 docker_setup.py -c $1 -p $2 -t $3
