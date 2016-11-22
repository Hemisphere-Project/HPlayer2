#!/bin/bash

if [[ $(uname -m) = armv* ]]; then
	echo "RPi"
else
        echo "not RPi"
fi
