#!/bin/bash

#
# test svn server to test p4 server
#

srcport="svn://172.17.0.3:3690/repos"
srcuser="guest"
srcpass="guest"
src_mapping="svn_src_mapping.cfg"

dstport="172.17.0.2:1666"
dstuser="bruno"
dstpass="' '"
dst_mapping="p4_dst_mapping.cfg"

wsroot="$PWD/replicating"

mkdir -p $wsroot

cmd="../SvnP4Replicate.py --source-port $srcport \
                          --source-user $srcuser \
                          --source-passwd $srcpass \
                          --target-port $dstport \
                          --target-user $dstuser \
                          --target-passwd $dstpass \
                          --source-workspace-view-cfgfile $src_mapping \
                          --target-workspace-view-cfgfile $dst_mapping \
                          -r $wsroot"

echo $cmd
