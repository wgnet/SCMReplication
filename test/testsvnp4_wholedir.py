#!/usr/bin/python3

'''test replication of depots in svn repository.
'''

import os
import unittest
import shutil
import time
import tempfile
from pprint import pprint
from testcommon import (obliterate_all_depots,
                        obliterate_depots,
                        BUILD_TEST_P4D_USER,
                        BuildTestException,)
from lib.p4server import P4Server
from lib.scmsvn import RepSvnException
from lib.scm2scm import ReplicationException
from lib.buildcommon import (generate_file_hash, )
from lib.buildlogger import getLogger
from lib.SvnPython import SvnPython
from lib.SubversionToPerforce import SvnToP4Exception
from replicationunittest import ReplicationTestCaseWithDocker
import SvnP4Replicate as SvnP4

from testcommon_svnp4 import (replicate_SvnP4Replicate,
                              verify_replication,
                              get_svn_rev_list)

logger = getLogger(__name__)


class SvnSampleRepoRepTest(ReplicationTestCaseWithDocker):
    def setUp(self):
        '''Obliterate all p4 depots due to file number limit of trial license
        '''
        dst_docker_cli = self.docker_p4d_clients['p4d_0']
        obliterate_all_depots(dst_docker_cli)

    def replicate_sample_svn_repo(self, src_repos_dir, **kwargs):
        dst_depot_dir = os.path.basename(src_repos_dir)

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_ip = src_docker_cli.get_container_ip_addr()
        dst_ip = dst_docker_cli.get_container_ip_addr()

        dst_depot = '//depot/buildtest%s/...' % dst_depot_dir
        dst_view = ((dst_depot, './...'),)

        src_mapping = ((src_repos_dir, ' '),)
        dst_mapping = dst_view

        replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                 src_docker_cli,
                                 dst_docker_cli,
                                 **kwargs)
        verify_replication(src_mapping, dst_mapping,
                           src_docker_cli, dst_docker_cli,
                           **kwargs)

        obliterate_depots(dst_docker_cli, dst_mapping)

    def test_replicate_repos_bigtop_trunk(self):
        '''replicate the whole /repos/bigtop/trunk
        '''
        test_case = 'replicate_repos_bigtop_trunk'

        src_repos_dir = '/bigtop/trunk'
        self.replicate_sample_svn_repo(src_repos_dir)

        logger.passed(test_case)

    def test_replicate_repos_bigtop_trunk_last_change(self):
        '''replicate the whole /repos/bigtop/trunk upto last_change
        '''
        test_case = 'replicate_repos_bigtop_trunk_last_change'

        src_repos_dir = '/bigtop/trunk'
        source_last_changeset = 952
        self.replicate_sample_svn_repo(
            src_repos_dir, source_last_changeset=source_last_changeset)

        logger.passed(test_case)

    @unittest.skip('exceptions cannot be caught if the script runs in docker')
    def test_replicate_repos_bigtop_trunk_last_change_negative(self):
        '''replicate the whole /repos/bigtop/trunk upto last_change
        988 not in revisions of /bigtop/trunk
        '''
        test_case = 'replicate_repos_bigtop_trunk_last_change'

        src_repos_dir = '/bigtop/trunk'
        source_last_changeset = 988
        try:
            self.replicate_sample_svn_repo(
                src_repos_dir, source_last_changeset=source_last_changeset)
        except RepSvnException as e:
            err_msg = '%d not in svn revisions' % source_last_changeset
            self.assertTrue(err_msg in str(e))
        else:
            self.fail(
                'rev 988 not in /bigtop/trunk, should fail but no exception caught')

        logger.passed(test_case)

    def test_replicate_repos_project_branch(self):
        '''replicate a branch /repos/bigtop/branches/branch-0.3.1
        '''
        test_case = 'replicate_repos_project_branch'

        src_repos_dir = '/bigtop/branches/branch-0.3.1'
        self.replicate_sample_svn_repo(src_repos_dir)

        logger.passed(test_case)

    def test_replicate_repos_project_site(self):
        '''replicate a branch /repos/bigtop/site/trunk
        '''
        test_case = 'replicate_repos_project_site_branch'

        src_repos_dir = '/bigtop/site/trunk'
        self.replicate_sample_svn_repo(src_repos_dir)

        logger.passed(test_case)

    def test_replicate_repos_project_site_subdir(self):
        '''replicate subdir of a branch
        /repos/bigtop/site/trunk/content
        '''
        test_case = 'replicate_repos_project_site_subdir'

        src_repos_dir = '/bigtop/site/trunk/content'
        self.replicate_sample_svn_repo(src_repos_dir)

        logger.passed(test_case)

    def test_replicate_repos_project_branch_subdir(self):
        '''replicate subdir of a branch
        /repos/bigtop/branches/branch-0.3.1/bigtop-deploy
        '''
        test_case = 'replicate_repos_project_branch_subdir'

        src_repos_dir = '/bigtop/branches/branch-0.3.1/bigtop-deploy'
        self.replicate_sample_svn_repo(src_repos_dir)

        logger.passed(test_case)

    def test_replicate_repos_bigtop_trunk_ingroups(self):
        '''replicate the whole /repos/bigtop/trunk
        '''
        test_case = 'replicate_repos_bigtop_trunk_ingroups'

        src_depot_dir = '/bigtop/trunk'
        dst_depot_dir = os.path.basename(src_depot_dir)

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        svn_revs = get_svn_rev_list(src_docker_cli, src_depot_dir)
        svn_revs.insert(0, 0)
        num_replicate = 2

        dst_depot = '//depot/buildtest%s/...' % dst_depot_dir
        dst_view = ((dst_depot, './...'),)

        src_mapping = ((src_depot_dir, ' '),)
        dst_mapping = dst_view

        for src_counter in svn_revs[::num_replicate]:
            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli,
                                     src_counter=0,
                                     replicate_change_num=num_replicate)

            verify_replication(src_mapping, dst_mapping,
                               src_docker_cli, dst_docker_cli,
                               src_counter=src_counter,
                               replicate_change_num=num_replicate)

        obliterate_depots(dst_docker_cli, dst_mapping)
        logger.passed(test_case)

    @unittest.skip('exceptions cannot be caught if the script runs in docker')
    def test_replicate_repos_bigtop_trunk_source_counter(self):
        '''test incorrect source counter
        '''
        test_case = 'replicate_repos_bigtop_trunk_source_counter'

        src_depot_dir = '/bigtop/site/trunk/content/xdoc'
        dst_depot_dir = os.path.basename(src_depot_dir)

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        svn_revs = get_svn_rev_list(src_docker_cli, src_depot_dir)
        svn_revs.insert(0, 0)
        num_replicate = 2

        src_ip = src_docker_cli.get_container_ip_addr()
        dst_ip = dst_docker_cli.get_container_ip_addr()

        dst_depot = '//depot/buildtest%s/...' % dst_depot_dir
        dst_view = ((dst_depot, './...'),)

        src_mapping = ((src_depot_dir, ' '),)
        dst_mapping = dst_view

        for idx, src_counter in enumerate(svn_revs[:10:num_replicate]):
            changelist_offset = 0
            if idx == 1:
                changelist_offset = -1
            elif idx == 2:
                changelist_offset = 1

            try:
                replicate_SvnP4Replicate(
                    src_mapping,
                    dst_mapping,
                    src_docker_cli,
                    dst_docker_cli,
                    src_counter=src_counter +
                    changelist_offset,
                    replicate_change_num=num_replicate)
            except ReplicationException as e:
                if ('src counter' in str(e) and
                    'last replicated rev' in str(e) and
                        changelist_offset > 0):
                    break
                raise

            verify_replication(src_mapping, dst_mapping,
                               src_docker_cli, dst_docker_cli,
                               src_counter=src_counter,
                               replicate_change_num=num_replicate)

        obliterate_depots(dst_docker_cli, dst_mapping)
        logger.passed(test_case)

    def test_replicate_repos_bigtop_trunk_ingroups_changing_repoinfo_location(
            self):
        '''replicate the whole /repos/bigtop/trunk
        '''
        test_case = 'replicate_repos_bigtop_trunk_ingroups_changing_repoinfo'

        src_depot_dir = '/bigtop/trunk'
        dst_depot_dir = os.path.basename(src_depot_dir)

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        svn_revs = get_svn_rev_list(src_docker_cli, src_depot_dir)
        svn_revs.insert(0, 0)
        num_replicate = 2

        src_ip = src_docker_cli.get_container_ip_addr()
        dst_ip = dst_docker_cli.get_container_ip_addr()

        dst_depot = '//depot/buildtest%s/...' % dst_depot_dir
        dst_view = ((dst_depot, './...'),)

        src_mapping = ((src_depot_dir, ' '),)
        dst_mapping = dst_view

        prefix_repinfo = False

        for src_counter in svn_revs[:10:num_replicate]:
            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli,
                                     src_counter=0,
                                     replicate_change_num=num_replicate,
                                     prefix_repinfo=prefix_repinfo)

            verify_replication(src_mapping, dst_mapping,
                               src_docker_cli, dst_docker_cli,
                               src_counter=src_counter,
                               replicate_change_num=num_replicate,
                               prefix_repinfo=prefix_repinfo)

            prefix_repinfo = not prefix_repinfo

        obliterate_depots(dst_docker_cli, dst_mapping)
        logger.passed(test_case)


if __name__ == '__main__':
    unittest.main()
