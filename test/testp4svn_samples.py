#!/usr/bin/env python

'''test replication of depots in perforce sampledepot.
'''
import os

import unittest
from replicationunittest import ReplicationTestCaseWithDocker
from testcommon import get_p4d_from_docker
from testcommon_p4svn import replicate_P4SvnReplicate, verify_replication
from lib.buildlogger import getLogger
from lib.buildcommon import generate_random_str

import tempfile
import testsampledepot
import testsampledepot_misc

logger = getLogger(__name__)

class P4SvnReplicationTest(ReplicationTestCaseWithDocker):
    def replicate_sample_dir_withdocker(self, depot_dir, **kwargs):
        '''replicate depot_dir to svn

        @param depot_dir, e.g. /depot/Jam
        '''
        src_depot = '/%s/...' % depot_dir
        svn_test_dir_name = ('buildtest' +
                             '_'.join(depot_dir.split('/')) +
                             '_' + generate_random_str())
        dst_depot = '/%s' % svn_test_dir_name

        src_docker_cli = kwargs.pop('src_docker_cli', None)
        if not src_docker_cli:
            src_docker_cli = self.docker_p4d_clients['p4d_0']

        dst_docker_cli = kwargs.pop('dst_docker_cli', None)
        if not dst_docker_cli:
            dst_docker_cli = self.docker_svn_clients['svn_0']

        src_view = ((src_depot, './...'),)
        dst_view = ((dst_depot, ''),)

        replicate_P4SvnReplicate(src_view, dst_view,
                                 src_docker_cli, dst_docker_cli, **kwargs)
        verify_replication(src_view, dst_view, src_docker_cli,
                           dst_docker_cli, **kwargs)


class P4SvnSampleDepotTest(P4SvnReplicationTest,
                           testsampledepot.SampleDepotTest,
                           testsampledepot_misc.SampleDepotTestMisc):
    # inherits all tests of P4P4 SampleDepotTest, overloaded
    # replicate_sample_dir_withdocker() so that p4svn replication
    # script is used.

    def test_replicate_sample_depot_Jam_ingroups(self):
        '''replicate the whole /repos/bigtop/trunk
        '''
        test_case = 'replicate_sample_depot_Jam_ingroup'

        depot_dir = '/depot/Jam'

        src_docker_cli = self.docker_p4d_clients['p4d_0']
        dst_docker_cli = self.docker_svn_clients['svn_0']
        with get_p4d_from_docker(src_docker_cli, depot_dir) as p4:
            src_revs = p4.run_changes('-l', '...@0,#head')
            src_revs.reverse()
            src_revs = [c['change'] for c in src_revs]
        src_revs.insert(0, 0)
        num_replicate = 1
        max_replicate = 20

        src_depot = '/%s/...' % depot_dir
        svn_test_dir_name = 'buildtest%s_group' % '_'.join(depot_dir.split('/'))
        dst_depot = '/%s' % svn_test_dir_name

        src_view = ((src_depot, './...'),)
        dst_view = ((dst_depot, ''),)

        for src_counter in src_revs[:max_replicate:num_replicate]:
            replicate_P4SvnReplicate(src_view, dst_view,
                                     src_docker_cli, dst_docker_cli,
                                     src_counter=0,
                                     replicate_change_num=num_replicate)
            verify_replication(src_view, dst_view, src_docker_cli,
                               dst_docker_cli, src_counter=src_counter,
                               replicate_change_num=num_replicate)

        verify_replication(src_view, dst_view, src_docker_cli,
                           dst_docker_cli,
                           replicate_change_num=max_replicate)

        logger.passed(test_case)

    def test_replicate_sample_depot_specialsymbols_1(self):
        '''verify that file(dir) name including special symbols '% * # @'
        could also be replicated properly
        '''
        test_case = 'replicate_sample_depot_specialsymbols'

        depot_dir = '/depot/test_special_name'
        src_docker_cli = self.docker_p4d_clients['p4d_0']

        with get_p4d_from_docker(src_docker_cli, depot_dir) as p4:
            clientspec = p4.fetch_client(p4.client)
            ws_root = clientspec._root
            # add a file with special symbols in a directory with special symbols
            special_dir_name =  'a_dir_with_%_*_#_@_in_its_name'
            test_dir = tempfile.mkdtemp(prefix=special_dir_name, dir=ws_root)
            special_file_names = ['a_file_with_%_*_#_@_in_its_name.txt',
                                  'another file with whitespaces.txt']
            for fn in special_file_names:
                special_file_path = os.path.join(test_dir, fn)
                description = 'test a file with file name %s' % fn
                with open(special_file_path, 'wt') as f:
                    f.write('My name is %s!\n' % fn)
                p4.run_add('-f', special_file_path)
                p4.run_submit('-d', description)

        self.replicate_sample_dir_withdocker(depot_dir)
        logger.passed(test_case)

    @unittest.skip('only available for p4p4 rep')
    def test_replicate_sample_depot_copy_deleted_rev(self):
        logger.warning('%s skipped' % test_case)

    @unittest.skip('only available for p4p4 rep')
    def test_replicate_sample_commit_message_reformat_review(self):
        logger.warning('%s skipped' % test_case)

    @unittest.skip('only available for p4p4 rep')
    def test_replicate_sample_integration_ignored(self):
        pass

    @unittest.skip('only available for p4p4 rep')
    def test_replicate_sample_depot_resume_from_manual_change(self):
        pass

if __name__ == '__main__':
    import unittest

    unittest.main()
