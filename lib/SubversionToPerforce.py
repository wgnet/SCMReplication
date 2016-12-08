#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''Svn to p4 replication script

This script will do an SVN update and submit the changes to perforce
run this script from your working directory

'''

import argparse
import os
import shutil
import stat
import traceback

from ConfigParser import ConfigParser

from buildlogger import getLogger
from buildcommon import (working_in_dir, remove_dir_contents,
                         sleep_until_interrupted)
from scmp4 import ReplicationP4, ChangeRevision, RepP4Exception
from scmsvn import ReplicationSvn, RepSvnException
import scm2scm

from svn2p4template import (SOURCE_SECTION,
                            TARGET_SECTION,
                            writeTemplateConfig)


class SvnToP4Exception(scm2scm.ReplicationException):
    pass


class SvnToP4(scm2scm.Replication):
    '''Subversion to perforce replication class
    '''
    def __init__(self):
        self.parse_cli_arguments()
        self.setup_logger()

        self.create_config_parser()
        self.create_scms()

        # default svn to p4 replication info format
        rep_info_formatter = (
            'Imported from {srcserver}\n'
            'r{revision}|{submitter}|{submittime}')
        rep_info_extracter = (
            'Imported from (?P<srcserver>.+)\n'
            'r(?P<revision>[0-9]+)\|(?P<submitter>.+)\|(?P<submittime>.+)')
        self.target.set_desc_rep_info_pattern(rep_info_formatter,
                                              rep_info_extracter)

    def parse_cli_arguments(self):
        cli_parser = argparse.ArgumentParser(
            description="SubversionToPerforce",
            epilog="Copyright (C) 2015 CTG Austin, Wargaming.net"
        )

        cli_parser.add_argument('-c', '--config', required=True,
                                help="Use --template-config to create a sample config")
        cli_parser.add_argument('-m', '--maximum', default=None, type=int,
                                help="maximum number of changes to transfer")
        cli_parser.add_argument('-v', '--verbose', nargs='?',
                                const="INFO", default="INFO",
                                choices=('DEBUG', 'INFO', 'WARNING',
                                         'ERROR', 'CRITICAL'),
                                help="Various levels of debug output")
        cli_parser.add_argument('--prefix-description-with-replication-info',
                                action='store_true',
                                help=('if set, add replication info before original'
                                      ' description. by default, after it'))
        cli_parser.add_argument('--template-config', action='store_true',
                                help="Write a template config file and exit")
        cli_parser.add_argument('-n', '--dry-run', action='store_true',
                                help="Preview only, no transfer")
        cli_parser.add_argument('--svn-ignore-externals', action='store_true',
                                help="ignore externals when svn-updating")
        cli_parser.add_argument('--replicate-user-and-timestamp',
                                action='store_true',
                                help=('Enable replication of user and timestamp '
                                'of source changelist. NOTE! needs "admin" '
                                'access for this operation'))

        self.cli_arguments = cli_parser.parse_args()
        # assure config file path
        self.cli_arguments.config = os.path.abspath(self.cli_arguments.config)

    def setup_logger(self):
        logger_name = "SubversionToPerforce"
        self.logger = getLogger(logger_name)
        self.logger.setLevel(self.cli_arguments.verbose)

    def create_config_parser(self):
        self.cfg_parser = ConfigParser()
        self.cfg_parser.readfp(open(self.cli_arguments.config))

    def create_scms(self):
        '''Read configure file and configure src/target SCMs
        '''
        self.source = ReplicationSvn(SOURCE_SECTION,
                                     self.cfg_parser,
                                     self.cli_arguments,
                                     self.cli_arguments.verbose)
        self.target = ReplicationP4(TARGET_SECTION,
                                    self.cfg_parser,
                                    self.cli_arguments,
                                    self.cli_arguments.verbose)

        self.source.connect()
        self.target.connect()
        self.verify_work_dir_root()

        # Record the Players
        self.logger.info(self.source)
        self.logger.info(self.target)

    def decode_revision(self, svnChange):
        return svnChange['action'], svnChange['path']

    def p4_process_action_add(self, file_path):
        file_abspath, file_p4fixed = file_path
        p4 = self.target.p4

        def p4_run_add(file_path_to_add):
            result = p4.run_add('-f', file_path_to_add)
            err_msg = 'already opened for delete'
            if any([err_msg in l for l in result]):
                ascii_filename = ChangeRevision.convert_p4wildcard_to_ascii(file_path_to_add)
                p4.run_revert('-k', ascii_filename)
                p4.run_edit('-k', ascii_filename)

        # check directory
        if os.path.isdir(file_abspath):
            # Could be a 'branch' action
            for walk_root, dirs, names in os.walk(file_abspath):
                dirs[:] = [d for d in dirs if d != '.svn']

                for name in names:
                    file_in_dir = os.path.join(walk_root, name)
                    p4_run_add(file_in_dir)
        elif os.path.isfile(file_abspath) or os.path.islink(file_abspath):
            p4_run_add(file_abspath)
        else:
            self.logger.error('%s doesnot exist' % file_abspath)

    def p4_edit_file(self, file_path):
        file_abspath, file_p4fixed = file_path
        p4cfg = self.target
        p4 = p4cfg.p4
        p4.run_sync('-k', file_p4fixed)

        f_st = os.lstat(file_abspath)
        is_executable = f_st.st_mode & (stat.S_IXGRP | stat.S_IXUSR)
        is_symlink = os.path.islink(file_abspath)
        if is_symlink:
            output = p4.run_edit('-t', 'symlink', file_p4fixed)
        elif is_executable:
            output = p4.run_edit('-t', '+x', file_p4fixed)
        else:
            output = p4.run_edit('-t', 'auto', file_p4fixed)

        # If the initial 'add' change was lost
        # an edit on a missing file will report
        # an error 'not on client'
        if p4cfg.inWarnings('not on client'):
            msg = '%s not on client. Changing P4 Edit to P4 Add' % file_abspath
            self.logger.warning(msg)

            output = p4.run_add('-f', file_abspath)

    def p4_process_action_mod(self, file_path):
        file_abspath, file_p4fixed = file_path

        # check directory
        if self.target.is_p4_directory(file_p4fixed):
            return
        elif os.path.isdir(file_abspath):
            msg = '"M" %s, directory not tracked by p4.' % file_abspath
            self.logger.warning(msg)
        else:
            self.p4_edit_file(file_path)

    def p4_process_action_del(self, file_path):
        file_abspath, file_p4fixed = file_path
        p4cfg = self.target
        p4 = p4cfg.p4

        # check directory
        if self.target.is_p4_directory(file_p4fixed):
            file_p4fixed += '/...'
            output = p4.run_sync('-f', file_p4fixed)
            output = p4.run_delete(file_p4fixed)
            shutil.rmtree(file_abspath)
        elif os.path.isdir(file_abspath):
            msg = '"D" %s, directory not tracked by p4.' % file_abspath
            self.logger.warning(msg)
        else:
            output = p4.run_delete('-v', file_p4fixed)

    def p4_process_action_rep(self, file_path):
        file_abspath, file_p4fixed = file_path
        p4cfg = self.target
        p4 = p4cfg.p4

        if self.target.is_p4_directory(file_p4fixed):
            '''AFAIK if a directory is replaced, there are two situations:
            1) it's replaced with an empty dir
               svn log has only 1 message for this directory,
               which is "R path/of/target/dir"
            2) it's replaced with a dir with other files
                svn log would give extra entries for the files.
            either case, we can simply delete this directory.
            '''
            tmp_dir = file_p4fixed + '_copied_tmp'
            shutil.move(file_p4fixed, tmp_dir)

            p4.run_sync('-f', file_p4fixed + '/...')
            p4.run_delete(file_p4fixed + '/...')
            shutil.rmtree(file_p4fixed)
            shutil.move(tmp_dir, file_p4fixed)
        elif os.path.isdir(file_abspath):
            msg = '"R" %s, directory not tracked by p4!' % file_abspath
            self.logger.warning(msg)
        else:
            self.p4_edit_file(file_path)

    def p4_replicate_change(self, svn_rev_log):
        '''submit svn changes to perforce

        @param svn_rev_log svn_log output
        '''
        changed_paths = svn_rev_log['changed_paths']
        rev_num = svn_rev_log['revision'].number

        self.logger.info('Replicating %d to p4' % rev_num)

        # parse the changeList and submit it to perforce
        if not changed_paths:
            msg = 'Svn revision %d has no changed path' % rev_num
            self.logger.warning(msg)
            return

        changed_paths = sorted(changed_paths,
                               key=lambda cp: 0 if self.decode_revision(cp)[0] == 'R' else 1)
        for changed_path in changed_paths:
            action, file_abspath = self.decode_revision(changed_path)

            if not self.target.file_in_workspace(file_abspath):
                continue

            file_p4fixed = ChangeRevision.convert_p4wildcard_to_ascii(file_abspath)

            self.logger.debug('%s %s' % (action, file_abspath))
            file_path = (file_abspath, file_p4fixed)
            
            if action == 'A':
                self.p4_process_action_add(file_path)
            elif action == 'M':
                self.p4_process_action_mod(file_path)
            elif action == 'R':
                self.p4_process_action_rep(file_path)
            elif action == 'D':
                self.p4_process_action_del(file_path)
            else:
                err_msg = 'unknown action %s for %s' % (action, file_abspath)
                raise SvnToP4Exception(err_msg)

            self.target.checkWarnings(action)
            self.target.checkErrors(action)

        # submit change to p4
        desc = self.source.get_commit_msg(svn_rev_log)
        src_rev = svn_rev_log['revision'].number
        src_srv = self.source.SVN_REPO_LABEL
        orig_user = svn_rev_log.get('author', 'guest')
        orig_date = svn_rev_log.get('date')
        p4_change_num = self.target.submit_opened_files(desc, src_rev,
                                                        src_srv,
                                                        orig_user,
                                                        orig_date)

        if not p4_change_num:
            return

        if self.cli_arguments.replicate_user_and_timestamp:
            self.target.update_change(p4_change_num, orig_user, orig_date)

        return p4_change_num

    def verify_work_dir_root(self):
        '''Verify Svn working copy dir is the same as the p4 workspace
        '''
        svn_wc_root = self.source.get_root_folder()
        p4_ws_root = self.target.get_root_folder()
        if p4_ws_root != svn_wc_root:
            err_msg = 'Svn Root Folder and P4 Root Folder must be the same.'
            err_msg += '%s != %s' % (svn_wc_root, p4_ws_root)
            raise SvnToP4Exception(err_msg)

    def replication_sanity_check(self, svn_rev_log):
        '''Sanity check after replication of each commit.

        on-the-fly checksum comparision between svn revision and new
        p4d revision. If anything insane detected, we stop the
        replication.

        TODO: We cannot yet get checksum from calling svn.info2()

        '''
        raise NotImplementedError()

        def get_changed_paths(svn_changed_paths):
            changed_paths = []
            for cp in svn_changed_paths:
                action, path = self.decode_revision(cp)
                if action == 'D':
                    continue
                changed_paths.append(path)
            return changed_paths

        changed_paths = svn_rev_log['changed_paths']
        changed_paths = self.get_changed_paths(changed_paths)

        rev_num = svn_rev_log['revision'].number

        self.logger.info('sanity check %d' % rev_num)

        # parse the changeList and submit it to perforce
        if not changed_paths:
            return

        # no wc_info in info
        #infos = self.source.svn.run_info2(changed_paths)

    def replicate(self):
        self.calc_start_changelist()
        svn_revs = self.source.get_changes_to_replicate()

        self.logger.info('Changes to replicate: %s' % svn_revs)

        if self.cli_arguments.dry_run:
            self.source.disconnect()
            return svn_revs

        try:
            num_revisions_to_rep = len(svn_revs)
            for idx, rev_num in enumerate(svn_revs):
                self.logger.info('replicating %d' % rev_num)
                svn_rev_log = self.source.update_to_revision(rev_num)

                p4_change = self.p4_replicate_change(svn_rev_log)

                self.logger.info('Replicated : %d -> %s, %d of %d' % (
                    rev_num, p4_change, idx+1, num_revisions_to_rep))

                self.source.cleanup_externals()
        except (SvnToP4Exception, RepP4Exception, RepSvnException) as e:
            self.logger.error(e)
            self.logger.error(traceback.format_exc())
            raise
        finally:
            self.source.disconnect()
            self.target.revertChanges()

        return svn_revs

def SubversionToPerforce():
    svntop4 = SvnToP4()

    if svntop4.cli_arguments.template_config:
        writeTemplateConfig()
        return

    with working_in_dir(svntop4.source.get_root_folder()):
        return svntop4.replicate()

if __name__ == "__main__":
    SubversionToPerforce()

