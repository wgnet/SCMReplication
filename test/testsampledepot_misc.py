#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''some misc test cases
'''

import os
import shutil
import tempfile

from testcommon import (BUILD_TEST_P4D_USER,
                        replicate_sample_view,
                        get_p4d_from_docker,
                        obliterate_all_depots)
from lib.p4server import P4Server
from lib.buildlogger import getLogger
from lib.scmp4 import RepP4Exception
from lib.scm2scm import ReplicationException
from replicationunittest import ReplicationTestCaseWithDocker

logger = getLogger(__name__)


class SampleDepotTestMisc(ReplicationTestCaseWithDocker):

    def replicate_sample_dir_withdocker(self, depot_dir, **kwargs):
        '''test replicating directory

        create/start src/dst docker containers.  connect to src/dst
        p4d
        '''
        src_depot = '/%s/...' % depot_dir
        dst_depot = '//depot/buildtest%s/...' % depot_dir

        src_view = ((src_depot, './...'),)
        dst_view = ((dst_depot, './...'),)

        src_docker = kwargs.pop('src_docker_cli', None)
        if not src_docker:
            src_docker = self.docker_clients[0]

        dst_docker = kwargs.pop('dst_docker_cli', None)
        if not dst_docker:
            dst_docker = self.docker_clients[1]

        replicate_sample_view(src_view, dst_view,
                              src_docker_cli=src_docker,
                              dst_docker_cli=dst_docker,
                              **kwargs)
        return dst_depot

    def test_replicate_sample_depot_lastchange(self):
        test_case = 'replicate_sample_depot_lastchange'

        depot_dir = '/depot/Jam'
        src_docker_cli = self.docker_clients[0]
        self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli,
                                             source_last_changeset=35)

        logger.passed(test_case)

    def test_replicate_sample_depot_maximum(self):
        test_case = 'replicate_sample_depot_maximum'

        depot_dir = '/depot/Jam'
        src_docker_cli = self.docker_clients[0]
        self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli,
                                             replicate_change_num=10)

        logger.passed(test_case)

    def test_replicate_sample_depot_resume_from_manual_change(self):
        test_case = 'replicate_sample_depot_resume_from_manual_change'

        depot_dir = '/depot/Jam'
        src_docker_cli = self.docker_clients[0]
        dst_docker_cli = self.docker_clients[1]
        dst_depot = self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli,
                                             dst_docker_cli=dst_docker_cli,
                                             replicate_change_num=10,
                                             obliterate=False)

        dst_dir = dst_depot[1:-4]
        # manual commit to mess up replication script
        with get_p4d_from_docker(dst_docker_cli, dst_dir) as dst_p4:
            clientspec = dst_p4.fetch_client(dst_p4.client)
            ws_root = clientspec._root

            test_file_path = os.path.join(ws_root, 'test_file_')
            with open(test_file_path, 'wt') as f:
                f.write('My name is %s!\n' % test_file_path)
            dst_p4.run_add('-f', test_file_path)
            desc = 'manual change to fool replication script'
            dst_p4.run_submit('-d', desc)

        try:
            self.replicate_sample_dir_withdocker(depot_dir,
                                                 src_docker_cli=src_docker_cli,
                                                 dst_docker_cli=dst_docker_cli,
                                                 replicate_change_num=10)
        except ReplicationException, e:
            if 'src counter is 0(default) while last replicated rev is 10' in str(e):
                logger.info('Expected exception: %s' % str(e))
            else:
                raise
            
        try:
            self.replicate_sample_dir_withdocker(depot_dir,
                                                 src_docker_cli=src_docker_cli,
                                                 dst_docker_cli=dst_docker_cli,
                                                 src_counter=8,
                                                 replicate_change_num=10)
        except ReplicationException, e:
            if 'src counter(8) < last replicated rev(10)' in str(e):
                logger.info('Expected exception: %s' % str(e))
            else:
                raise
            
        self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli,
                                             dst_docker_cli=dst_docker_cli,
                                             src_counter=10,
                                             replicate_change_num=10)

        logger.passed(test_case)

    def test_replicate_sample_depot_specialsymbols(self):
        '''verify that file(dir) name including special symbols '% * # @'
        could also be replicated properly
        '''
        test_case = 'replicate_sample_depot_specialsymbols'

        src_docker_cli = self.docker_clients[0]
        dst_docker_cli = self.docker_clients[1]

        # create workspace
        depot_dir = '/depot/test_special_name_%s' % test_case

        with get_p4d_from_docker(src_docker_cli, depot_dir) as src_p4:
            clientspec = src_p4.fetch_client(src_p4.client)
            ws_root = clientspec._root

            # add a file with special symbols in a directory with special symbols
            special_dir_name = 'a_dir_with_%_*_#_@_in_its_name'
            special_depot_dir_name = 'a_dir_with_%25_%2A_%23_%40_in_its_name'
            test_dir = os.path.join(ws_root, special_dir_name)
            os.mkdir(test_dir)

            fn_depots = [('a_file_with_%_*_#_@_in_its_name.txt',
                          'a_file_with_%25_%2A_%23_%40_in_its_name.txt'),
                         ('another file with whitespaces.txt',
                          'another file with whitespaces.txt'),]
            for special_file_name, special_depot_file_name in fn_depots:
                test_depot_dir = os.path.join(ws_root, special_depot_dir_name)
                special_file_path = os.path.join(test_dir, special_file_name)
                special_depot_file_path = os.path.join(test_depot_dir, special_depot_file_name)
                description = 'test a file with file name %s' % special_file_name
                with open(special_file_path, 'wt') as f:
                    f.write('My name is %s!\n' % special_file_name)
                src_p4.run_add('-f', special_file_path)
                src_p4.run_submit('-d', description)

                for idx in range(2):
                    src_p4.run_edit(special_depot_file_path)
                    with open(special_file_path, 'a') as f:
                        f.write('edited %s!\n' % special_file_path)
                    desc = 'edit %s(%s) #%d' % (special_file_path,
                                                special_depot_file_path,
                                                idx)
                    src_p4.run_submit('-d', desc)

            src_p4.run_delete(special_depot_file_path)
            src_p4.run_submit('-d', 'delete special file')

        # replicate
        self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli)

        logger.passed(test_case)

    def test_replicate_sample_depot_copy_samefile(self):
        '''verify that "p4 copy //depot/file.c#3 //depot/file.c" could be
        replicated
        '''
        test_case = 'replicate_sample_depot_copy_samefile'

        depot_dir = '/depot/Misc/Artwork'
        depot_file = '//depot/Misc/Artwork/HQ.psd'
        copy_rev = 3
        src_docker_cli = self.docker_clients[0]
        dst_docker_cli = self.docker_clients[1]
        with get_p4d_from_docker(src_docker_cli, depot_dir) as src_p4:
            src_p4.run_copy('%s#%d' % (depot_file, copy_rev), depot_file)
            src_p4.run_submit('-d', 'copy %s#%d %s' % (depot_file, copy_rev,
                                                       depot_file))

        # replicate
        self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli)

        logger.passed(test_case)

    def test_replicate_sample_commit_message_reformat_review(self):
        '''verify that "#review" in commit message is changed to "# review"
        '''
        test_case = 'copy_commit_message_reformat_review'

        src_docker_cli = self.docker_clients[0]
        dst_docker_cli = self.docker_clients[1]

        src_dir = '/depot/Talkhouse/main-dev'

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

        dst_depot = self.replicate_sample_dir_withdocker(src_dir,
                                                         src_docker_cli=src_docker_cli,
                                                         dst_docker_cli=dst_docker_cli,
                                                         do_change_desc_verification=False,
                                                         obliterate=False)

        dst_dir = dst_depot[1:-4]
        with get_p4d_from_docker(dst_docker_cli, dst_dir) as p4:
            changes = p4.run_changes('-l', '...')
            last_change = changes[0]
            desc = last_change['desc']
            self.assertTrue(expected_desc in desc, desc)

        obliterate_all_depots(dst_docker_cli)

        logger.passed(test_case)

    def test_replicate_sample_integration_ignored(self):
        test_case = 'replicate_sample_integration_ignored'

        src_docker_cli = self.docker_clients['ignored-src']
        dst_docker_cli = self.docker_clients['ignored-dst']

        src_dir = '/depot/Talkhouse/main-dev'
        with get_p4d_from_docker(src_docker_cli, src_dir) as p4:
            clientspec = p4.fetch_client(p4.client)
            ws_root = clientspec._root
            test_file = os.path.join(ws_root, 'testfile')
            with open(test_file, 'wt') as fo:
                fo.write('My name is %s!\n' % test_file)
            p4.run_add('-f', test_file)
            p4.run_submit('-d', 'add test file')

            #  src should not be in //depot/Talkhouse/main-dev'
            integ_src = '//depot/Talkhouse/rel1.0/system/ide.log'

            # case 1
            p4.run_edit(test_file)
            with open(test_file, 'at') as fo:
                fo.write('editing %s!\n' % test_file)
            p4.run_integrate('-f', '-Rb', '-Rd', '%s#1' % integ_src, test_file)
            p4.run_resolve('-ay')
            p4.run_submit('-d', 'ignored integration, edit and changed')

            # case 2
            p4.run_edit(test_file)
            p4.run_integrate('-f', '-Rb', '-Rd', '%s#1' % integ_src, test_file)
            p4.run_resolve('-ay')
            p4.run_submit('-d', 'ignored integration, edit but no change')

            # case 3
            test_file1 = '%s_1' % test_file
            with open(test_file1, 'wt') as fo:
                fo.write('My name is %s!\n' % test_file1)
            p4.run_add('-f', test_file1)
            p4.run_integrate('-f', '-Rb', '-Rd', '%s#1' % integ_src, test_file)
            p4.run_resolve('-ay')
            p4.run_submit('-d', 'add another file and ignored integrate')

            #  case 4
            p4.run_integrate('-f', '-Rb', '-Rd', '%s#1' % integ_src, test_file)
            p4.run_resolve('-ay')
            p4.run_submit('-d', 'ignored integration, just integrate')

        try:
            self.replicate_sample_dir_withdocker(src_dir,
                                                 src_docker_cli=src_docker_cli,
                                                 dst_docker_cli=dst_docker_cli)
        except RepP4Exception, e:
            if '--target-empty-file' not in str(e):
                raise
        else:
            raise

    def test_replicate_sample_depot_copy_deleted_rev(self):
        '''verify that branch generated by "p4 populate -f" could be replicated.
        '''
        test_case = 'replicate_sample_depot_copy_deleted_rev'

        src_docker_cli = self.docker_clients[0]
        #dst_docker_cli = self.docker_clients[1]

        # run populate -f
        src_dir = '//depot/Jam/...'
        dst_dir = '//depot/RBG_%s/...' % test_case
        populate_rev = '326'
        with get_p4d_from_docker(src_docker_cli, '/depot') as p4:
            # changelist 326 has "delete" action
            p4.run_populate('-f', '%s@%s' % (src_dir, populate_rev), dst_dir)
        import lib.P4ReleaseBranchGenerate as p4rbg
        # use Release Branch Generation script to copy the rest changelists.
        p4_user = BUILD_TEST_P4D_USER
        ip = src_docker_cli.get_container_ip_addr()
        p4_port = '%s:1666' % ip
        p4_passwd = ''
        p4rbg.release_branch_generate(p4_port, p4_user, p4_passwd,
                                      src_dir, dst_dir)

        # replicate
        depot_dir = dst_dir[1:-4]
        self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli,
                                             do_change_desc_verification=False,
                                             do_integration_verification=False)

        logger.passed(test_case)

    def test_replicate_sample_depot_changing_exec_binary(self):
        '''verify replication of changing executable bit
        '''
        test_case = 'replicate_sample_depot_changing_exec_binary'

        depot_dir = '/depot/Misc/Artwork'
        depot_file = '//depot/Misc/Artwork/HQ.psd'
        src_docker_cli = self.docker_clients[0]
        with get_p4d_from_docker(src_docker_cli, depot_dir) as src_p4:
            clientspec = src_p4.fetch_client(src_p4.client)
            ws_root = clientspec._root
            file_path = os.path.join(ws_root, 'HQ.psd')

            src_p4.run_sync('...')
            for i in range(4):
                sign = 'binary' if i & 1 else '+x'
                src_p4.run_edit('-t', '%s' % sign, file_path)
                src_p4.run_submit('-d', '%s executable bit' % sign)

        # replicate
        self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli)

        logger.passed(test_case)

    def test_replicate_sample_depot_changing_symlink(self):
        '''verify replication of changing symlink
        '''
        test_case = 'replicate_sample_depot_changing_symlink'

        depot_dir = '/depot/Misc/Artwork'
        depot_file = '//depot/Misc/Artwork/HQ.psd'
        src_docker_cli = self.docker_clients[0]
        with get_p4d_from_docker(src_docker_cli, depot_dir) as src_p4:
            clientspec = src_p4.fetch_client(src_p4.client)
            ws_root = clientspec._root

            file_path = os.path.join(ws_root, 'HQ.psd')
            link_path = os.path.join(ws_root, 'HQ.psd_link')
            src_p4.run_sync('...')

            with open(link_path, 'wt') as f:
                f.write('text file')
            src_p4.run_add(link_path)
            src_p4.run_submit('-d', 'submit text file %s' % link_path)

            for i in range(6):
                if i & 1:
                    src_p4.run_edit('-t', 'text', link_path)
                    os.remove(link_path)
                    with open(link_path, 'wt') as f:
                        f.write('text file')
                    src_p4.run_submit('-d', 'now text file')
                else:
                    src_p4.run_edit('-t', 'symlink', link_path)
                    os.remove(link_path)
                    os.symlink(file_path, link_path)
                    src_p4.run_submit('-d', 'now symlink')

        # replicate
        self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli)

        logger.passed(test_case)


    def test_replicate_sample_depot_ignored_files(self):
        '''verify replication of .so, .a and others that could be ignored by
        SCMs by default
        '''
        test_case = 'replicate_sample_depot_ignored_files'

        depot_dir = '/depot/Misc/Artwork'
        src_docker_cli = self.docker_clients[0]
        with get_p4d_from_docker(src_docker_cli, depot_dir) as src_p4:
            clientspec = src_p4.fetch_client(src_p4.client)
            ws_root = clientspec._root

            src_p4.run_sync('...')
            ignored_suffixes = ['so', 'a', 'o', 'lo', 'la', 'al',
                                'libs', 'so.0', 'so.1', 'so.9', 'pyc',
                                'pyo', 'rej', '~', 'swp', 'DS_Store']
            test_suffixes = ignored_suffixes + ['txt']

            # add them in separate folders
            for suffix in test_suffixes:
                test_dir = os.path.join(ws_root, 'suffix_%s' % suffix)
                os.mkdir(test_dir)
                fn = os.path.join(test_dir, 'a.%s' % suffix)
                with open(fn, 'wt') as f:
                    f.write('%s' % fn)
                src_p4.run_add('-ft', 'xbinary', fn)
                src_p4.run_submit('-d', 'submit %s' % fn)

            # add them all to one folder in one change
            test_dir = os.path.join(ws_root, 'suffix_all_in_one')
            os.mkdir(test_dir)
            for suffix in test_suffixes:
                fn = os.path.join(test_dir, 'a.%s' % suffix)
                with open(fn, 'wt') as f:
                    f.write('%s' % fn)
                src_p4.run_add('-ft', 'xbinary', fn)
            src_p4.run_submit('-d', 'submit files in one change')

            txt_file = os.path.join(test_dir, 'a.txt')
            src_p4.run_edit(txt_file)
            with open(fn, 'wt') as f:
                f.write('edited %s' % fn)
            src_p4.run_submit('-d', 'submit %s' % txt_file)

        # replicaten
        self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli)

        logger.passed(test_case)

    def test_replicate_sample_depot_special_strings(self):
        test_case = 'replicate_sample_depot_special_strings'

        special_strings = {'utf-8':u"мыслю, следовательно существую., it's a smilling face, \u263A",
                           'cp1251':u"мыслю, следовательно существую., it's a smilling face'",
                           'latin1':u'La Santé',}
        depot_dir = '/depot/Misc'
        src_docker_cli = self.docker_clients[0]
        with get_p4d_from_docker(src_docker_cli, depot_dir) as src_p4:
            clientspec = src_p4.fetch_client(src_p4.client)
            ws_root = clientspec._root

            src_p4.run_sync('...')
            logger.info('src_p4.charset: %s' % src_p4.charset)

            test_dir = os.path.join(ws_root, test_case)
            os.mkdir(test_dir)
            
            import locale
            _, locale_encoding = locale.getlocale()
            special_string = special_strings.get(locale_encoding.lower())
            special_string = special_string.encode(locale_encoding)
            fn = os.path.join(test_dir, special_string + '.txt')
            with open(fn, 'wt') as f:
                f.write('added %s' % fn)
            src_p4.run_add(fn)
            src_p4.run_submit('-d', 'submit %s' % fn)

            fn = os.path.join(test_dir, 'exec_file')
            with open(fn, 'wt') as f:
                f.write('added %s' % special_string)
            src_p4.run_add('-t', '+x', fn)
            src_p4.run_submit('-d', 'submit %s' % fn)

        # replicaten
        depot_dir = os.path.join(depot_dir, test_case)
        self.replicate_sample_dir_withdocker(depot_dir,
                                             src_docker_cli=src_docker_cli)

        logger.passed(test_case)


if __name__ == '__main__':
    import unittest
    unittest.main()
