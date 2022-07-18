#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''test replication of depots in svn repository.
'''

import os
import locale
import unittest
import lib.localestring as liblocale


from testcommon import (obliterate_all_depots,
                        set_p4d_unicode_mode,
                        get_p4d_from_docker)
from lib.buildcommon import (generate_random_str)
from replicationunittest import ReplicationTestCaseWithDocker

from testcommon_svnp4 import (replicate_SvnP4Replicate,
                              verify_replication,
                              get_svn_rev_list,
                              get_svn_from_docker,
                              svn_test_action_actions,)

from lib.buildlogger import getLogger
logger = getLogger(__name__)


class SvnBasicActionRepTest(ReplicationTestCaseWithDocker):
    def setUp(self):
        '''Obliterate all p4 depots due to file number limit of trial license
        '''
        dst_docker_cli = self.docker_p4d_clients['p4d_0']
        obliterate_all_depots(dst_docker_cli)

    def svn_test_action_add(self, docker_cli, depot_dir):
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            testdir = os.path.join(svn_root, depot_dir[1:])
            testfile = os.path.join(testdir, 'repo_test_file')
            os.mkdir(testdir)

            action = 'adding %s\n' % testdir
            with open(testfile, 'wt') as f:
                f.write(action)
            svn.run_add(testdir)
            svn.run_checkin(testdir, '%s' % action)

    def common_svn_test_externals(self, docker_cli, depot_dir, external_cfgs):
        src_svn = self.docker_svn_clients['svn_0']
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            testdir = os.path.join(svn_root, depot_dir[1:])
            testfile = os.path.join(testdir, 'repo_test_file')
            os.mkdir(testdir)

            action = 'adding %s\n' % testdir
            with open(testfile, 'wt') as f:
                f.write(action)
            svn.run_add(testdir)
            svn.run_checkin(testdir, '%s' % action)
            # set external
            for external_cfg in external_cfgs:
                svn.run_update(testdir)
                if not external_cfg:
                    svn.client.propdel('svn:externals', testdir)
                else:
                    svn.client.propset('svn:externals', external_cfg, testdir)
                svn.run_checkin(testdir, 'added external %s' % external_cfg)

                action = 'editing %s\n' % testfile
                with open(testfile, 'a') as f:
                    f.write(action)
                svn.run_checkin(testfile, '%s' % action)

            # delete external
            svn.run_update(testdir)
            svn.client.propdel('svn:externals', testdir)
            svn.run_checkin(testdir, 'del external')

            action = 'editing %s\n' % testfile
            with open(testfile, 'a') as f:
                f.write(action)
            svn.run_checkin(testfile, '%s' % action)

    def svn_test_externals_special1(
            self,
            docker_cli,
            depot_dir,
            external_cfgs):
        '''this function generates a test directory with interleaving
        externals and files
        '''
        src_svn = self.docker_svn_clients['svn_0']
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            testdir = os.path.join(svn_root, depot_dir[1:])
            testfile = os.path.join(testdir, 'repo_test_file')
            os.mkdir(testdir)

            action = 'adding %s\n' % testdir
            with open(testfile, 'wt') as f:
                f.write(action)
            svn.run_add(testdir)
            svn.run_checkin(testdir, '%s' % action)

            # set external
            for external_cfg in external_cfgs:
                svn.run_update(testdir)

                external_todir_rel = external_cfg.split()[1]
                external_todir_rel_root = external_todir_rel.split('/')[0]
                dir_to_add = os.path.join(testdir, external_todir_rel_root)
                external_todir_abs = os.path.join(testdir, external_todir_rel)
                external_todir_base = os.path.split(external_todir_abs)[0]
                os.makedirs(external_todir_base)
                testfile = os.path.join(external_todir_base, 'test_file')

                action = 'adding %s\n' % testfile
                with open(testfile, 'wt') as f:
                    f.write(action)
                svn.run_add(dir_to_add)
                svn.run_checkin(dir_to_add, '%s' % action)

                svn.run_update(testdir)
                if not external_cfg:
                    svn.client.propdel('svn:externals', testdir)
                else:
                    svn.client.propset('svn:externals', external_cfg, testdir)
                svn.run_checkin(testdir, 'added external %s' % external_cfg)

                action = 'editing %s\n' % testfile
                with open(testfile, 'a') as f:
                    f.write(action)
                svn.run_checkin(testfile, '%s' % action)

            # delete external
            svn.run_update(testdir)
            svn.client.propdel('svn:externals', testdir)
            svn.run_checkin(testdir, 'del external')

            action = 'editing %s\n' % testfile
            with open(testfile, 'a') as f:
                f.write(action)
            svn.run_checkin(testfile, '%s' % action)

    def svn_test_externals_10(self, docker_cli, depot_dir):
        external_svn = self.docker_svn_clients['svn_1']
        external_ip = external_svn.get_container_ip_addr()
        external_url = 'svn://%s:3690' % external_ip
        external_url += '/repos/bigtop/branches/hadoop-0.23/bigtop-repos/apt'
        external_cfg = ['%s a/b/c/apt' % external_url, ]
        self.svn_test_externals_special1(docker_cli, depot_dir, external_cfg)

    def svn_test_externals_0(self, docker_cli, depot_dir):
        external_svn = self.docker_svn_clients['svn_1']
        external_ip = external_svn.get_container_ip_addr()
        external_url = 'svn://%s:3690' % external_ip
        external_url += '/repos/bigtop/branches/hadoop-0.23/bigtop-repos/apt'
        external_cfg = ['%s apt' % external_url]
        self.common_svn_test_externals(docker_cli, depot_dir, external_cfg)

    def svn_test_externals_1(self, docker_cli, depot_dir):
        external_repo = '../bigtop/branches/hadoop-0.23/bigtop-repos/apt'
        external_cfg = ['%s apt' % external_repo]
        self.common_svn_test_externals(docker_cli, depot_dir, external_cfg)

    def svn_test_externals_2(self, docker_cli, depot_dir):
        external_repo = '^/bigtop/branches/hadoop-0.23/bigtop-repos/apt'
        external_cfg = ['%s apt' % external_repo]
        self.common_svn_test_externals(docker_cli, depot_dir, external_cfg)

    def svn_test_externals_3(self, docker_cli, depot_dir):
        external_svn = self.docker_svn_clients['svn_1']
        external_ip = external_svn.get_container_ip_addr()
        external_url = 'svn://%s:3690' % external_ip
        external_url += '/repos/bigtop/branches/hadoop-0.23/bigtop-repos/apt'
        external_cfg = ['apt %s' % external_url]
        self.common_svn_test_externals(docker_cli, depot_dir, external_cfg)

    def svn_test_externals_4(self, docker_cli, depot_dir):
        external_cfg = '^/bigtop/branches/hadoop-0.23/bigtop-repos/apt apt\n'
        external_cfg += '../bigtop/branches/hadoop-0.23/bigtop-tests tests'
        external_cfg = [external_cfg]
        self.common_svn_test_externals(docker_cli, depot_dir, external_cfg)

    def svn_test_externals_5(self, docker_cli, depot_dir):
        external_cfg0 = '^/bigtop/branches/hadoop-0.23/bigtop-repos/apt apt'
        external_cfg1 = '^/bigtop/branches/hadoop-0.23/bigtop-repos/apt apt\n'
        external_cfg1 += '../bigtop/branches/hadoop-0.23/bigtop-tests tests'
        external_cfgs = [external_cfg0, external_cfg1]
        self.common_svn_test_externals(docker_cli, depot_dir, external_cfgs)

    def svn_test_externals_6(self, docker_cli, depot_dir, **kwargs):
        external_cfg0 = '^/bigtop/branches/hadoop-0.23/bigtop-repos/apt apt'
        external_cfg1 = '../bigtop/branches/hadoop-0.23/bigtop-tests apt'
        external_cfgs = [external_cfg0, external_cfg1]
        self.common_svn_test_externals(docker_cli, depot_dir, external_cfgs)

    def svn_test_externals_7(self, docker_cli, depot_dir):
        external_cfg0 = ' -r950 ../bigtop/trunk/bigtop-tests@950 tests'
        external_cfgs = [external_cfg0]
        self.common_svn_test_externals(docker_cli, depot_dir, external_cfgs)

    def svn_test_externals_8(self, docker_cli, depot_dir):
        external_cfg0 = '../bigtop/branches/hadoop-0.23/docs docs'
        external_cfgs = [external_cfg0]
        self.common_svn_test_externals(docker_cli, depot_dir, external_cfgs)

        src_svn = self.docker_svn_clients['svn_0']
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            bigtop_repos = os.path.join(
                svn_root, 'bigtop/branches/hadoop-0.23')
            svn.run_update(bigtop_repos, update_arg='--set-depth infinity')

            testdir = os.path.join(bigtop_repos, 'docs')
            action = 'delete %s' % testdir
            svn.run_remove(testdir)
            svn.run_checkin(testdir, action)

    def svn_test_externals_9(self, docker_cli, depot_dir):
        external_cfg = '../bigtop/branches/hadoop-0.23/bigtop-deploy bigtop-deploy'

 #       src_svn = self.docker_svn_clients['svn_0']
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            testdir = os.path.join(svn_root, depot_dir[1:])
            testfile = os.path.join(testdir, 'repo_test_file')
            os.mkdir(testdir)

            action = 'adding %s\n' % testdir
            with open(testfile, 'wt') as f:
                f.write(action)
            svn.run_add(testdir)
            svn.client.propset('svn:externals', external_cfg, testdir)
            svn.run_checkin(testdir, '%s' % action)

            action = 'editing %s\n' % testfile
            with open(testfile, 'a') as f:
                f.write(action)
            svn.run_checkin(testfile, '%s' % action)

            bigtop_repos = os.path.join(
                svn_root, 'bigtop/branches/hadoop-0.23')
            svn.run_update(bigtop_repos, update_arg='--set-depth infinity')

            testdir = os.path.join(bigtop_repos, 'bigtop-deploy')
            action = 'delete %s' % testdir
            svn.run_remove(testdir)
            svn.run_checkin(testdir, action)

    def svn_test_externals_11(self, docker_cli, depot_dir):
        external_url = '/repos/bigtop/branches/hadoop-0.23/bigtop-repos/apt'
        external_cfg = ['%s apt' % external_url]
        self.common_svn_test_externals(docker_cli, depot_dir, external_cfg)

    def svn_test_russian_filename(self, docker_cli, depot_dir):
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            testdir = os.path.join(svn_root, depot_dir[1:])
            os.mkdir(testdir)

            sys_locale = locale.getdefaultlocale()
            filename = 'следовательносуществую.txt'
#            filename = filename.encode(sys_locale[1])
            filename = os.path.join(testdir, filename)
            with open(filename, 'w') as f:
                f.write(filename)

            from subprocess import Popen, check_output, PIPE
            p = Popen('svn add %s' % testdir, stdout=PIPE,
                      stderr=PIPE, shell=True)
            out, err = p.communicate()
            logger.info('%s, %s', out, err)

            p = Popen('svn commit -m russianfilename', stdout=PIPE,
                      stderr=PIPE, shell=True)
            out, err = p.communicate()
            logger.info('%s, %s', out, err)

    def svn_test_action_edit(self, docker_cli, depot_dir):
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            testdir = os.path.join(svn_root, depot_dir[1:])
            testfile = os.path.join(testdir, 'repo_test_file')
            os.mkdir(testdir)

            action = 'adding %s\n' % testdir
            with open(testfile, 'wt') as f:
                f.write(action)
            svn.run_add(testdir)
            svn.run_checkin(testdir, '%s' % action)

            action = 'editing %s\n' % testfile
            with open(testfile, 'a') as f:
                f.write(action)
            svn.run_checkin(testfile, '%s' % action)

    def svn_test_setup_src_branch(self, docker_cli, depot_dir,
                                  edits_in_other_folder_before_copy=False):
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            test_dir = os.path.join(svn_root, depot_dir[1:])
            trunk_dir = os.path.join(test_dir, 'trunk')
            branch_dir_1 = os.path.join(test_dir, 'branches_1')
            branch_dir_2 = os.path.join(test_dir, 'branches_2')
            src_dir = os.path.join(trunk_dir, 'src')

            for directory in [test_dir, trunk_dir, branch_dir_1,
                              branch_dir_2, src_dir]:
                os.mkdir(directory)
                action = 'adding %s\n' % directory
                svn.run_add(directory)
                svn.run_checkin(directory, '%s' % action)

            # add test file
            test_file = os.path.join(src_dir, 'repo_test_file')
            test_file2 = os.path.join(branch_dir_2, 'repo_test_file')
            for tf in [test_file2, test_file]:
                action = 'adding %s\n' % tf
                with open(tf, 'wt') as f:
                    f.write(action)
                svn.run_add(tf)
                svn.run_checkin(tf, '%s' % action)

            if edits_in_other_folder_before_copy:
                for idx in range(3):
                    # edit test file
                    action = 'editing %s Num. %d\n' % (test_file2, idx)
                    with open(test_file2, 'a') as f:
                        f.write(action)
                    svn.run_checkin(test_file2, '%s' % action)

            # add branch
            branch1 = os.path.join(branch_dir_1, generate_random_str())
            svn.run_copy(trunk_dir, branch1)
            svn.run_checkin(branch1, '1st branch')

            # edit test file in branch
            test_file = os.path.join(branch1,
                                     '/'.join(test_file.split('/')[-2:]))
            action = 'editing %s\n' % test_file
            with open(test_file, 'a') as f:
                f.write(action)
            svn.run_checkin(test_file, '%s' % action)

        return trunk_dir[len(svn_root):], branch1[len(svn_root):]

    def svn_test_replicate_subdir(self, docker_cli, depot_dir):
        trunk, branch = self.svn_test_setup_src_branch(docker_cli, depot_dir)

        return os.path.join(branch, 'src')

    def svn_test_action_commitmsg(self, docker_cli, depot_dir, commit_msg):
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            testdir = os.path.join(svn_root, depot_dir[1:])
            testfile = os.path.join(testdir, 'repo_test_file')
            os.mkdir(testdir)

            act_str = 'adding %s\n' % testdir
            with open(testfile, 'wt') as f:
                f.write(act_str)
            svn.run_add(testdir)
            svn.run_checkin(testdir, '%s' % act_str)

            encoding, act_str_orig = commit_msg
            act_str = act_str_orig[:]
            with open(testfile, 'a') as f:
                f.write(act_str)
            cmd = "-m '%s'" % act_str
            svn._run('commit', cmd)

            '''
            # more tests for utf-8
            encoding = 'utf-8'
            act_str = act_str_orig[:]
            with open(testfile, 'a') as f:
                f.write(act_str.encode(encoding))
            act_str = act_str.encode(encoding)
            cmd = "--encoding %s -m '%s'" % (encoding, act_str)
            svn.run_cmd_with_args('commit', cmd)
            '''

    def svn_test_action_symbol_in_commitmsg(
            self, docker_cli, depot_dir, commit_msg):
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            testdir = os.path.join(svn_root, depot_dir[1:])
            testfile = os.path.join(testdir, 'repo_test_file')
            os.mkdir(testdir)

            act_str = 'adding %s\n' % testdir
            with open(testfile, 'wt') as f:
                f.write(act_str)
            svn.run_add(testdir)
            svn.run_checkin(testdir, '%s' % act_str)

            with open(testfile, 'a') as f:
                f.write('something more')
            svn.run_checkin(testfile, commit_msg)

    def svn_test_action_deletefile(self, docker_cli, depot_dir):
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            testdir = os.path.join(svn_root, depot_dir[1:])
            testfile = os.path.join(testdir, 'repo_test_file')
            os.mkdir(testdir)

            action = 'add %s' % testdir
            with open(testfile, 'wt') as f:
                f.write(action)
            svn.run_add(testdir)
            svn.run_checkin(testdir, action)

            action = 'edit %s' % testfile
            with open(testfile, 'a') as f:
                f.write(action)
            svn.run_checkin(testfile, action)

            action = 'delete %s' % testfile
            svn.run_remove(testfile)
            svn.run_checkin(testfile, action)

    def svn_test_add_empty_dir(self, docker_cli, project_dir):
        with get_svn_from_docker(docker_cli) as (svn, svn_root):
            # add project directory
            project_dir = os.path.join(svn_root, project_dir[1:])
            os.mkdir(project_dir)
            test_dir = os.path.join(project_dir, 'test_dir')
            os.mkdir(test_dir)

            action = 'add %s' % project_dir
            svn.run_add(project_dir)
            svn.run_checkin(project_dir, action)

            test_file = os.path.join(test_dir, 'repo_test_file')
            action = 'add %s' % test_file
            with open(test_file, 'wt') as f:
                f.write(action)
            svn.run_add(test_file)
            svn.run_checkin(test_file, action)

    def svn_action_rep_action(self, action, act_func, **kwargs):
        '''create test env, run test, and verify replication

        @param action, string of action to be tested
        @param act_func, function to be called to create test svn repo
        @param **kwargs, other arguments used to create test repo
        '''
        test_case = 'svn_action_rep_%s' % action

        src_depot_dir = '/reptest_%s' % action
        dst_depot_dir = src_depot_dir

        src_docker_cli = self.docker_svn_clients['svn_0']
        dst_docker_cli = kwargs.get('dst_docker_cli')
        if not dst_docker_cli:
            dst_docker_cli = self.docker_p4d_clients['p4d_0']
        else:
            del kwargs['dst_docker_cli']

        group_num = kwargs.get('group_num')
        if group_num:
            del kwargs['group_num']
        test_dir = act_func(src_docker_cli, src_depot_dir, **kwargs)
        if test_dir:
            src_depot_dir = test_dir

        dst_depot = '//depot/buildtest%s/...' % dst_depot_dir
        dst_view = ((dst_depot, './...'),)

        if kwargs.get('replicate_only_branch_dir'):
            src_depot_dir = os.path.join(src_depot_dir, 'branches')
            del kwargs['replicate_only_branch_dir']

        src_mapping = ((src_depot_dir, ' '),)
        dst_mapping = dst_view

        replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                 src_docker_cli, dst_docker_cli, **kwargs)
        verify_replication(src_mapping, dst_mapping,
                           src_docker_cli, dst_docker_cli, **kwargs)

        if group_num is None:
            return dst_depot

        obliterate_all_depots(dst_docker_cli)

        svn_revs = get_svn_rev_list(src_docker_cli, src_depot_dir)
        num_replicate = group_num
        svn_revs.insert(0, 0)

        for src_counter in svn_revs[::num_replicate]:
            replicate_SvnP4Replicate(
                src_mapping,
                dst_mapping,
                src_docker_cli,
                dst_docker_cli,
                src_counter=0,
                replicate_change_num=num_replicate,
                **kwargs)

            verify_replication(src_mapping, dst_mapping,
                               src_docker_cli, dst_docker_cli,
                               src_counter=src_counter,
                               replicate_change_num=num_replicate, **kwargs)
        logger.passed(test_case)

        return dst_depot

    def test_svn_action_rep_externals_other_srv(self):
        self.svn_action_rep_action('svn_externals_other_srv',
                                   self.svn_test_externals_0)

    def test_svn_action_rep_externals_other_repo(self):
        self.svn_action_rep_action('svn_externals_other_repo',
                                   self.svn_test_externals_1)

    def test_svn_action_rep_externals_root_of_repo(self):
        self.svn_action_rep_action('svn_externals_root_of_repo',
                                   self.svn_test_externals_2)

    def test_svn_action_rep_externals_reverse_order_remote(self):
        self.svn_action_rep_action('svn_externals_reverse_order_remote',
                                   self.svn_test_externals_3)

    def test_svn_action_rep_externals_two_externals(self):
        self.svn_action_rep_action('svn_externals_two_externals',
                                   self.svn_test_externals_4)

    def test_svn_action_rep_externals_two_externals_to_one(self):
        self.svn_action_rep_action('svn_externals_two_externals_to_one',
                                   self.svn_test_externals_5)

    def test_svn_action_rep_externals_change_externals(self):
        self.svn_action_rep_action('svn_externals_change_externals',
                                   self.svn_test_externals_6)

    def test_svn_action_rep_externals_with_revision(self):
        self.svn_action_rep_action('svn_externals_change_with_revision',
                                   self.svn_test_externals_7)

    def test_svn_action_rep_externals_no_longer_exist(self):
        self.svn_action_rep_action('svn_externals_change_no_longer_exist',
                                   self.svn_test_externals_8)

    def test_svn_action_rep_externals_add_dir_with_externals(self):
        self.svn_action_rep_action('svn_externals_add_dir_with_externals',
                                   self.svn_test_externals_9)

    def test_svn_action_rep_externals_interleaving_externals_and_other_1(self):
        self.svn_action_rep_action(
            'svn_externals_interleaving_externals_and_other_1',
            self.svn_test_externals_10,
            group_num=1)

    def test_svn_action_rep_externals_interleaving_externals_and_other_2(self):
        self.svn_action_rep_action(
            'svn_externals_interleaving_externals_and_other_2',
            self.svn_test_externals_10,
            group_num=2)

    def test_svn_action_rep_externals_interleaving_externals_and_other_3(self):
        self.svn_action_rep_action(
            'svn_externals_interleaving_externals_and_other_3',
            self.svn_test_externals_10,
            group_num=3)

    def test_svn_action_rep_externals_ignore_externals(self):
        self.svn_action_rep_action('svn_externals_ignore_externals',
                                   self.svn_test_externals_6,
                                   svn_ignore_externals=True)

    def test_svn_action_rep_externals_relative_to_root_url(self):
        self.svn_action_rep_action('svn_externals_relative_to_root_url',
                                   self.svn_test_externals_11)

    def test_svn_action_rep_add(self):
        self.svn_action_rep_action('add',
                                   self.svn_test_action_add)

    def test_svn_action_rep_russianfilename(self):
        self.svn_action_rep_action('russianfilename',
                                   self.svn_test_russian_filename)

    def test_svn_action_rep_add_dir(self):
        self.svn_action_rep_action('add_dir',
                                   svn_test_action_actions,
                                   actions=['edit', 'add_dir', 'edit'])

    def test_svn_action_rep_edit(self):
        self.svn_action_rep_action('edit',
                                   self.svn_test_action_edit)

    def test_svn_action_rep_delete_file(self):
        self.svn_action_rep_action('delete_file',
                                   self.svn_test_action_deletefile)

    def test_svn_action_rep_delete_dir(self):
        self.svn_action_rep_action('delete_dir',
                                   svn_test_action_actions,
                                   actions=['delete_dir'])

    def test_svn_action_rep_delete_file_add(self):
        self.svn_action_rep_action(
            'delete_file_add',
            svn_test_action_actions,
            actions=[
                'edit',
                'rename',
                'delete_file',
                'add_exec'])

    def test_svn_action_rep_rename(self):
        self.svn_action_rep_action(
            'rename', svn_test_action_actions, actions=[
                'edit', 'edit', 'rename', 'rename'])

    def test_svn_adding_rep_empty_dir(self):
        self.svn_action_rep_action('empty_dir',
                                   self.svn_test_add_empty_dir)

    def test_svn_action_rep_copy_latest(self):
        self.svn_action_rep_action('copy_latest',
                                   svn_test_action_actions,
                                   actions=['copy_latest'])

    def test_svn_action_rep_exec_file(self):
        self.svn_action_rep_action('add_exec',
                                   svn_test_action_actions,
                                   actions=['add_exec'])

    def test_svn_action_rep_changing_exec_file_g2(self):
        self.svn_action_rep_action('changing_exec_g2',
                                   svn_test_action_actions,
                                   actions=['changing_exec'],
                                   group_num=2)

    def test_svn_action_rep_changing_exec_file_g3(self):
        self.svn_action_rep_action('changing_exec_g3',
                                   svn_test_action_actions,
                                   actions=['changing_exec'],
                                   group_num=3)

    def test_svn_action_rep_replace_file(self):
        self.svn_action_rep_action('replace_file',
                                   svn_test_action_actions,
                                   actions=['replace_file'])

    def test_svn_action_rep_replace_dir_empty(self):
        self.svn_action_rep_action('replace_dir_empty',
                                   svn_test_action_actions,
                                   actions=['replace_dir_empty'])

    def test_svn_action_rep_replace_dir_new_file(self):
        self.svn_action_rep_action('replace_dir_new_file',
                                   svn_test_action_actions,
                                   actions=['replace_dir_new_file'])

    def test_svn_action_rep_replace_dir_same_file(self):
        self.svn_action_rep_action('replace_dir_same_file',
                                   svn_test_action_actions,
                                   actions=['replace_dir_same_file'])

    def test_svn_action_rep_replace_dir_same_file_one_more(self):
        self.svn_action_rep_action('replace_dir_same_file_one_more',
                                   svn_test_action_actions,
                                   actions=['replace_dir_same_file_one_more'])

    def test_svn_action_rep_copy_prev(self):
        self.svn_action_rep_action('copy_prev',
                                   svn_test_action_actions,
                                   actions=['copy_prev'])

    def test_svn_action_rep_symlink_rel(self):
        self.svn_action_rep_action(
            'symlink_rel', svn_test_action_actions, actions=[
                'edit', 'rename', 'symlink_rel', 'edit'])

    def test_svn_action_rep_symlink_abs(self):
        self.svn_action_rep_action(
            'symlink_abs', svn_test_action_actions, actions=[
                'edit', 'rename', 'symlink_abs', 'edit'])

    def test_svn_action_rep_changing_symlink_g2(self):
        self.svn_action_rep_action('changing_symlink_g2',
                                   svn_test_action_actions,
                                   actions=['edit', 'changing_symlink', ],
                                   group_num=2)

    def test_svn_action_rep_changing_symlink_g3(self):
        self.svn_action_rep_action('changing_symlink_g3',
                                   svn_test_action_actions,
                                   actions=['edit', 'changing_symlink', ],
                                   group_num=3)

    def test_svn_action_rep_special_file_name(self):
        special_names = {
            'specialcharacter': 'a_file_with_%_*_#_@_in_its_name.txt',
            'space_in_name': 'file_with_space _in_its_name.txt',
            'single_quote_in_name': "file_with_space'_in_its_name.txt",
            'russian_filename': 'следовательносуществую.txt',
        }
        for case, name in list(special_names.items()):
            # import locale
            # _, locale_encoding = locale.getlocale()
            # name = name.encode(locale_encoding)
            self.svn_action_rep_action(
                case, svn_test_action_actions, actions=[
                    'edit', 'rename', 'delete_dir'], special_filename=name)

    def test_svn_action_rep_special_file_name_unicodeserver(self):
        special_names = {
            'specialcharacter': 'a_file_with_%_*_#_@_in_its_name.txt',
            'space_in_name': 'file_with_space _in_its_name.txt',
            'russian_filename': 'следовательносуществую.txt',
        }
        dst_docker_cli = self.docker_p4d_clients['unicode-server']
        set_p4d_unicode_mode(dst_docker_cli)
        for case, name in list(special_names.items()):
            # import locale
            # _, locale_encoding = locale.getlocale()
            # name = name.encode(locale_encoding)
            self.svn_action_rep_action(
                case + '_unicodeserver',
                svn_test_action_actions,
                actions=[
                    'edit',
                    'rename',
                    'delete_dir'],
                special_filename=name,
                dst_docker_cli=dst_docker_cli)

    def test_svn_action_rep_special_dir_name(self):
        special_names = {
            'specialcharacterdir': 'a_file_with_%_*_#_@_in_its_name.txt',
            'space_in_dirname': 'file_with_space _in_its_name.txt',
        }
        for case, name in list(special_names.items()):
            self.svn_action_rep_action(
                case, svn_test_action_actions, actions=[
                    'edit', 'rename', 'delete_dir'], special_dirname=name)

    def test_svn_action_rep_trunk_with_branch(self):
        actions = ['edit', 'rename', 'delete_file', 'add_exec',
                   'branch', 'edit', 'delete_dir']
        self.svn_action_rep_action('trunk_with_branch',
                                   svn_test_action_actions,
                                   actions=actions)

    def test_svn_action_rep_branch(self):
        actions = ['edit', 'rename', 'delete_file', 'add_exec',
                   'branch', 'edit', 'delete_dir']
        self.svn_action_rep_action('branch',
                                   svn_test_action_actions,
                                   actions=actions,
                                   replicate_only_branch_dir=True)

    def gen_special_commitmsgs(self):
        commit_msgs = {'utf-8': 'I think, therefore I am.',
                       'cp1251': 'мыслю, следовательно существую.', }

        if liblocale.locale_encoding == "UTF-8":
            commit_msgs.update({'gb2312': '我思故我在.',
                                'latin1': 'La Santé'})
        return commit_msgs

    def test_svn_action_rep_special_commitmsgs(self):
        commitmsgs = self.gen_special_commitmsgs()
        for encoding, msg in list(commitmsgs.items()):
            self.svn_action_rep_action(encoding,
                                       self.svn_test_action_commitmsg,
                                       commit_msg=[encoding, msg])

    def test_svn_action_rep_special_commitmsgs_unicodeserver(self):
        commitmsgs = self.gen_special_commitmsgs()
        dst_docker_cli = self.docker_p4d_clients['unicode-server']
        set_p4d_unicode_mode(dst_docker_cli)

        for encoding, msg in list(commitmsgs.items()):
            self.svn_action_rep_action(encoding+'_unicodeserver',
                                       self.svn_test_action_commitmsg,
                                       commit_msg=[encoding, msg],
                                       dst_docker_cli=dst_docker_cli)

    def test_svn_action_rep_review_commitmsgs(self):
        orig_desc = 'add new file, and testing review in comments\n'
        orig_desc += '#review-22\n'
        orig_desc += '##review-22review\n'
        expected_desc = 'add new file, and testing review in comments\n'
        expected_desc += '# review-22\n'
        expected_desc += '## review-22review\n'

        dst_depot = self.svn_action_rep_action('remove_review_commitmsg',
                                               self.svn_test_action_commitmsg,
    commit_msg=['utf-8', orig_desc])

        dst_docker_cli = self.docker_p4d_clients['p4d_0']
        dst_dir = dst_depot[1:-4]
        with get_p4d_from_docker(dst_docker_cli, dst_dir) as p4:
            changes = p4.run_changes('-l', '...')
            last_change = changes[0]
            desc = last_change['desc']
            self.assertTrue(expected_desc in desc, desc)

        obliterate_all_depots(dst_docker_cli)

    def test_svn_action_rep_symbols_in_commitmsgs(self):
        commitmsgs  = ['"a " b "',
                       "'a ' b '",
                       " aaa b ec \\\\",
                       " aaa b ec \\",
                       "let's `ls -al` \\",
                       "hello world` a",
                       "hell world",
                       "aaa `ls -l`",
                       "# ls ",
                       "'''",
                       "''",
                       '"""',
                       '""',
                       '|',
                       'echo $HOME',
                       'echo $$HOME',
                       'echo \$HOME',
                       'echo #!/usr/bin/ls -al',
                       '`#!/usr/bin/bash ls`',
                       '`#!/usr/bin/sh history`',
                       '*',
                       '(a=hello; echo $a)',
        ]

        for idx, msg in enumerate(commitmsgs):
            test_item = 'symbol_in_commitmsg-%d' % idx
            self.svn_action_rep_action(test_item,
                                       self.svn_test_action_symbol_in_commitmsg,
                                       commit_msg=msg)

    def test_svn_action_rep_branch_subdir(self):
        self.svn_action_rep_action('branch_subdir',
                                   self.svn_test_replicate_subdir)

    def test_svn_action_rep_branch_detection(self):
        '''test svn->p4 branch point detection script'''
        action = 'branch_detection'
        src_docker_cli = self.docker_svn_clients['svn_bd']
        result = self.svn_action_rep_branch_detection(action, src_docker_cli,
                                                      self.svn_test_setup_src_branch,
                                                      False)
        should_branch_from = '//depot/svn_rep/buildtest_trunk/...@12106'
        should_skip_revision = 985
        self.assertEqual(result[0], should_branch_from)
        self.assertEqual(result[1], should_skip_revision)

    def test_svn_action_rep_branch_detection_extra_rev(self):
        '''test svn->p4 branch point detection script'''
        action = 'branch_detection_rev'
        src_docker_cli = self.docker_svn_clients['svn_bd_rev']
        result = self.svn_action_rep_branch_detection(action, src_docker_cli,
                                                      self.svn_test_setup_src_branch,
                                                      True)

        should_branch_from = '//depot/svn_rep/buildtest_trunk/...@12106'
        should_skip_revision = 988
        self.assertEqual(result[0], should_branch_from)
        self.assertEqual(result[1], should_skip_revision)

    def svn_action_rep_branch_detection(self, action, src_docker_cli, act_func,
                                        edits_in_other_folder_before_copy):
        '''test svn->p4 branch point detection script'''
        test_case = 'svn_action_rep_%s' % action

        dst_docker_cli = self.docker_p4d_clients['p4d_%s' % action]

        src_depot_dir = '/reptest_%s' % action
        trunk, branch = act_func(src_docker_cli, src_depot_dir,
                                 edits_in_other_folder_before_copy)

        trunk_src = os.path.join(trunk, 'src')
        branch_src = os.path.join(branch, 'src')

        # replicate trunk
        src_depot_dir = trunk
        dst_depot_dir = src_depot_dir

        dst_depot = '//depot/svn_rep/buildtest_trunk/...'
        dst_view = ((dst_depot, './...'),)

        src_mapping = ((src_depot_dir, ' '),)
        dst_mapping = dst_view

        args = replicate_SvnP4Replicate(src_mapping, dst_mapping,
                                        src_docker_cli, dst_docker_cli)
        verify_replication(src_mapping, dst_mapping,
                           src_docker_cli, dst_docker_cli)

        args.target_rep_branch_root = '//depot/svn_rep'
        args.source_project_dir = branch_src

        # detect svn branch point
        from SvnP4BranchDetection import detect_branch_point
        branch_from = detect_branch_point(args)
        return branch_from


if __name__ == '__main__':
    unittest.main()
