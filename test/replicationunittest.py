#!/usr/bin/python3

'''Build replication test case base class, creates and deletes dockers
in setup and teardown methods.
'''

from collections import defaultdict
from datetime import datetime
import time
import unittest
import os
import locale
import docker


from lib.buildlogger import getLogger, set_logging_color_format
from lib.p4server import P4Server
from lib.SvnPython import SvnPython
from lib.dockerclient import DockerClient

set_logging_color_format()
logger = getLogger(__name__)
logger.setLevel('INFO')


BUILD_TEST_P4D_DOCKER_IMAGE = 'buildtest_p4d_sampledepot'
BUILD_TEST_SVN_DOCKER_IMAGE = 'buildtest_svn_sampledepot'
BUILD_TEST_P4D_USER = ''
BUILD_TEST_SVN_USER = ''


filepath = os.path.abspath(__file__)
dirname = os.path.dirname
scriptRootDir = dirname(dirname(filepath))


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
    logger.info("p4 server ip is %s", p4d_ip)
    src_p4 = P4Server('%s:1666' % p4d_ip, p4_user, login=False)

    start_time = datetime.now()
    time.sleep(5)
    while (datetime.now() - start_time).seconds < timeout:
        try:
            src_p4.connect()
            logger.info('p4d is now up and running')
            return
        except P4Exception:
            time.sleep(.1)
            for e in p4.errors:            # Display errors
                logger.info("P4 errors: %s", e)
            logger.info('p4d not yet ready.')

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
    except Exception as e:

        docker_cli.stop_container()
        docker_cli.delete_container()
        raise e

    return docker_cli


def check_svn_running(svn_docker, timeout=10):
    '''check if svn is up and running in docker.

    probably need something similar with check_p4d_running()
    '''
    svn_user = BUILD_TEST_SVN_USER
    svn_passwd = ''
    svn_ip = svn_docker.get_container_ip_addr()
    svn_url = f"svn://{svn_ip}:3690/repos"
    svn = SvnPython(svn_url, svn_user, svn_passwd)
    start_time = datetime.now()
    while (datetime.now() - start_time).seconds < timeout:
        svn_dir = '/'
        try:
            svn_list = svn.run_list(svn_url)
            logger.debug(svn_list)
            svn.client = None
            return
        except Exception as e:
            time.sleep(1)
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
    except Exception as e:
        docker_cli.stop_container()
        docker_cli.delete_container()
        raise e

    return docker_cli


def compose_command(script, args):
    # compose command
    cmd = ['python3', os.path.join(scriptRootDir, script), ]

    # source
    cmd.extend(['--source-port', args.source_port, ])
    cmd.extend(['--source-user', args.source_user, ])
    cmd.extend(['--source-passwd', '"%s"' % args.source_passwd, ])
    cmd.extend(['--source-workspace-view-cfgfile',
                '"%s"' % args.source_workspace_view_cfgfile, ])
    cmd.extend(['--source-counter', str(args.source_counter), ])

    # target
    cmd.extend(['--target-port', args.target_port, ])
    cmd.extend(['--target-user', args.target_user, ])
    cmd.extend(['--target-passwd', '"%s"' % args.target_passwd, ])
    cmd.extend(['--target-workspace-view-cfgfile',
                '"%s"' % args.target_workspace_view_cfgfile, ])

    # options
    cmd.extend(['-r', '"%s"' % args.workspace_root, ])

    if hasattr(args, 'svn_ignore_externals') and args.svn_ignore_externals:
        cmd.extend(['--svn-ignore-externals', ])
    if hasattr(args, 'source_p4_stream'):
        cmd.extend(['--source-p4-stream', args.source_p4_stream, ])
    if (hasattr(args, 'prefix_description_with_replication_info') and
            args.prefix_description_with_replication_info):
        cmd.extend(['--prefix-description-with-replication-info', ])

    if args.source_last_changeset:
        cmd.extend(['--source-last-changeset',
                    str(args.source_last_changeset), ])
    if args.maximum:
        cmd.extend(['--maximum', str(args.maximum), ])
    cmd.extend(['--replicate-user-and-timestamp', ])
    cmd.extend(['--verbose', args.verbose, ])

    cmd = ' '.join(cmd)
    print(cmd)

    return cmd


def run_replication_in_container(script, args):

    rep_docker_image = 'c7_source_replication'
    base_url = 'unix:///var/run/docker.sock'
    #docker_cli = docker.from_env(base_url=base_url, version='auto')
    docker_cli = docker.from_env()

    cmd = compose_command(script, args)
    language, locale_encoding = locale.getlocale()
    if locale_encoding is None:
        language, locale_encoding = locale.getdefaultlocale()
    environment = {'LANG': "{}.{}".format(language, locale_encoding), }

    test_rep_root = os.path.join(scriptRootDir, './test/replication')
    volumes = {'replication-test-vol': {'bind': test_rep_root, 'mode': 'rw', }, }

    # should be the same user who built the replication docker image
    user = os.environ.get('USER')

    #cmd = "ls / %s" % scriptRootDir
    container = docker_cli.containers.run(image=rep_docker_image,
                                          command=cmd,
                                          environment=environment,
                                          volumes=volumes,
                                          working_dir=scriptRootDir,
                                          user=user,
                                          detach=True,)

    container.start()
    container.wait()

    logger.info(container.logs())
    container.remove()


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

        docker_clients = list(zip(list(p4d_clients.keys()) +
                                  list(svn_clients.keys()), list(p4d_clients.values()) +
                                  list(svn_clients.values())))
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
