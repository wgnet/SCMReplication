'''Build replication test case base class, creates and deletes dockers
in setup and teardown methods.
'''

from collections import defaultdict
from datetime import datetime
import time
import unittest
import tempfile
import shutil

from testcommon import (BUILD_TEST_P4D_DOCKER_IMAGE,
                        BUILD_TEST_SVN_DOCKER_IMAGE,
                        BUILD_TEST_P4D_USER,
                        BUILD_TEST_SVN_USER)
from lib.p4server import P4Server
from lib.SvnPython import SvnPython
from lib.dockerclient import DockerClient
from lib.buildlogger import getLogger, set_logging_color_format
set_logging_color_format()
logger = getLogger(__name__)
logger.setLevel('INFO')

def check_p4d_running(p4d_docker, timeout=10):
    '''check if p4d is up and running in docker.

    When stating a new docker container, p4d which is running in the
    container takes a little time to start. So we cannot connect to it
    right after creation of container. A hard coded sleep(3) was used
    to avoid exceptions raised by p4d.connect(). It works but ugly. In
    this change, I added a check_p4d_running() function to try-connect
    p4d within a certain timeout(10 seconds for now). A separate
    Exception would be raised if p4d failed to start in 10 seconds.
    '''
    p4_user = BUILD_TEST_P4D_USER
    p4d_ip = p4d_docker.get_container_ip_addr()
    src_p4 = P4Server('%s:1666' % p4d_ip, p4_user, login=False)

    start_time = datetime.now()
    while (datetime.now() - start_time).seconds < timeout:
        try:
            src_p4.connect()
            logger.debug('p4d is now up and running')
            return
        except:
            time.sleep(.1)
            logger.debug('p4d not yet ready.')

    raise Exception('p4d not up after %d seconds in %s' % (timeout, p4d_ip))


def create_p4_docker_cli():
    '''create a new docker container and start it

    used as default_factory of defaultdict
    '''
    logger.info('creating new container')
    docker_cli = DockerClient(BUILD_TEST_P4D_DOCKER_IMAGE)
    docker_cli.create_container()
    docker_cli.start_container()

    try:
        check_p4d_running(docker_cli)
    except Exception, e:
        docker_cli.stop_container()
        docker_cli.delete_container()
        raise e

    return docker_cli


def check_svn_running(svn_docker, timeout=10):
    '''check if svn is up and running in docker.

    probably need something similar with check_p4d_running()
    '''
    svn_user = BUILD_TEST_SVN_USER
    svn_passwd = 'guest'
    svn_ip = svn_docker.get_container_ip_addr()
    svn_url = 'svn://%s:3690/repos' % svn_ip
    svn = SvnPython(svn_url, svn_user, svn_passwd)

    start_time = datetime.now()
    while (datetime.now() - start_time).seconds < timeout:
        svn_dir='/'
        try:
            svn_list = svn.run_list(svn_url)
            logger.debug(svn_list)
            svn.client = None
            return
        except Exception, e:
            time.sleep(.1)
            logger.debug('svn not yet ready. %s' % e)

    raise Exception('svn not up after %d seconds in %s' % (timeout, svn_ip))


def create_svn_docker_cli():
    '''create a new docker container and start it

    used as default_factory of defaultdict
    '''
    docker_cli = DockerClient(BUILD_TEST_SVN_DOCKER_IMAGE)
    docker_cli.create_container()
    docker_cli.start_container()

    try:
        check_svn_running(docker_cli)
    except Exception, e:
        docker_cli.stop_container()
        docker_cli.delete_container()
        raise e

    return docker_cli


class ReplicationTestCaseWithDocker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docker_clients = defaultdict(create_p4_docker_cli)
        cls.docker_p4d_clients = cls.docker_clients
        cls.docker_svn_clients = defaultdict(create_svn_docker_cli)

    @classmethod
    def tearDownClass(cls):
        p4d_clients = cls.docker_clients
        svn_clients = cls.docker_svn_clients

        docker_clients = zip(p4d_clients.keys() + svn_clients.keys(),
                             p4d_clients.values() + svn_clients.values())
        for name, cli in docker_clients:
            logger.info('stopping/removing container %s' % str(name))
            cli.stop_container()
            cli.delete_container()


if __name__ == '__main__':
    class TestClass(ReplicationTestCaseWithDocker):
        def test_me(self):
            svn_docker = self.docker_svn_clients['svn']
            pass

    unittest.main()
