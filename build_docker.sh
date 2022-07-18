#!/bin/bash -xe

# get uid&gid of current user so that we can recreate it in the container.
user_name="$USER"
group_name=`groups $user_name | awk -F: '{print $2}' | awk '{print $1}'`
user_uid=`id -u ${user_name}`
user_gid=`id -g ${user_name}`


image_repo="c7_source_replication"
image_repo_ver="${image_repo}:latest"

# if [ ! -e "./p4" ]; then
#     wget http://filehost.perforce.com/perforce/r18.2/bin.linux26x86_64/p4
# fi

# use --no-cache to force rebuild
docker build --no-cache \
             --build-arg user_uid=${user_uid} \
             --build-arg user_gid=${user_gid} \
             --build-arg user_name=${user_name} \
             --build-arg group_name=${group_name} \
             -t ${image_repo_ver}    \
             .

