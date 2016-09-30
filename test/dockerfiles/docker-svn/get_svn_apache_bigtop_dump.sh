#!/bin/env bash


echo "Creating svn sample repos from http://svn.apache.org/repos/asf/bigtop"
echo "dump http://svn.apache.org/repos/asf/bigtop to svn.apache.org_repos_asf_bigtop.dump"
echo "This may take a while..."
svn log http://svn.apache.org/repos/asf/bigtop/ >./apache.asf.bigtop.log

rm -rf ./svn.apache.org_repos_asf_bigtop.dump
cat ./apache.asf.bigtop.log  | grep "^r[0-9]"  | awk '{print $1}'  | \
    cut -c 2- | sort  -n | \
    awk '{print "svnrdump dump http://svn.apache.org/repos/asf/bigtop/ --incremental -r " $1 " >>./svn.apache.org_repos_asf_bigtop.dump"}' | bash

