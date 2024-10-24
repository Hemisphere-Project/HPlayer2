#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "USAGE: $0 <hostname> <script-to-execute>"
    exit 1
fi


ssh root@$1 "bash -s" < $2 