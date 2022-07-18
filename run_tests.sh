#!/bin/bash

set -xe


p4p4tests=(testsampledepot_misc.py
           testsampledepot_ingroup.py
           testsampledepot_mapping.py
           testsampledepot_streams.py
           testsampledepot_integratemissingchange.py
           testsampledepot_obliterate.py
           testsampledepot.py
           testsampledepot_unicodeserver.py
          )

p4svntests=(testp4svn_actions.py
            testp4svn_samples.py)

svnp4tests=(testsvnp4_actions.py
            testsvnp4_exclusion.py
            testsvnp4_wholedir.py)

alltests=()
alltests+=("${p4p4tests[@]}" "${p4svntests[@]}" "${svnp4tests[@]}")

function main {
    ./build_docker.sh

    for test_script in ${alltests[@]}; do
        docker run --rm \
                   --env LANG=en_US.UTF-8 \
                   -v /var/run/docker.sock:/var/run/docker.sock \
                   -v replication-test-vol:/application/test/replication c7_source_replication \
                   python3 /application/test/${test_script} 
        echo $test_script finished 
    done
}

main
