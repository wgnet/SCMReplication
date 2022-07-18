#!/bin/bash

#
# test svn server to test p4 server
#

WORKDIR=$(dirname $PWD)
srcport=""
srcuser=""
srcpass=""
src_mapping="$WORKDIR/cfg/svn_src_mapping.cfg"

dstport=""
dstuser=""
dstpass=""
dst_mapping="$WORKDIR/cfg/p4_dst_mapping.cfg"

wsroot=$PWD/replicating
mkdir -p $wsroot

cmd="$WORKDIR/SvnP4Replicate.py --source-port $srcport \
                                --source-user $srcuser \
                                --source-passwd $srcpass \
                                --target-port $dstport \
                                --target-user $dstuser \
                                --target-passwd $dstpass \
                                --source-workspace-view-cfgfile $src_mapping \
                                --target-workspace-view-cfgfile $dst_mapping \
                                -r $wsroot"


docker_cmd="docker run --name replication --rm -e \"LANG=en_US.UTF-8\" -v $WORKDIR:$WORKDIR c7_source_replication $cmd"
echo $docker_cmd 
