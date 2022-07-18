# Synopsis

This set of scripts is developed to continuously replicate changes
between p4 and svn servers.

Features:

-   P4(Perforce) to P4 replication
-   P4 to SVN(Subversion) replication
-   SVN to P4 replication
-   APIs, p4python and pysvn, are used.
-   configurable source counter, changeset to stop replication,
    maximum number of changelists to replicate
-   No workspace/working copy need to be created manually
-   Only files modified in a change will be updated and submitted.
-   symlinks supported
-   executable bits are replicated
-   svn externals supported



# Preparation

The replication scripts run in docker containers. They should be able to 
work on all Linux distros, provided docker being installed properly.

## Docker containers are used for testing.
Install docker by following instructions in https://docs.docker.com/install/linux/docker-ce/centos/
 
## build source replication docker image
    ```bash
    # this script builds docker image "c7_source_replication:latest" on your machine
    ./build_docker.sh
    
    docker images | grep c7_source_replication || echo "failed"
    ```

# Examples
SVN-P4 rep Example

    ```bash
    test -n "${BWREPL_SOURCE_SVNDIR}" 
    test -n "${BWREPL_DEST_P4DEPOT}"
    test -n "${BWREPL_SOURCE_SVNSERVER}"
    test -n "${BWREPL_DEST_P4SERVER}"
    
    test -n "${SCMREP_SOURCE_USER}"
    test -n "${SCMREP_SOURCE_PASS}"
    test -n "${SCMREP_TARGET_USER}"
    test -n "${SCMREP_TARGET_PASS}"
    
    
    SOURCE_COUNTER=${SOURCE_COUNTER:-0}
    
    WORKSPACE=./workspace
    export TMPDIR=${WORKSPACE}/svn_tmp
    mkdir -p ${WORKSPACE}
    mkdir -p ${TMPDIR}
    
    # create source/destination view mapping config files
    SRC_VIEWMAP_CFG="${WORKSPACE}/source_svn_dir.cfg"
    DST_VIEWMAP_CFG="${WORKSPACE}/target_p4_mapping.cfg"
    echo "${BWREPL_SOURCE_SVNDIR}" > ${SRC_VIEWMAP_CFG}
    echo "${BWREPL_DEST_P4DEPOT} ./..." > ${DST_VIEWMAP_CFG}
    
    # workspace root directory for replication
    WS_ROOT="${WORKSPACE}/replication_rootdir"
    rm -rf ${WS_ROOT}
    mkdir -p ${WS_ROOT}
    
    # Go Go Go
    # use -m to specify a maximum number of change to replicate
    cmd="${PWD}/SvnP4Replicate.py \
        --source-port $BWREPL_SOURCE_SVNSERVER \
        --target-port $BWREPL_DEST_P4SERVER \
        --source-replicate-dir-cfgfile ${SRC_VIEWMAP_CFG} \
        --target-workspace-view-cfgfile ${DST_VIEWMAP_CFG} \
        -r ${WS_ROOT} \
        --source-counter ${SOURCE_COUNTER} \
        --svn-ignore-externals \
        --verbose INFO \
        -m 512"
    
    echo ${cmd}
    
    temp_env_file=$(mktemp)
    function remove_tmp_env_file() {
    	rm -f ${temp_env_file}
    }
    trap remove_tmp_env_file EXIT
    
    cat >$temp_env_file <<EOF
    SCMREP_SOURCE_USER=${SCMREP_SOURCE_USER}
    SCMREP_SOURCE_PASS=${SCMREP_SOURCE_PASS}
    SCMREP_TARGET_USER=${SCMREP_TARGET_USER}
    SCMREP_TARGET_PASS=${SCMREP_TARGET_PASS}
    LANG=en_US.UTF-8
    TMPDIR=${TMPDIR}
    EOF
    
    rep_docker_image=bw-docker-01.artifactory.bigworldtech.com/build/c7_source_replication
    docker run --name ${JOB_NAME} --user $UID --rm --env-file ${temp_env_file} -v $WORKSPACE:$WORKSPACE ${rep_docker_image} $cmd
    ```

# Tests

## Tests are available in ./test directory.

   
- create the test server containers, it takes a while:
    ```bash
    # this script builds
    #   buildtest_p4d_sampledepot, with perforce sample depot, and
    #   buildtest_svn_sampledepot, with a mirror of <http://svn.apache.org/repos/asf/bigtop>

    ./setup_test_dockers.sh

    docker images | grep buildtest_p4d_sampledepot || echo "failed"
    docker images | grep buildtest_svn_sampledepot || echo "failed"

    ```

- test scripts require a docker volume precreated for configuration files
  and temporary replication root
  ```bash
  docker volume create replication-test-vol
  ```

## run tests

Tests run in docker containers.

- run all tests

    ```bash
    # it took 4729s to run 204 tests on my VM.
    docker run -it --rm \
               --env LANG=en_US.UTF-8 \
               -v /var/run/docker.sock:/var/run/docker.sock \
               -v replication-test-vol:/application/test/replication \
               c7_source_replication \
               python -m unittest discover -f
    ```

- run a test module
    ```bash
    docker run -it --rm \
               --env LANG=en_US.UTF-8 \
               -v /var/run/docker.sock:/var/run/docker.sock \
               -v replication-test-vol:/application/test/replication \
               c7_source_replication \
               python ./test/testsampledepot.py -f
    ```

-   p4p4 replication tests
    -   testsampledepot_ingroup.py
    -   testsampledepot_integratemissingchange.py
    -   testsampledepot_mapping.py
    -   testsampledepot_misc.py
    -   testsampledepot_obliterate.py
    -   testsampledepot.py
    -   testsampledepot_streams.py
    -   testsampledepot_unicodeserver.py

-   svnp4 replication tests
    -   testsvnp4_actions.py
    -   testsvnp4_exclusion.py
    -   testsvnp4_wholedir.py

-   p4svn replication tests
    -   testp4svn_actions.py
    -   testp4svn_samples.py


# License

> Copyright (c) 2019, BigWorld Pty. Ltd.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are met:
>
> 1.  Redistributions of source code must retain the above copyright notice, this
>     list of conditions and the following disclaimer.
> 2.  Redistributions in binary form must reproduce the above copyright notice,
>     this list of conditions and the following disclaimer in the documentation
>     and/or other materials provided with the distribution.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
> ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
> WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
> DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
> ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
> (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
> LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
> ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
> (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
> SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
>
> The views and conclusions contained in the software and documentation are those
> of the authors and should not be interpreted as representing official policies,
> either expressed or implied, of the FreeBSD Project.

