#!/usr/bin/python3

'''tests for release branch generation script
'''

import json
import os
import unittest
import lib.P4ReleaseBranchGenerate as p4rbg

from P4 import Map
from lib.buildcommon import generate_random_str
from lib.buildlogger import getLogger
from .replicationunittest import ReplicationTestCaseWithDocker
from .testcommon_releasebranchgeneration import verify_replication
from .testcommon import (BUILD_TEST_P4D_USER,
                         get_changelist_in_sample_depot,
                         get_p4d_from_docker,
                         obliterate_all_depots,
                         BuildTestException,)

logger = getLogger(__name__)


def create_branch_view(p4, branch_mapping):
    '''create a branch view from source_depot_dir to target_depot_dir

    @param p4, P4Server instance
    @param source_depot_dir, string e.g. //depot/source/branch/...
    @param target_depot_dir, string e.g. //depot/target/branch/...
    @return string, name of branch view
    '''
    branch_name = 'RBG_branch_view_' + generate_random_str()
    branch_spec = {'Branch': branch_name,
                   'Description': 'branch for release branch generation',
                   'Owner': p4.user,
                   'Options': 'unlocked',
                   'View': branch_mapping}

    branch_spec = '\n'.join('%s: %s' % (k, v)
                            for k, v in list(branch_spec.items()))

    p4.input = branch_spec
    p4.run_branch('-i')

    return branch_name


class RBGSampleDepotTest(ReplicationTestCaseWithDocker):
    def copy_sample_dir_withdocker(self, testcase, src_dir,
                                   src_counter=0,
                                   use_separate_container=False,
                                   **kwargs):
        if use_separate_container:
            src_docker = self.docker_clients[testcase]
        else:
            src_docker = self.docker_clients[0]

        p4_user = BUILD_TEST_P4D_USER
        ip = src_docker.get_container_ip_addr()
        p4_port = '%s:1666' % ip
        p4_passwd = ''

        dst_dir = '//depot/RBG_%s/...' % testcase
        p4rbg.release_branch_generate(p4_port, p4_user, p4_passwd,
                                      src_dir, dst_dir, **kwargs)

        verify_replication(src_dir, dst_dir, src_docker, src_counter, **kwargs)

    def test_copy_single_branch(self):
        ''' copy from //depot/Jam/MAIN/...
        '''
        test_case = 'copy_single_branch'

        src_dir = '//depot/Jam/MAIN/...'
        self.copy_sample_dir_withdocker(test_case, src_dir)

        logger.passed(test_case)

    def test_copy_username_timestamp_positive(self):
        ''' copy from //depot/Jam/MAIN/...
        '''
        test_case = 'copy_username_timestamp_positive'

        src_dir = '//depot/Jam/MAIN/...'
        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        maximum=3,
                                        replicate_user_and_timestamp=True)

        logger.passed(test_case)

    def test_copy_username_timestamp_negative(self):
        ''' copy from //depot/Jam/MAIN/...
        '''
        test_case = 'copy_username_timestamp_negative'

        src_dir = '//depot/Jam/MAIN/...'
        try:
            src_docker = self.docker_clients[0]

            p4_user = BUILD_TEST_P4D_USER
            ip = src_docker.get_container_ip_addr()
            p4_port = '%s:1666' % ip
            p4_passwd = ''
            dst_dir = '//depot/RBG_%s/...' % test_case
            p4rbg.release_branch_generate(p4_port, p4_user, p4_passwd,
                                          src_dir, dst_dir,
                                          replicate_user_and_timestamp=False,
                                          maximum=3)

            verify_replication(src_dir, dst_dir, src_docker, src_counter=0,
                               replicate_user_and_timestamp=True, maximum=3)
        except BuildTestException as e:
            self.assertTrue('src user != dst user' in str(e) or
                            'src time != dst time' in str(e))
        else:
            self.fail('verification should fail')

        logger.passed(test_case)

    def test_copy_username_timestamp_flippling(self):
        ''' copy from //depot/Jam/MAIN/...
        test copy in groups
        '''
        test_case = 'copy_username_timestamp_flippling'

        src_dir = '//depot/Jamgraph/...'

        src_changelists = get_changelist_in_sample_depot(
            self.docker_clients[0], src_dir)
        src_changelists.insert(0, 0)
        src_docker = self.docker_clients[0]

        p4_user = BUILD_TEST_P4D_USER
        ip = src_docker.get_container_ip_addr()
        p4_port = '%s:1666' % ip
        p4_passwd = ''
        dst_dir = '//depot/RBG_%s/...' % test_case

        num_changes_to_rep_per_round = 5
        replicate_user_and_timestamp = False
        repopulate_change_properties = False
        for i in range(4):
            if i == 2:
                replicate_user_and_timestamp = True
                repopulate_change_properties = True

            logger.info(
                '*' * 80 + 'round %d, user_and_timestamp: %s' %
                (i, replicate_user_and_timestamp))

            p4rbg.release_branch_generate(
                p4_port,
                p4_user,
                p4_passwd,
                src_dir,
                dst_dir,
                replicate_user_and_timestamp=replicate_user_and_timestamp,
                repopulate_change_properties=repopulate_change_properties,
                maximum=num_changes_to_rep_per_round)

            try:
                verify_replication(src_dir, dst_dir, src_docker,
                                   src_counter=src_changelists[i * num_changes_to_rep_per_round],
                                   replicate_user_and_timestamp=True,
                                   maximum=num_changes_to_rep_per_round)
            except BuildTestException as e:
                if not replicate_user_and_timestamp:
                    self.assertTrue('src user != dst user' in str(e) or
                                    'src time != dst time' in str(e))
                else:
                    raise

            # only need to do it once
            repopulate_change_properties = False

        verify_replication(src_dir, dst_dir, src_docker,
                           src_counter=0,
                           replicate_user_and_timestamp=True,
                           maximum=num_changes_to_rep_per_round * 4)

        logger.passed(test_case)

    def test_copy_to_target_populated_from_main(self):
        ''' copy from //depot/Jam/MAIN/...
        target branch is already populated
        '''
        test_case = 'copy_to_target_populated_from_main'

        src_dir = '//depot/Jam/MAIN/...'

        dst_dir = '//depot/RBG_%s/...' % test_case
        docker_cli = self.docker_clients[0]
        with get_p4d_from_docker(docker_cli, '/depot') as p4:
            changes = p4.run_changes(src_dir)
            src_revs = [c['change'] for c in changes]
            populate_rev = src_revs[len(src_revs) / 2]
            p4.run_populate('%s@%s' % (src_dir, populate_rev), dst_dir)

        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        src_counter=populate_rev)

        logger.passed(test_case)

    def test_copy_to_target_populated_from_main_at107_and_switch_to_rel(self):
        ''' copy from //depot/Jam/MAIN/...
        target branch is populated with a revision before branch point of rel
        '''
        test_case = 'copy_to_target_populated_from_main_at107_and_switch_to_rel'

        src_dir = '//depot/Jam/MAIN/...'
        dst_dir = '//depot/RBG_%s/...' % test_case
        docker_cli = self.docker_clients[0]
        populate_rev = 107
        with get_p4d_from_docker(docker_cli, '/depot') as p4:
            p4.run_populate('%s@%s' % (src_dir, populate_rev), dst_dir)

        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        src_counter=populate_rev)

        src_dir = '//depot/Jam/REL2.1/...'
        self.copy_sample_dir_withdocker(test_case, src_dir)

        logger.passed(test_case)

    def test_copy_to_target_populated_from_main_at206_and_switch_to_rel(self):
        ''' copy from //depot/Jam/MAIN/...
        target branch is populated with a revision after branch point of rel
        '''
        test_case = 'copy_to_target_populated_from_main_at206_and_switch_to_rel'

        src_dir = '//depot/Jam/MAIN/...'
        dst_dir = '//depot/RBG_%s/...' % test_case
        docker_cli = self.docker_clients[0]
        populate_rev = 206
        with get_p4d_from_docker(docker_cli, '/depot') as p4:
            p4.run_populate('%s@%s' % (src_dir, populate_rev), dst_dir)

        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        src_counter=populate_rev)

        src_dir = '//depot/Jam/REL2.1/...'
        self.copy_sample_dir_withdocker(test_case, src_dir)

        logger.passed(test_case)

    def test_copy_single_branch_max(self):
        ''' copy from //depot/Jam/MAIN/...
        test argument maximum
        '''
        test_case = 'copy_single_branch_max'

        src_dir = '//depot/Jam/MAIN/...'
        self.copy_sample_dir_withdocker(test_case, src_dir, maximum=3)

        logger.passed(test_case)

    def test_copy_single_branch_ingroup(self):
        ''' copy from //depot/Jam/MAIN/...
        test copy in groups
        '''
        test_case = 'copy_single_branch_ingroup'

        src_dir = '//depot/Jam/MAIN/...'

        src_changelists = get_changelist_in_sample_depot(
            self.docker_clients[0], src_dir)
        src_changelists.insert(0, 0)
        for i in range(10):
            self.copy_sample_dir_withdocker(test_case, src_dir,
                                            src_counter=src_changelists[i * 3],
                                            maximum=3)

        logger.passed(test_case)

    def test_copy_single_branch_last(self):
        ''' copy from //depot/Jam/MAIN/...
        test argument source_last_revision
        '''
        test_case = 'copy_single_branch_last'

        src_dir = '//depot/Jam/MAIN/...'
        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        source_last_revision=208)

        logger.passed(test_case)

    def test_copy_release_branch(self):
        ''' copy from //depot/Jam/REL2.1/...
        test argument source_last_revision
        '''
        test_case = 'copy_release_branch'

        src_dir = '//depot/Jam/REL2.1/...'
        self.copy_sample_dir_withdocker(test_case, src_dir)

        logger.passed(test_case)

    def test_copy_switching_branch_gwt_17_20(self):
        '''trunk->rel1.7->rel2.0
        '''
        test_case = 'copy_switching_branch_gwt_17_20'

        src_dir = '//gwt/trunk/...'
        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        use_separate_container=True)

        src_dir = '//gwt/releases/1.7/...'
        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        use_separate_container=True)

        src_dir = '//gwt/releases/2.0/...'
        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        use_separate_container=True)

        expected_src_revs = [
            # copy to top of rel2.0
            '7489', '6897', '6896', '6751', '6750', '6593',
            '6155', '5886', '5395', '5135', '4964', '4618',

            # reversion from rel1.7 to start of rel2.0
            '12128', '12185', '12186', '12187', '12188', '12189',

            # copy to top of rel1.7
            '5250', '5092', '5089', '4909', '4568', '4196',

            # reversion from top of trunk to start of rel1.7
            '12128', '12129', '12130', '12131', '12132', '12133',
            '12134', '12135', '12136', '12137', '12138', '12139',
            '12140', '12141', '12142', '12143', '12144', '12145',
            '12146', '12147', '12148', '12149', '12150', '12151',
            '12152', '12153', '12154', '12155',

            # copy to top of trunk
            '10044', '9973', '9965', '9927', '9904', '9824',
            '9769', '9748', '9744', '9638', '9637', '9626',
            '9622', '9475', '9471', '9454', '9240', '9169',
            '9166', '9076', '7485', '6155', '5886', '5395',
            '5135', '4964', '4618', '4420', '4021', '3814',
            '2541', '2444', '2440', '2413', '2346', '1859',
            '1827', '1784', '1770', '1608', '1470', '1414',
            '1251', '973', '669', '656', '540', '538', '503',
            '448', '430']

        self.compare_copied_revision_with_expected(test_case,
                                                   expected_src_revs)

        logger.passed(test_case)

    def test_copy_switching_branch_gwt_20_17(self):
        '''trunk->rel2.0->rel1.7
        '''
        test_case = 'copy_switching_branch_gwt_20_17'

        src_dir = '//gwt/trunk/...'
        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        use_separate_container=True)

        src_dir = '//gwt/releases/2.0/...'
        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        use_separate_container=True)

        src_dir = '//gwt/releases/1.7/...'
        self.copy_sample_dir_withdocker(test_case, src_dir,
                                        use_separate_container=True)

        expected_src_revs = [
            # to top of 1.7
            '5250', '5092', '5089', '4909', '4568', '4196',

            # reverse back to start of rel1.7
            '12128', '12130', '12131', '12132', '12133', '12134',
            '12135', '12178', '12179', '12180', '12181', '12182',

            # to top of 2.0
            '7489', '6897', '6896', '6751', '6750', '6593',

            # reverse back top start of rel2.0
            '12135', '12136', '12137', '12138', '12139', '12140',
            '12141', '12142', '12143', '12144', '12145', '12146',
            '12147', '12148', '12149', '12150', '12151', '12152',
            '12153', '12154', '12155',

            # to top of trunk
            '10044', '9973', '9965', '9927', '9904', '9824',
            '9769', '9748', '9744', '9638', '9637', '9626',
            '9622', '9475', '9471', '9454', '9240', '9169',
            '9166', '9076', '7485', '6155', '5886', '5395',
            '5135', '4964', '4618', '4420', '4021', '3814',
            '2541', '2444', '2440', '2413', '2346', '1859',
            '1827', '1784', '1770', '1608', '1470', '1414',
            '1251', '973', '669', '656', '540', '538', '503',
            '448', '430']

        self.compare_copied_revision_with_expected(test_case,
                                                   expected_src_revs)

        logger.passed(test_case)

    def create_test_branch_tree(self, test_case, depot_dir):
        '''create test branch tree in src_depot

        @param depot_dir /depot/src_branch_tree
        '''
        docker_cli = self.docker_clients[test_case]
        obliterate_all_depots(docker_cli)

        dir_names = ['1', '2', '3', '4']
        file_names = ['a_file', 'b_file', 'c_file', ]

        with get_p4d_from_docker(docker_cli, depot_dir) as p4:
            clientspec = p4.fetch_client(p4.client)
            ws_root = clientspec._root
            clientmap = Map(clientspec._view)
            ctr = Map('//%s/...  %s/...' % (clientspec._client,
                                            clientspec._root))
            localmap = Map.join(clientmap, ctr)
            depotmap = localmap.reverse()

            # create directories/files
            trunk_files = []
            trunk_fs_dir = os.path.join(ws_root, 'trunk')
            trunk_depot_dir = os.path.join(depot_dir, 'trunk')

            branches_fs_dir = os.path.join(ws_root, 'branches')
            branches_depot_dir = os.path.join(depot_dir, 'branches')
            os.mkdir(trunk_fs_dir)
            os.mkdir(branches_fs_dir)
            # add files one by one
            for d in dir_names:
                test_dir = os.path.join(trunk_fs_dir, d)
                os.mkdir(test_dir)
                for f in file_names:
                    test_file = os.path.join(test_dir, f)
                    with open(test_file, 'wt') as fo:
                        fo.write('My name is %s!\n' % test_file)
                    p4.run_add('-f', test_file)
                    trunk_files.append(test_file)
                    description = 'adding %s\n' % test_file
                    p4.run_submit('-d', description)

            # edit all files one by one
            for fn in trunk_files:
                p4.run_edit(fn)
                desc = '%s edited\n' % fn
                with open(fn, 'at') as f:
                    f.write(desc)
                p4.run_submit('-d', desc)

            # create branches for different file set
            branch_file_mapping = (('b1', (0, 4, 8)),
                                   ('b2', (1, 5, 9)),
                                   ('b3', (2, 6, 10)),
                                   ('b4', (0, 1, 2)),)
            branch_files = []
            branch_depots = [trunk_depot_dir, ]
            for branch_name, bfi in branch_file_mapping:
                branch_depot_dir = os.path.join(
                    branches_depot_dir, branch_name)
                branch_depots.append(branch_depot_dir)
                branch_fs_dir = os.path.join(branches_fs_dir, branch_name)
                os.mkdir(branch_fs_dir)
                file_mapping = ''
                for f_idx in bfi:
                    branch_src_fname = depotmap.translate(trunk_files[f_idx])
                    branch_src_rel_path = branch_src_fname[len(
                        trunk_depot_dir + '/') + 1:]
                    branch_dst_fname = '%s/%s' % (branch_depot_dir,
                                                  branch_src_rel_path)
                    file_mapping += '\t%s /%s\n' % (
                        branch_src_fname, branch_dst_fname)
                    branch_files.append(
                        os.path.join(
                            branch_fs_dir,
                            branch_src_rel_path))

                branch_view = create_branch_view(p4, file_mapping)
                p4.run_integrate('-b', branch_view)
                p4.run_submit('-d', 'creating branch %s' % branch_name)

            # edit trunk files
            for fn in trunk_files:
                p4.run_edit(fn)
                desc = '%s edited\n' % fn
                with open(fn, 'at') as f:
                    f.write(desc)
                p4.run_submit('-d', desc)

            # edit branch files
            for fn in branch_files:
                p4.run_edit(fn)
                desc = '%s edited\n' % fn
                with open(fn, 'at') as f:
                    f.write(desc)
                p4.run_submit('-d', desc)

            # delete half of branch files
            for fn in branch_files[:len(branch_files) / 2]:
                p4.run_delete(fn)
                desc = '%s deleted\n' % fn
                p4.run_submit('-d', desc)

        return branch_depots

    def compare_copied_revision_with_expected(self, test_case,
                                              expected_src_revs):
        dst_dir = '/depot/RBG_%s' % test_case
        with get_p4d_from_docker(self.docker_clients[test_case], dst_dir) as p4:
            changes = p4.run_changes('...')
            dst_revs = [c['change'] for c in changes]
            keys = p4.run_keys('-e', '*%s*' % test_case)
            keys.reverse()
            keys = [json.loads(k['value']) for k in keys]
            copy_src_revs = [k['src_revision'] for k in keys]
            copy_dst_revs = [k['dst_revision'] for k in keys]

            for dr, cdr in zip(dst_revs, copy_dst_revs):
                self.assertEqual(dr, cdr)

            for esr, csr in zip(expected_src_revs, copy_src_revs):
                self.assertEqual(esr, csr)

    def test_copy_created_branch_tree_trunk_b4_b1_b2_b3(self):
        test_case = 'copy_created_branch_tree_trunk_b4_b1_b2_b3'

        src_dir = '/depot/src_branch_tree'
        branch_depots = self.create_test_branch_tree(test_case, src_dir)

        trunk = '/%s/...' % branch_depots[0]
        self.copy_sample_dir_withdocker(test_case, trunk,
                                        use_separate_container=True)

        branch = '/%s/...' % branch_depots[4]
        self.copy_sample_dir_withdocker(test_case, branch,
                                        use_separate_container=True)

        branch = '/%s/...' % branch_depots[1]
        self.copy_sample_dir_withdocker(test_case, branch,
                                        use_separate_container=True)

        branch = '/%s/...' % branch_depots[2]
        self.copy_sample_dir_withdocker(test_case, branch,
                                        use_separate_container=True)

        branch = '/%s/...' % branch_depots[3]
        self.copy_sample_dir_withdocker(test_case, branch,
                                        use_separate_container=True)

        expected_src_revs = ['12154', '12153', '12152', '12132',
                             '12128', '12124', '12120', '12116', '12112', '12108',
                             '12165', '12169', '12173', '12177', '12181', '12185',
                             '12258', '12259', '12260', '12261', '12262', '12263',
                             '12163', '12162', '12161', '12151', '12150', '12149',
                             '12131', '12127', '12123', '12119', '12115', '12111',
                             '12107', '12164', '12168', '12172', '12176', '12180',
                             '12184', '12233', '12234', '12235', '12236', '12237',
                             '12238', '12160', '12159', '12158', '12148', '12147',
                             '12146', '12130', '12126', '12122', '12176', '12177',
                             '12178', '12221', '12222', '12223', '12157', '12156',
                             '12155', '12133', '12178', '12179', '12180', '12181',
                             '12182', '12183', '12184', '12185', '12186', '12187',
                             '12188', '12189', '12190', '12191', '12192', '12193',
                             '12194', '12195', '12196', '12197', '12198', '12145',
                             '12144', '12143', '12142', '12141', '12140', '12139',
                             '12138', '12137', '12136', '12135', '12134', '12129',
                             '12128', '12127', '12126', '12125', '12124', '12123',
                             '12122', '12121', '12120', '12119', '12118', '12117',
                             '12116', '12115', '12114', '12113', '12112', '12111',
                             '12110', '12109', '12108', '12107', '12106']

        self.compare_copied_revision_with_expected(test_case,
                                                   expected_src_revs)

        logger.passed(test_case)

    def test_copy_commit_message_reformat_review(self):
        '''verify that "#review" in commit message is changed to "# review"
        '''
        test_case = 'copy_commit_message_reformat_review'

        src_dir = '/depot/Talkhouse/main-dev'
        #src_dir = '/depot/Jam/MAIN'
        src_docker_cli = self.docker_clients[0]
        orig_desc = 'add new file, and testing review in comments\n'
        orig_desc += '#review-22\n'
        orig_desc += '##review-22review\n'
        expected_desc = 'add new file, and testing review in comments\n'
        expected_desc += '# review-22\n'
        expected_desc += '## review-22review\n'

        with get_p4d_from_docker(src_docker_cli, src_dir) as p4:
            clientspec = p4.fetch_client(p4.client)
            ws_root = clientspec._root
            test_file = os.path.join(ws_root, 'testfile')
            with open(test_file, 'wt') as fo:
                fo.write('My name is %s!\n' % test_file)
            p4.run_add('-f', test_file)
            output_lines = p4.run_submit('-d', orig_desc)

            for line in output_lines:
                if 'submittedChange' in line:
                    src_rev = line['submittedChange']

        depot_dir = '/%s/...' % src_dir
        self.copy_sample_dir_withdocker(test_case, depot_dir)

        expected_desc += '\nCopied from revision @%s by %s' % (
            src_rev, BUILD_TEST_P4D_USER)

        dst_dir = '/depot/RBG_%s' % test_case
        with get_p4d_from_docker(src_docker_cli, dst_dir) as p4:
            changes = p4.run_changes('-l', '...')
            last_change = changes[0]
            desc = last_change['desc']
            logger.debug(desc)
            self.assertEqual(desc, expected_desc)
        logger.passed(test_case)


if __name__ == '__main__':
    unittest.main()
