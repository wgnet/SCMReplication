#!/usr/bin/python3

''' test cases for obliterate
'''

from testcommon import replicate_sample_dir, BUILD_TEST_P4D_USER
from lib.p4server import P4Server
from lib.buildlogger import getLogger
from replicationunittest import ReplicationTestCaseWithDocker

logger = getLogger(__name__)


class SampleDepotTestObliterate(ReplicationTestCaseWithDocker):

    def obliterate_file_rev(self, docker_cli, file_rev):
        p4_user = BUILD_TEST_P4D_USER
        src_ip = docker_cli.get_container_ip_addr()
        src_p4 = P4Server('%s:1666' % src_ip, p4_user)
        src_p4.run_obliterate('-y', file_rev)

    def test_replicate_sample_depot_obliterate0(self):
        '''obliterate 1st revision of a file
        '''
        test_case = 'replicate_sample_depot_obliterate0'

        depot_dir = '/depot/Misc/Artwork'
        depot_file = '//depot/Misc/Artwork/HQ.psd#1'
        src_docker_cli = self.docker_clients['obliterate0']
        self.obliterate_file_rev(src_docker_cli, depot_file)

        replicate_sample_dir(depot_dir,
                             src_docker_cli=src_docker_cli,
                             dst_docker_cli=self.docker_clients[1],
                             do_integration_verification=False)

        logger.passed(test_case)

    def test_replicate_sample_depot_obliterate1(self):
        '''obliterate 2nd revision of a file
        '''
        test_case = 'replicate_sample_depot_obliterate1'

        depot_dir = '/depot/Misc/Artwork'
        depot_file = '//depot/Misc/Artwork/HQ.psd#2'
        src_docker_cli = self.docker_clients['obliterate1']
        self.obliterate_file_rev(src_docker_cli, depot_file)

        replicate_sample_dir(depot_dir,
                             src_docker_cli=src_docker_cli,
                             dst_docker_cli=self.docker_clients[1],
                             do_integration_verification=False)

        logger.passed(test_case)

    def test_replicate_sample_depot_obliterate2(self):
        '''obliterate a file revision which is created by "branch to"
        '''
        test_case = 'replicate_sample_depot_obliterate2'

        depot_dir = '/depot/Jamgraph'
        depot_file = '//depot/Jamgraph/REL1.0/src/jamgraph.vcproj#1'
        src_docker_cli = self.docker_clients['obliterate0']
        self.obliterate_file_rev(src_docker_cli, depot_file)

        replicate_sample_dir(depot_dir,
                             src_docker_cli=src_docker_cli,
                             dst_docker_cli=self.docker_clients[1],
                             do_integration_verification=False)

        logger.passed(test_case)

    def test_replicate_sample_depot_obliterate3(self):
        '''obliterate a file revision which is used as "branch from" in future
        change
        '''
        test_case = 'replicate_sample_depot_obliterate3'

        depot_dir = '/depot/Jamgraph'
        depot_file = '//depot/Jamgraph/MAIN/src/jamgraph.vcproj#3'
        src_docker_cli = self.docker_clients['obliterate1']
        self.obliterate_file_rev(src_docker_cli, depot_file)

        replicate_sample_dir(depot_dir,
                             src_docker_cli=src_docker_cli,
                             dst_docker_cli=self.docker_clients[1],
                             do_integration_verification=False)

        logger.passed(test_case)


if __name__ == '__main__':
    import unittest
    unittest.main()
