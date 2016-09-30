#!/bin/bash

#
# test sample p4 server to test svn server
#

srcport="172.17.0.2:1666"
srcuser="bruno"
srcpass="' '"
src_mapping="p4_src_mapping.cfg"

dstport="svn://172.17.0.3:3690/repos"
dstuser="guest"
dstpass="guest"
dst_mapping="svn_dst_mapping.cfg"

wsroot="$PWD/replicating"

mkdir -p $wsroot

cmd="../P4SvnReplicate.py --source-port $srcport \
                          --source-user $srcuser \
                          --source-passwd $srcpass \
                          --target-port $dstport \
                          --target-user $dstuser \
                          --target-passwd $dstpass \
                          --source-workspace-view-cfgfile $src_mapping \
                          --target-workspace-view-cfgfile $dst_mapping \
                          -r $wsroot"

echo $cmd
