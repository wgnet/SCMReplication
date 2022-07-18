#!/usr/bin/python3

'''some misc test cases
'''

import os
import tempfile
import unittest

from testcommon import (BUILD_TEST_P4D_USER,
                        replicate_sample_dir,
                        get_p4d_from_docker,
                        get_changelist_in_sample_depot)
from lib.p4server import P4Server
from lib.buildlogger import getLogger
from replicationunittest import ReplicationTestCaseWithDocker

logger = getLogger(__name__)


@unittest.skip("skipping changelists should not be supported")
class SampleDepotTestIntegrateMissingChange(ReplicationTestCaseWithDocker):

    def build_test_revision(self, docker_cli, depot_dir):
        src_depot = '/%s/...' % depot_dir
        src_view = ((src_depot, './...'),)
        src_mapping = list(map(P4Server.WorkspaceMapping._make, src_view))

        p4_user = BUILD_TEST_P4D_USER
        src_ip = docker_cli.get_container_ip_addr()
        src_p4 = P4Server('%s:1666' % src_ip, p4_user)

        ws_root = tempfile.mkdtemp(prefix='buildtest')
        src_p4.create_workspace(src_mapping, ws_root=ws_root)

        # create integ_src submits
        src_from_file_path = os.path.join(ws_root, 'integ_from')
        # add 1st revision
        with open(src_from_file_path, 'wt') as f:
            f.write('1\n')
        src_p4.run_add(src_from_file_path)
        src_p4.run_submit('-d', '1')
        # add 2nd ... 10th revisions
        contents = list(map(str, list(range(2, 10))))
        for content in contents:
            src_p4.run_edit(src_from_file_path)
            with open(src_from_file_path, 'at') as f:
                f.write(content + '\n')
            src_p4.run_submit('-d', content)

        # integrate integ_dst submits
        src_to_file_path = os.path.join(ws_root, 'integ_to')
        for srev, erev in ((1, 3), (4, 6), (7, 9)):
            integ_src_rev = '%s#%d,#%d' % (src_from_file_path, srev, erev)
            src_p4.run_integrate('-f', integ_src_rev, src_to_file_path)
            if srev > 1:
                src_p4.run_resolve('-at')
            src_p4.run_submit('-d', '%s' % integ_src_rev)
        src_p4.delete_workspace()

    def test_replicate_integ_with_no_missing_change(self):
        '''replication integrations with missing revisions, i.e. missing changes
        '''
        test_case = 'replicate_integ_with_missing_change'

        src_docker_cli = self.docker_clients['no_missing_src']
        dst_docker_cli = self.docker_clients['no_missing_dst']

        # create workspace
        depot_dir = '/depot/src_changes'
        self.build_test_revision(src_docker_cli, depot_dir)

        # replicate
        replicate_sample_dir(depot_dir,
                             src_docker_cli=src_docker_cli,
                             dst_docker_cli=dst_docker_cli)

        logger.passed(test_case)

    def replicate_integ_with_first_n_changes_missing(self, n):
        src_docker_cli = self.docker_clients['first_n_src']
        dst_docker_cli = self.docker_clients['first_n_dst']

        # create workspace
        depot_dir = '/depot/src_changes_missing%d' % n
        self.build_test_revision(src_docker_cli, depot_dir)

        src_depot = '/%s/...' % depot_dir
        src_changes = get_changelist_in_sample_depot(src_docker_cli, src_depot)
        src_counter = src_changes[n]

        # replicate
        replicate_sample_dir(depot_dir,
                             src_docker_cli=src_docker_cli,
                             dst_docker_cli=dst_docker_cli,
                             src_counter=int(src_counter),
                             obliterate=False,
                             skip_verification=True)

    def test_replicate_integ_with_first_n_missing_change(self):
        '''replication integrations with missing revisions, i.e. missing changes
        '''
        test_case = 'replicate_integ_with_first_n_missing_change'
        for n in range(0, 6):
            self.replicate_integ_with_first_n_changes_missing(n)

        logger.passed(test_case)

    def replicate_integ_with_nth_change_missing(self, n):
        src_docker_cli = self.docker_clients['missing_nth_src']
        dst_docker_cli = self.docker_clients['missing_nth_dst']

        # create workspace
        depot_dir = '/depot/src_changes_missing%d' % n
        src_depot = '/%s/...' % depot_dir
        self.build_test_revision(src_docker_cli, depot_dir)

        src_changes = get_changelist_in_sample_depot(src_docker_cli, src_depot)
        src_counter = src_changes[n]

        # replicate
        if n != 0:
            replicate_sample_dir(depot_dir,
                                 src_docker_cli=src_docker_cli,
                                 dst_docker_cli=dst_docker_cli,
                                 obliterate=False,
                                 skip_verification=True,
                                 replicate_change_num=n)

        replicate_sample_dir(depot_dir,
                             src_docker_cli=src_docker_cli,
                             dst_docker_cli=dst_docker_cli,
                             src_counter=int(src_counter),
                             obliterate=False,
                             skip_verification=True)

    def test_replicate_integ_with_nth_change_missing(self):
        '''replication integrations with missing revisions, i.e. missing changes
        '''
        test_case = 'replicate_integ_with_nth_change_missing'
        for n in range(0, 6):
            self.replicate_integ_with_nth_change_missing(n)

        logger.passed(test_case)

    def replicate_sampledepot_integ_with_first_n_changes_missing(
            self, depot_dir, n):
        src_docker_cli = self.docker_clients['first_n_src']
        dst_docker_cli = self.docker_clients['first_n_dst']

        src_depot = '/%s/...' % depot_dir
        src_changes = get_changelist_in_sample_depot(src_docker_cli, src_depot)
        src_counter = src_changes[n]

        # replicate
        replicate_sample_dir(depot_dir,
                             src_docker_cli=src_docker_cli,
                             dst_docker_cli=dst_docker_cli,
                             src_counter=int(src_counter),
                             skip_verification=True)

    def test_replicate_sampledepot_integ_with_first_n_missing_change(self):
        '''replication integrations with missing revisions, i.e. missing changes
        '''
        test_case = 'replicate_integ_with_first_n_missing_change'
        depot_dir = '/depot/Jamgraph'

        # for now, we test replication starting from changelist[3],
        # need to test more in the future.
        for n in range(0, 3):
            self.replicate_sampledepot_integ_with_first_n_changes_missing(
                depot_dir, n)

        logger.passed(test_case)

    def build_test_revision_move(self, docker_cli, depot_dir):
        '''Create revision history of a file which has 9 "edit" revisions and
        one "move" revision.
        '''
        src_from_file_path = None

        with get_p4d_from_docker(docker_cli, depot_dir) as src_p4:
            # create integ_src submits
            src_from_file_path = os.path.join(src_p4.cwd, 'move_from')
            # add 1st revision
            with open(src_from_file_path, 'wt') as f:
                f.write('1\n')
            src_p4.run_add(src_from_file_path)
            src_p4.run_submit('-d', '1')
            # add 2nd ... 9th revisions
            revs = list(map(str, list(range(2, 10))))
            for rev in revs:
                src_p4.run_edit(src_from_file_path)
                with open(src_from_file_path, 'at') as f:
                    f.write(rev + '\n')
                src_p4.run_submit('-d', rev)

            # move last rev to new file
            src_to_file_path = os.path.join(src_p4.cwd, 'move_to')
            #move_src_rev = '%s' % (src_from_file_path, revs[-1])
            src_p4.run_edit(src_from_file_path)
            src_p4.run_move(src_from_file_path, src_to_file_path)
            src_p4.run_submit('-d', 'moving %s to %s' % (src_from_file_path,
                                                         src_to_file_path))

        return src_from_file_path

    def test_replicate_with_additional_target_rev(self):
        '''replication integrations with additional revision in target depot.

        This test is designed for BENG-1447
        '''
        test_case = 'replicate_with_additional_target_rev'

        src_docker_cli = self.docker_clients['move_non_last_rev_src']
        dst_docker_cli = self.docker_clients['move_non_last_rev_dst']

        # create source revision graph
        depot_dir = '/depot/src_move_graph'
        from_file_path = self.build_test_revision_move(
            src_docker_cli, depot_dir)

        # replicate all changelists but the last one
        src_depot = '/%s/...' % depot_dir
        src_changes = get_changelist_in_sample_depot(src_docker_cli, src_depot)
        num_change = len(src_changes)

        replicate_sample_dir(depot_dir,
                             src_docker_cli=src_docker_cli,
                             dst_docker_cli=dst_docker_cli,
                             obliterate=False,
                             replicate_change_num=num_change - 1)

        # add one revision in target "move from" file
        dst_depot_dir = '/depot/buildtest%s' % depot_dir
        from_file_name = os.path.basename(from_file_path)
        with get_p4d_from_docker(dst_docker_cli, dst_depot_dir) as dst_p4:
            dst_from_file_path = os.path.join(dst_p4.cwd, from_file_name)
            dst_p4.run_sync('-f')
            dst_p4.run_edit(dst_from_file_path)
            with open(dst_from_file_path, 'at') as f:
                f.write('target additional rev')
            dst_p4.run_submit('-d', 'target additional rev')

        # replicate the last changelist
        replicate_sample_dir(depot_dir,
                             src_docker_cli=src_docker_cli,
                             dst_docker_cli=dst_docker_cli,
                             src_counter=int(src_changes[-2]),
                             skip_verification=True)

        logger.passed(test_case)


if __name__ == '__main__':
    unittest.main()
