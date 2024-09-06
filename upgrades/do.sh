#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "USAGE: $0 <hostname> \"<commands-to-execute>\""
    exit 1
fi


ssh root@$1.local $2 