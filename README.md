<div id="table-of-contents">
<h2>Table of Contents</h2>
<div id="text-table-of-contents">
<ul>
<li><a href="#orga9d4f72">1. Synopsis</a></li>
<li><a href="#org031b282">2. Examples</a></li>
<li><a href="#org5c67076">3. Installation</a></li>
<li><a href="#orgc17d1da">4. Tests</a>
<ul>
<li><a href="#orgfdb6181">4.1. Tests are available in ./test directory.</a></li>
<li><a href="#orgbd9c33c">4.2. Docker containers are used for testing.</a></li>
<li><a href="#orgd8fbf37">4.3. run tests</a></li>
</ul>
</li>
<li><a href="#org28b1388">5. License</a></li>
</ul>
</div>
</div>


<a id="orga9d4f72"></a>

# Synopsis

This set of scripts was developed to continuously replicate changes
between Perforce and Subversion servers. It is released under the BSD license.
Perforce to Perforce replication scripts were based on the code written by
Sven Erik Knop.

Features:

-   APIs, p4python and pysvn, are used.
-   configurable source counter, changeset to stop replication,
    maximum number of changelists to replicate
-   No workspace/working copy need to be created manually
-   Only files modified in a change will be updated and submitted.
-   symlinks supported
-   executable bits are replicated
-   svn externals supported


<a id="org031b282"></a>

# Examples

Configuration/command examples can be found in the directory:

	./cfg


<a id="org5c67076"></a>

# Installation

The scripts are tested in Centos 7. They should be able to work with
all Linux distros, provided libs/python modules being installed
properly.

To setup environment in Centos 7:

    sudo ./setupenv.sh
    source buildvenv/bin/activate


<a id="orgc17d1da"></a>

# Tests


<a id="orgfdb6181"></a>

## Tests location

Tests are available in the following location:

    ./test

<a id="orgbd9c33c"></a>

## Docker containers are used for testing.

-   create the test containers, it may take a while:
    
        sudo yum install -y docker
        sudo systemctl start docker
        cd test/dockerfiles
        # "sudo" in case root permission is needed to build Dockerfiles, Or
        # add user to docker group
        #   # sudo groupadd docker
        #   # sudo usermod -aG docker $USER
        #   log out and in again
        sudo ./setup_test_dockers.sh

-   New docker containers will be created:
    -   buildtest\_p4d\_sampledepot with perforce sample depot, and
    -   buildtest\_svn\_sampledepot with a mirror of <http://svn.apache.org/repos/asf/bigtop>


<a id="orgd8fbf37"></a>

## Run tests

-   run all tests

        # Make sure you are in ./test
        # If you ran the docker containers setup script, you will need to do:
        #   cd ..
        python -m unittest discover -f
        # Ran 204 tests in 4729.528s in my VM.

-   p4p4 replication tests
    -   testsampledepot\_ingroup.py
    -   testsampledepot\_integratemissingchange.py
    -   testsampledepot\_mapping.py
    -   testsampledepot\_misc.py
    -   testsampledepot\_obliterate.py
    -   testsampledepot.py
    -   testsampledepot\_streams.py
    -   testsampledepot\_unicodeserver.py

-   svnp4 replication tests
    -   testsvnp4\_actions.py
    -   testsvnp4\_exclusion.py
    -   testsvnp4\_wholedir.py

-   p4svn replication tests
    -   testp4svn\_actions.py
    -   testp4svn\_samples.py


<a id="org28b1388"></a>

# License

> Copyright (c) 2016, BigWorld Pty. Ltd.
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

