#!/bin/env bash

set -e

# create p4 docker image
cd docker-p4
docker build -t buildtest_p4d_sampledepot .
cd ..

# create svn docker image
cd docker-svn
./get_svn_apache_bigtop_dump.sh
docker build -t buildtest_svn_sampledepot .

cd ..
