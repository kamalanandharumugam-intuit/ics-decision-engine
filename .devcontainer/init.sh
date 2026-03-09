#!/bin/sh
set -e

# Install Python 3.12 and set as global
asdf install python 3.12.13
asdf global python 3.12.13

# Install pip dependencies
pip install --upgrade pip
pip install -r /workspace/ics-decision-engine/requirements.txt
