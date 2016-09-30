#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''test replication of svn depot from to p4 with exclusion

test repo directory structure

$ cd trunk; tree -L 3
|-- a.txt
|-- aveihc
|   |-- dwhxui
|   `-- dwhxui_exec
|-- bxhqin
|   `-- byhjzd
|-- paqblz
|   |-- bsykhn
|   `-- bsykhn_exec
|-- test_dir
|   `-- repo_test_file_new_exec
|-- test_dir_parent
|   |-- a.exe
|   |-- a.json
|   |-- a.txt
|   |-- b.exe
|   |-- b.json
|   |-- b.txt
|   |-- c.exe
|   |   |-- a.json
|   |   |-- a.txt
|   |   `-- b.txt
|   |-- deploy
|   |   |-- live-cd
|   |   |-- puppet
|   |   `-- vm
|   |-- hadoop_src
|   |   |-- resources
|   |   |-- site.xml
|   |   `-- xdoc
|   |-- some_dir
|   |   |-- a.json
|   |   |-- a.txt
|   |   |-- b.txt
|   |   `-- c.exe
|   `-- tests
|       |-- test-artifacts
|       `-- test-execution
`-- test_dir_parent_1
    |-- a.exe
    |-- a.json
    |-- a.txt
    |-- b.exe
    |-- b.json
    |-- b.txt
    |-- c.exe
    |   |-- a.json
    |   |-- a.txt
    |   `-- b.txt
    |-- deploy
    |   |-- live-cd
    |   |-- puppet
    |   `-- vm
    |-- hadoop_src
    |   |-- resources
    |   |-- site.xml
    |   `-- xdoc
    |-- some_dir
    |   |-- a.json
    |   |-- a.txt
    |   |-- b.txt
    |   `-- c.exe
    `-- tests
        |-- test-artifacts
        `-- test-execution

'''

import os
import unittest
import tempfile

from testcommon import (obliterate_all_depots,
                        BuildTestException,
                        get_p4d_from_docker,)
from lib.buildcommon import (generate_random_str, )
from replicationunittest import ReplicationTestCaseWithDocker

from testcommon_svnp4 import (replicate_SvnP4Replicate,
                              verify_replication,
                              get_svn_rev_list,
                              get_svn_from_docker,
                              svn_test_action_actions,)

from lib.buildlogger import getLogger
logger = getLogger(__name__)


class SvnExclusionRepTest(ReplicationTestCaseWithDocker):
    def setUp(self):
        '''Obliterate all p4 depots due to file number limit of trial license
        '''
        dst_docker_cli=self.docker_p4d_clients['p4d_0']
        obliterate_all_depots(dst_docker_cli)

    def svn_exclusion_construct_source_repos(self, src_depot_dir):
        logger.info('testing %s' % src_depot_dir)

        # create svn repo tree
        actions=['edit', 'rename', 'delete_file', 'add_exec',
                 'add_dir', 'edit', 'add_exec',
                 'add_dir', 'edit', 'add_exec',
                 'add_dir', 'edit',]

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        init_external_cfg = [
            '^/bigtop/branches/hadoop-0.23/bigtop-deploy deploy',
            '^/bigtop/branches/hadoop-0.23/bigtop-tests tests',
            '^/bigtop/branches/hadoop-0.23/src/site hadoop_src',]

        mod_external_cfgs = [
            [# remove tests
             '^/bigtop/branches/hadoop-0.23/bigtop-deploy deploy',
             '^/bigtop/branches/hadoop-0.23/src/site hadoop_src',
            ],

            [# add tests back
             '^/bigtop/branches/hadoop-0.23/bigtop-deploy deploy',
             '^/bigtop/branches/hadoop-0.23/bigtop-tests tests',
             '^/bigtop/branches/hadoop-0.23/src/site hadoop_src',
            ],

            [# relocate hadoop_src
             '^/bigtop/branches/hadoop-0.23/src/site hadoop/hadoop_src',
            ],

            [# relocate hadoop_src
             '^/bigtop/branches/hadoop-0.23/src/site hadoop_src',
             '^/bigtop/branches/hadoop-0.23/bigtop-tests tests',
            ],
        ]

        svn_test_action_actions(src_docker_cli, src_depot_dir,
                                actions=actions)
        with get_svn_from_docker(src_docker_cli) as (svn, svn_root):
            # add project directory
            project_abs_dir = os.path.join(svn_root, src_depot_dir[1:])
            svn.run_update(project_abs_dir, update_arg='--depth infinity')
            trunk_dir = os.path.join(project_abs_dir, 'trunk')

            for idx, dir_name in enumerate(['test_dir_parent', 'test_dir_parent_1', ]):
                trunk_parent = os.path.join(trunk_dir, dir_name)
                os.mkdir(trunk_parent)

                if idx == 0:
                    exclude_path = trunk_parent[len(svn_root):]

                ''' add
                test_dir_parent/c.exe
                test_dir_parent/c.exe/{a.json, a.txt, b.txt}
                '''
                exec_subdir = os.path.join(trunk_parent, 'c.exe')
                os.mkdir(exec_subdir)
                for fn in ['a.json', 'a.txt', 'b.txt']:
                    file_path = os.path.join(exec_subdir, fn)
                    with open(file_path, 'wt') as f:
                        f.write('my name is %s' % fn)

                normal_subdir = os.path.join(trunk_parent, 'some_dir')
                os.mkdir(normal_subdir)
                for fn in ['a.json', 'a.txt', 'b.txt', 'c.exe']:
                    file_path = os.path.join(normal_subdir, fn)
                    with open(file_path, 'wt') as f:
                        f.write('my name is %s' % fn)

                '''add
                test_dir_parent/{a.exe, b.exe, a.json, b.json, a.txt, b.txt}
                '''
                for fn in ['a.exe', 'b.exe', 'a.json', 'b.json', 'a.txt', 'b.txt']:
                    file_path = os.path.join(trunk_parent, fn)
                    with open(file_path, 'wt') as f:
                        f.write('my name is %s' % fn)
                svn.run_add(trunk_parent)
                # add svn:externals
                # test_dir_parent/bigtop-deploy
                if idx == 0:
                    svn.propset('svn:externals', '\n'.join(init_external_cfg),
                                trunk_parent)
                svn.run_checkin(trunk_parent, 'adding %s' % trunk_parent)

                # edit test_dir_parent/a.exe
                testfile = os.path.join(trunk_parent, 'a.exe')
                action = 'editing %s\n' % testfile
                with open(testfile, 'a') as f:
                    f.write(action)
                svn.run_checkin(testfile, '%s' % action)

                # add svn:externals
                # test_dir_parent/bigtop-deploy
                if idx == 1:
                    svn.run_update(trunk_parent, update_arg='--depth infinity')
                    svn.propset('svn:externals', '\n'.join(init_external_cfg),
                                trunk_parent)
                    svn.run_checkin(trunk_parent, 'adding externals')

                # edit test_dir_parent/b.json
                testfile = os.path.join(trunk_parent, 'b.json')
                action = 'editing %s\n' % testfile
                with open(testfile, 'a') as f:
                    f.write(action)
                svn.run_checkin(testfile, '%s' % action)

                for ext_cfg in mod_external_cfgs:
                    svn.run_update(trunk_parent, update_arg='--depth infinity')
                    svn.propset('svn:externals', '\n'.join(ext_cfg),
                                trunk_parent)
                    svn.run_checkin(trunk_parent,
                                    'changing externals: %s' % str(ext_cfg))

                    testfile = os.path.join(trunk_parent, 'b.json')
                    action = 'editing %s\n' % testfile
                    with open(testfile, 'a') as f:
                        f.write(action)
                    svn.run_checkin(testfile, '%s' % action)


            testfile = os.path.join(trunk_dir, 'a.txt')
            action = 'editing %s\n' % testfile
            with open(testfile, 'a') as f:
                f.write(action)
            svn.run_add(testfile)
            svn.run_checkin(testfile, '%s' % action)

        return exclude_path

    def test_svn_action_rep_view_mapping_exclude_dir(self):
        '''Exclude a whole test_dir_parent
        '''
        test_case = 'svn_action_rep_view_mapping_exclude_dir'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/%s' % test_case
        exc_path = self.svn_exclusion_construct_source_repos(src_depot_dir)

        for idx, exclude_path in enumerate([exc_path, exc_path + '_1']):
            dst_depot = '//depot/buildtest%s_%s/...' % (src_depot_dir, idx)
            dst_mapping = ((dst_depot, './...'),)

            exclude_path = '-%s' % exclude_path
            src_mapping = ((src_depot_dir, ' '), (exclude_path, ' '))

            verification_exclude = exclude_path[len('-')+len(src_depot_dir):]
            exclude_subdir = [verification_exclude,]

            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli)
            verify_replication(src_mapping, dst_mapping,
                               src_docker_cli, dst_docker_cli,
                               excluded_subdirs=exclude_subdir)
            obliterate_all_depots(dst_docker_cli)

    def test_svn_action_rep_view_mapping_exclude_external_subdirs(self):
        '''Exclude a whole external: test_dir_parent/deploy
        '''
        test_case = 'svn_action_rep_view_mapping_exclude_externals_subdirs'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/%s' % test_case
        exc_path = self.svn_exclusion_construct_source_repos(src_depot_dir)

        for idx, exclude_path in enumerate([exc_path, exc_path + '_1']):
            dst_depot = '//depot/buildtest%s_%s/...' % (src_depot_dir, idx)
            dst_mapping = ((dst_depot, './...'),)

            exclude_path = '-%s/deploy' % exclude_path
            src_mapping = ((src_depot_dir, ' '), (exclude_path, ' '))

            verification_exclude = exclude_path[len('-')+len(src_depot_dir):]
            exclude_subdir = [verification_exclude,]

            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli)
            verify_replication(src_mapping, dst_mapping,
                               src_docker_cli, dst_docker_cli,
                               excluded_subdirs=exclude_subdir)
            obliterate_all_depots(dst_docker_cli)

    def test_svn_action_rep_view_mapping_externals_include_subdir(self):
        '''Exclude external: test_dir_parent/tests
        but keep test_dir_parent/tests/test-artifacts
        '''
        test_case = 'svn_action_rep_view_mapping_externals_include_subdir'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/%s' % test_case
        exc_path = self.svn_exclusion_construct_source_repos(src_depot_dir)

        for idx, exclude_path in enumerate([exc_path, exc_path + '_1']):
            dst_depot = '//depot/buildtest%s_%s/...' % (src_depot_dir, idx)
            dst_mapping = ((dst_depot, './...'),)

            exclude_dir = '-%s/tests' % exclude_path
            include_dir = '+%s/tests/test-artifacts' % exclude_path
            src_mapping = ((src_depot_dir, ' '), (exclude_dir, ' '),
                           (include_dir, ' '),)

            verification_exclude = exclude_dir[len('-')+len(src_depot_dir):]
            exclude_subdir = [os.path.join(verification_exclude, 'test-execution'),]

            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli)
            verify_replication(src_mapping, dst_mapping,
                               src_docker_cli, dst_docker_cli,
                               excluded_subdirs=exclude_subdir)
            obliterate_all_depots(dst_docker_cli)

    def test_svn_action_rep_view_mapping_externals_include_subsubdir(self):
        '''Exclude external: test_dir_parent/hadoop_src
        but keep test_dir_parent/hadoop_src/resources/images
        '''
        test_case = 'svn_action_rep_view_mapping_externals_include_subsubdir'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/%s' % test_case

        exc_path = self.svn_exclusion_construct_source_repos(src_depot_dir)

        for idx, exclude_path in enumerate([exc_path, exc_path + '_1']):
            dst_depot = '//depot/buildtest%s_%s/...' % (src_depot_dir, idx)
            dst_mapping = ((dst_depot, './...'),)

            exclude_dir = '-%s/hadoop_src' % exclude_path
            include_dir = '+%s/hadoop_src/resources/images' % exclude_path
            src_mapping = ((src_depot_dir, ' '),
                           (exclude_dir, ' '),
                           (include_dir, ' '),)

            external_files_to_exclude = ['resources/css/site.css', 'site.xml',
                                         'xdoc/index.xml',
                                         'xdoc/irc-channel.xml',
                                         'xdoc/issue-tracking.xml',
                                         'xdoc/mail-lists.xml',
                                         'xdoc/release-notes.xml',
                                         'xdoc/team-list.xml',]
            excluded_files = [os.path.join(exclude_path[len(src_depot_dir)+1:],
                                           'hadoop_src/%s' % fn)
                              for fn in external_files_to_exclude]

            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli)
            verify_replication(src_mapping, dst_mapping, src_docker_cli,
                               dst_docker_cli, excluded_files=excluded_files)
            obliterate_all_depots(dst_docker_cli)

    def test_svn_action_rep_view_mapping_rel_externals_include_subsubdir(self):
        '''Exclude external: test_dir_parent/hadoop/hadoop_src
        but keep test_dir_parent/hadoop/hadoop_src/resources/images
        '''
        test_case = 'svn_action_rep_view_mapping_rel_externals_include_subsubdir'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/%s' % test_case

        exc_path = self.svn_exclusion_construct_source_repos(src_depot_dir)

        for idx, exclude_path in enumerate([exc_path, exc_path + '_1']):
            dst_depot = '//depot/buildtest%s_%s/...' % (src_depot_dir, idx)
            dst_mapping = ((dst_depot, './...'),)

            exclude_dir = '-%s/hadoop/hadoop_src' % exclude_path
            include_dir = '+%s/hadoop/hadoop_src/resources/images' % exclude_path
            src_mapping = ((src_depot_dir, ' '),
                           (exclude_dir, ' '),
                           (include_dir, ' '),)

            external_files_to_exclude = ['resources/css/site.css', 'site.xml',
                                         'xdoc/index.xml',
                                         'xdoc/irc-channel.xml',
                                         'xdoc/issue-tracking.xml',
                                         'xdoc/mail-lists.xml',
                                         'xdoc/release-notes.xml',
                                         'xdoc/team-list.xml',]
            excluded_files = [os.path.join(exclude_path[len(src_depot_dir)+1:],
                                           'hadoop/hadoop_src/%s' % fn)
                              for fn in external_files_to_exclude]

            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli)
            verify_replication(src_mapping, dst_mapping, src_docker_cli,
                               dst_docker_cli, excluded_files=excluded_files)
            obliterate_all_depots(dst_docker_cli)


    def test_svn_action_rep_view_mapping_exclude_certain_file_0(self):
        '''Exclude test_dir_parent/a.*
        '''
        test_case = 'svn_action_rep_view_mapping_exclude_certain_file_0'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/%s' % test_case
        exc_path = self.svn_exclusion_construct_source_repos(src_depot_dir)

        for idx, exclude_path in enumerate([exc_path, exc_path + '_1']):
            dst_depot = '//depot/buildtest%s_%s/...' % (src_depot_dir, idx)
            dst_mapping = ((dst_depot, './...'),)

            exclude_mapping = '-%s/a.*' % exclude_path
            src_mapping = ((src_depot_dir, ' '),
                           (exclude_mapping, ' '))

            excluded_files = [os.path.join(exclude_path[len(src_depot_dir)+1:], fn)
                              for fn in ['a.exe', 'a.json', 'a.txt',]]

            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli)
            verify_replication(src_mapping, dst_mapping, src_docker_cli,
                               dst_docker_cli, excluded_files=excluded_files)
            obliterate_all_depots(dst_docker_cli)

    def test_svn_action_rep_view_mapping_exclude_certain_file_1(self):
        '''Exclude test_dir_parent/*.exe
        '''
        test_case = 'svn_action_rep_view_mapping_exclude_certain_file_1'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/%s' % test_case
        exc_path = self.svn_exclusion_construct_source_repos(src_depot_dir)

        for idx, exclude_path in enumerate([exc_path, exc_path + '_1']):
            dst_depot = '//depot/buildtest%s_%s/...' % (src_depot_dir, idx)
            dst_mapping = ((dst_depot, './...'),)

            exclude_mapping = '-%s/*.exe' % exclude_path
            src_mapping = ((src_depot_dir, ' '),
                           (exclude_mapping, ' '))

            excluded_files = [os.path.join(exclude_path[len(src_depot_dir)+1:], fn)
                              for fn in ['a.exe', 'b.exe', 'c.exe/a.json',
                                         'c.exe/a.txt', 'c.exe/b.txt',]]

            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli)
            verify_replication(src_mapping, dst_mapping, src_docker_cli,
                               dst_docker_cli, excluded_files=excluded_files)
            obliterate_all_depots(dst_docker_cli)

    def test_svn_action_rep_view_mapping_exclude_certain_file_2(self):
        '''Exclude test_dir_parent/.../*.exe
        '''
        test_case = 'svn_action_rep_view_mapping_exclude_certain_file_2'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/%s' % test_case
        exc_path = self.svn_exclusion_construct_source_repos(src_depot_dir)

        for idx, exclude_path in enumerate([exc_path, exc_path + '_1']):
            dst_depot = '//depot/buildtest%s_%s/...' % (src_depot_dir, idx)
            dst_mapping = ((dst_depot, './...'),)

            exclude_mapping_0 = '-%s/*.exe' % exclude_path
            exclude_mapping_1 = '-%s/.../*.exe' % exclude_path
            src_mapping = ((src_depot_dir, ' '),
                           (exclude_mapping_0, ' '),
                           (exclude_mapping_1, ' '),)

            excluded_files = [os.path.join(exclude_path[len(src_depot_dir)+1:], fn)
                              for fn in ['a.exe', 'b.exe', 'c.exe/a.json',
                                         'c.exe/a.txt', 'c.exe/b.txt',
                                         'some_dir/c.exe',]]

            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli)
            verify_replication(src_mapping, dst_mapping, src_docker_cli,
                               dst_docker_cli, excluded_files=excluded_files)
            obliterate_all_depots(dst_docker_cli)

    def test_svn_action_rep_view_mapping_exclude_subdir(self):
        '''Exclude a subdirectory
        '''
        test_case = 'svn_action_rep_view_mapping_exclude_subdir'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/%s' % test_case
        exc_path = self.svn_exclusion_construct_source_repos(src_depot_dir)

        for idx, exclude_path in enumerate([exc_path, exc_path + '_1']):
            dst_depot = '//depot/buildtest%s_%s/...' % (src_depot_dir, idx)
            dst_mapping = ((dst_depot, './...'),)

            exclude_mapping = '-%s/some_dir' % exclude_path
            src_mapping = ((src_depot_dir, ' '),
                           (exclude_mapping, ' '),)
            excluded_files = [os.path.join(exclude_path[len(src_depot_dir)+1:], fn)
                              for fn in ['some_dir/a.json', 'some_dir/a.txt',
                                         'some_dir/b.txt', 'some_dir/c.exe',]]

            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli)
            verify_replication(src_mapping, dst_mapping, src_docker_cli,
                               dst_docker_cli, excluded_files=excluded_files)
            obliterate_all_depots(dst_docker_cli)

    def test_svn_action_rep_view_mapping_exclude_subdir_inc_one_file(self):
        test_case = 'svn_action_rep_view_mapping_exclude_subdir_inc_one_file'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/%s' % test_case
        exc_path = self.svn_exclusion_construct_source_repos(src_depot_dir)

        #exc_path = exc_path[len(src_depot_dir):]
        for idx, exclude_path in enumerate([exc_path, exc_path + '_1']):
            dst_depot = '//depot/buildtest%s_%s/...' % (src_depot_dir, idx)
            dst_mapping = ((dst_depot, './...'),)

            logger.error(exc_path)
            exclude_mapping = '-%s/*.exe' % exclude_path
            include_mapping = '+%s/b.exe' % exclude_path
            src_mapping = ((src_depot_dir, ' '),
                           (exclude_mapping, ' '),
                           (include_mapping, ' '),)
            excluded_files = [os.path.join(exclude_path[len(src_depot_dir)+1:], fn)
                              for fn in ['a.exe', 'c.exe/a.json', 'c.exe/a.txt', 'c.exe/b.txt',]]

            replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                     src_docker_cli, dst_docker_cli)
            verify_replication(src_mapping, dst_mapping, src_docker_cli,
                               dst_docker_cli, excluded_files=excluded_files)

            obliterate_all_depots(dst_docker_cli)


    def test_svn_action_rep_sample_mapping_exclude_subdir(self):
        '''Exclude a subdirectory from sample svn repo
        '''
        test_case = 'svn_action_rep_sample_mapping_exclude_subdir'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/bigtop/trunk'
        exclude_path = '/bigtop/trunk/bigtop-packages'

        dst_depot = '//depot/buildtest%s/...' % test_case
        dst_mapping = ((dst_depot, './...'),)

        exclude_mapping = '-%s' % exclude_path
        src_mapping = ((src_depot_dir, ' '),
                       (exclude_mapping, ' '),)

        exclude_dirs = ['bigtop-packages',]
        replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                 src_docker_cli, dst_docker_cli)
        verify_replication(src_mapping, dst_mapping, src_docker_cli,
                           dst_docker_cli, excluded_subdirs=exclude_dirs)

    def test_svn_action_rep_sample_mapping_exclude_two_subdir(self):
        '''Exclude two subdirectories from sample svn repo
        '''
        test_case = 'svn_action_rep_sample_mapping_exclude_two_subdir'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/bigtop/trunk'
        exclude_path_0 = '/bigtop/trunk/bigtop-packages'
        exclude_path_1 = '/bigtop/trunk/bigtop-test-framework/src/main'

        dst_depot = '//depot/buildtest%s/...' % test_case
        dst_mapping = ((dst_depot, './...'),)

        exclude_mapping_0 = '-%s' % exclude_path_0
        exclude_mapping_1 = '-%s' % exclude_path_1
        src_mapping = ((src_depot_dir, ' '),
                       (exclude_mapping_0, ' '),
                       (exclude_mapping_1, ' '),)

        exclude_dirs = [exclude_path_0[len(src_depot_dir)+1:],
                        exclude_path_1[len(src_depot_dir)+1:],]
        replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                 src_docker_cli, dst_docker_cli)
        verify_replication(src_mapping, dst_mapping, src_docker_cli,
                           dst_docker_cli, excluded_subdirs=exclude_dirs)

    def test_svn_action_rep_sample_mapping_exclude_recursively_same_suffix(self):
        '''Exclude files with same suffix from sample svn repo
        '''
        test_case = 'svn_action_rep_sample_mapping_exclude_recursively_same_suffix'

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = self.docker_p4d_clients['p4d_0']

        src_depot_dir = '/bigtop/trunk'
        exclude_path = '/bigtop/trunk/bigtop-tests'

        dst_depot = '//depot/buildtest%s/...' % test_case
        dst_mapping = ((dst_depot, './...'),)

        exclude_mapping = '-%s/.../*.out' % exclude_path
        src_mapping = ((src_depot_dir, ' '),
                       (exclude_mapping, ' '),)

        rel_exc_files = '''test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-null-string.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-t_bool.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-t_date-export.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-all-tables.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-columns.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-where-clause.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-testtable.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-t_fp.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-t_string.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-t_bool-export.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-t_date.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-query.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-null-non-string.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-append.out
        test-artifacts/sqoop-smokes/src/main/resources/mysql-files/sqoop-t_int.out'''
        excluded_files = [os.path.join(exclude_path[len(src_depot_dir)+1:], fn.strip())
                          for fn in rel_exc_files.split('\n')]
        logger.error('excluded_files: %s' % excluded_files)
        replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                 src_docker_cli, dst_docker_cli)
        verify_replication(src_mapping, dst_mapping, src_docker_cli,
                           dst_docker_cli, excluded_files=excluded_files)

if __name__ == '__main__':
    unittest.main()

