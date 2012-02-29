#!/bin/bash
/usr/bin/curl "http://localhost:8983/solr/$1/dataimport_aws?command=full-import&clean=true&commit=true&wt=json&indent=true"
