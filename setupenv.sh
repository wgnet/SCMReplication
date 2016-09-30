#!/bin/bash

set -e

# for p4python
yum install -y gcc
yum install -y gcc-c++
yum install -y python-devel

# pysvn/svn
yum install -y epel-release
yum install -y pysvn
yum install -y svn

yum install -y python-pip
pip install virtualenv

# create virtualenv
virtualenv --system-site-packages -p /usr/bin/python2.7 buildvenv
source ./buildvenv/bin/activate

# install required python modules in virtualenv
pip install -r ./requirements.txt
