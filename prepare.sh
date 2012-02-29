#!/bin/bash

dirname=`dirname $0`

source ${dirname}/config.sh
python ${dirname}/prepare.py ${EC2_KEY_ID} ${EC2_SECRET_KEY}
