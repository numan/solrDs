#!/bin/bash
/usr/bin/curl --silent "http://localhost:8983/solr/$1/dataimport_aws?command=status&wt=json&indent=true"
