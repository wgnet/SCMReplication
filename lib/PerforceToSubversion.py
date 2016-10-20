#!/usr/bin/env python

'''Perforce to Subversion replication script.
'''


import argparse
import os
from pprint import pprint, pformat
import pysvn
import traceback
import time
from datetime import datetime
from urlparse import urlparse

from ConfigParser import ConfigParser

from buildlogger import getLogger
from buildcommon import working_in_dir, print_data, sleep_until_interrupted
from scmp4 import ReplicationP4, RepP4Exception
from scmsvn import ReplicationSvn, RepSvnException
from SvnPython import SvnPythonException
import scm2scm

from svn2p4template import (SOURCE_SECTION, TARGET_SECTION,)


class P4ToSvnException(scm2scm.ReplicationException):
    pass


class P4ToSvn(scm2scm.Replication):
    '''Perforce to Subversion replication class
    '''
    def __init__(self):
        self.parse_cli_arguments()
        self.setup_logger()

        self.create_config_parser()
        self.create_scms()

        self.svn_versioned_directories = {}

    def parse_cli_arguments(self):
        parser = argparse.ArgumentParser(description="PerforceToSubversion",
                                         epilog="Wargaming.net Sydney")

        parser.add_argument('-c', '--config', required=True,
                            help="config file for replication")
        parser.add_argument('-m', '--maximum', default=None, type=int,
                            help="maximum number of changes to transfer")
        parser.add_argument('--prefix-description-with-replication-info',
                            action='store_true',
                            help=('if set, add replication info before original'
                                  ' description. by default, after it'))
        parser.add_argument('-v', '--verbose', nargs='?',
                            const="INFO", default="INFO",
                            choices=('DEBUG', 'INFO', 'WARNING',
                                     'ERROR', 'CRITICAL'),
                            help="Various levels of debug output")
        parser.add_argument('-n', '--dry-run', action='store_true',
                            help="Preview only, no transfer")

        self.cli_arguments = parser.parse_args()
        # assure config file path
        self.cli_arguments.config = os.path.abspath(self.cli_arguments.config)

    def setup_logger(self):
        logger_name = "PerforceToSubversion"
        self.logger = getLogger(logger_name)
        self.logger.setLevel(self.cli_arguments.verbose)

    def create_config_parser(self):
        self.cfg_parser = ConfigParser()
        self.cfg_parser.readfp(open(self.cli_arguments.config))

    def verify_work_dir_root(self):
        '''Verify Svn working copy dir is the same as the p4 workspace
        '''
        p4_ws_root = self.source.get_root_folder()
        svn_wc_root = self.target.get_root_folder()
        if p4_ws_root != svn_wc_root:
            err_msg = 'Svn Root Folder and P4 Root Folder must be the same.'
            err_msg += '%s != %s' % (svn_wc_root, p4_ws_root)
            raise P4ToSvnException(err_msg)

    def create_scms(self):
        '''Read configure file and configure src/target SCMs
        '''
        self.source = ReplicationP4(SOURCE_SECTION,
                                    self.cfg_parser,
                                    self.cli_arguments,
                                    self.cli_arguments.verbose)
        self.target = ReplicationSvn(TARGET_SECTION,
                                     self.cfg_parser,
                                     self.cli_arguments,
                                     self.cli_arguments.verbose)

        self.source.connect()
        self.target.connect()
        self.verify_work_dir_root()

        # Record the Players
        self.logger.info(self.source)
        self.logger.info(self.target)

    def _file_is_svn_tracked(self, file_path):
        try:
            file_info = self.target.svn.run_info(file_path)

            if file_info is None:
                return False
        except pysvn.ClientError:
            return False
        return True

    def _svn_path_to_url(self, file_path):
        svn_wc_root = self.target.get_root_folder()
        svn_proj_repos = self.target.SVN_REPO_URL + self.target.SVN_PROJECT_DIR

        if not file_path.startswith(svn_wc_root):
            raise P4ToSvnException('%s not in %s' % (file_path, svn_wc_root))

        rel_path = file_path[len(svn_wc_root):]
        file_url = '%s%s' % (svn_proj_repos, rel_path)

        return file_url

    def _file_is_svn_versioned(self, file_path):
        #if file_path in self.svn_versioned_directories:
        #    return self.svn_versioned_directories[file_path]

        file_url = self._svn_path_to_url(file_path)

        file_info = None
        try:
            file_info = self.target.svn.run_info2(file_url)
        except pysvn.ClientError, e:
            pass

        is_versioned = file_info is not None
        self.svn_versioned_directories[file_path] = is_versioned

        return is_versioned

    def svn_replicate_add(self, files_to_add, p4_rev):
        '''deal with addition of files
        '''
        if not files_to_add:
            return []
        paths_to_add = [cf.localFile for cf in files_to_add]
        local_files_to_add = [cf.fixedLocalFile for cf in files_to_add]
        add_file_splits = [(os.path.split(fn)[0], fn)
                           for fn in local_files_to_add]
        files_to_submit = []

        add_dir_files = {}
        for d, f in add_file_splits:
            files_list = add_dir_files.get(d, [])
            files_list.append(f)
            add_dir_files[d] = files_list

        # directories that need svn update
        # p4 sync
        # files/directories for svn add
        paths_to_update = set()
        paths_to_submit = set()
        local_dir_files = dict(add_dir_files)
        self.logger.debug('%s # of dirs to detect: %s' % ('*'*80,
                                                          len(local_dir_files)))
        for local_dir, local_files in local_dir_files.items():
            svn_versioned_dir = local_dir
            last_not_versioned = local_files

            while svn_versioned_dir != '/':
                msg = 'svn_versioned_dir/last_not_versioned: %s, %s' % (svn_versioned_dir,
                                                                        last_not_versioned)
                self.logger.debug(msg)
                if svn_versioned_dir in paths_to_update:
                    msg = '%s in paths_to_update' % svn_versioned_dir
                    self.logger.debug(msg)
                    paths_to_submit.update(last_not_versioned)
                    break
                if any([svn_versioned_dir.startswith(d+'/') for d in paths_to_submit]):
                    msg = '%s startswith d in paths_to_submit' % svn_versioned_dir
                    self.logger.debug(msg)
                    break
                elif self._file_is_svn_versioned(svn_versioned_dir):
                    paths_to_update.add(svn_versioned_dir)
                    paths_to_submit.update(last_not_versioned)
                    break
                else:
                    last_not_versioned = set([svn_versioned_dir])
                    svn_versioned_dir = os.path.split(svn_versioned_dir)[0]

        # if svn-versioned parent doesnot exist, svn-update it.
        if paths_to_update:
            additional_upd_arg = '--set-depth empty'
            try:
                paths_upd = list(paths_to_update)
                paths_upd = [p for p in paths_upd if not os.path.isdir(p)]
                if paths_upd:
                    self.target.svn.run_update(paths_upd,
                                               update_arg=additional_upd_arg)
            except Exception, e:
                pass

        self.logger.debug('local_files_to_add: %s' % local_files_to_add)
        self.logger.debug('paths_to_update: %s' % paths_to_update)
        self.logger.debug('paths_to_submit: %s' % paths_to_submit)

        self.p4_sync_files(paths_to_add, p4_rev)
        self.svn_add_files(list(paths_to_submit))

        return list(paths_to_submit)

    def svn_replicate_action_edit(self, cf):
        file_path = cf.fixedLocalFile

        file_executable_in_fs = os.access(file_path, os.X_OK)
        prop_executable = self.target.svn.run_propget('svn:executable', file_path)
        file_executable_in_svn = '*' == prop_executable.get(file_path)
        if file_executable_in_fs != file_executable_in_svn:
            if file_executable_in_fs:
		self.target.svn.run_propset('svn:executable', '*', file_path)
            else:
                self.target.svn.run_propdel('svn:executable', file_path)

        file_symlink_in_fs = os.path.islink(file_path)
        prop_special = self.target.svn.run_propget('svn:special', file_path)
        file_symlink_in_svn = '*' == prop_special.get(file_path)
        if file_symlink_in_fs != file_symlink_in_svn:
            if file_symlink_in_fs:
                self.target.svn.run_propset('svn:special', '*', file_path)
            else:
                self.target.svn.run_propdel('svn:special', file_path)

        return [file_path]

    def p4_sync_files(self, list_of_files, rev):
        if not list_of_files:
            return

        num_of_files = len(list_of_files)

        gs = 500
        for idx in range(gs, num_of_files + gs, gs):
            files_group = list_of_files[idx-gs:idx]
            sync_args = ['-f']
            sync_args.extend(['%s@%s' % (fn, rev) for fn in files_group])
            self.source.p4.run_sync(*sync_args)

    def svn_add_files(self, list_of_files):
        if not list_of_files:
            return

        num_of_files = len(list_of_files)

        gs = 500
        for idx in range(gs, num_of_files + gs, gs):
            files_group = list_of_files[idx-gs:idx]
            self.target.svn.run_add(files_group, ignore=False)

    def svn_update_files(self, list_of_files, update_arg=None):
        if not list_of_files:
            return

        num_of_files = len(list_of_files)

        t0 = datetime.now()
        gs = 500
        for idx in range(gs, num_of_files + gs, gs):
            files_group = list_of_files[idx-gs:idx]
            self.target.update_changed_files(files_group, 'HEAD',
                                             update_arg=update_arg)
        t1 = datetime.now()
        self.logger.debug('%s spent %s updating %s files' % ('#'*30,
                                                             t1-t0,
                                                             num_of_files))

    def svn_replicate_delete(self, files_to_del, files_to_add):
        '''svn remove files that were deleted in p4, and their parent
        directories if empty.

        @param files_to_del list of p4 ChangeRevisions
        @param files_to_add list of p4 ChangeRevisions
        '''
        local_files_to_del = [cf.fixedLocalFile for cf in files_to_del]
        del_file_splits = [(os.path.split(fn)[0], fn) for fn in local_files_to_del]
        files_to_submit = []

        del_dir_files = {}
        for d, f in del_file_splits:
            files_list = del_dir_files.get(d, [])
            files_list.append(f)
            del_dir_files[d] = files_list

        local_files_to_add = [cf.fixedLocalFile for cf in files_to_add]
        dirs_with_add = [os.path.split(fn)[0] for fn in local_files_to_add]

        self.logger.debug('del_dir_files: %s' % pformat(del_dir_files))
        recursive_detect_empty_dir = True
        svn_file_list = {}
        while recursive_detect_empty_dir:
            recursive_detect_empty_dir = False

            svn_proj_repos = self.target.SVN_PROJECT_DIR
            def is_dir_deleted(local_dir, local_files):
                dir_url = self._svn_path_to_url(local_dir)
                file_urls = [self._svn_path_to_url(fn) for fn in local_files]

                list_of_dir = svn_file_list.get(dir_url)
                if not list_of_dir:
                    list_of_dir = self.target.svn.run_list(dir_url)
                    svn_file_list[dir_url] = list_of_dir

                repos_path_in_srv = [urlparse(l[0].path).path for l in list_of_dir]
                removed_file_repos_paths = [urlparse(fu).path for fu in file_urls]

                set_repos_path = set(repos_path_in_srv)
                dir_repos_path = urlparse(dir_url).path
                set_removed_paths = set(removed_file_repos_paths + [dir_repos_path])

                all_deleted = set_repos_path == set_removed_paths
                no_added = all([not ad.startswith(local_dir + '/') and
                                ad != local_dir
                                for ad in dirs_with_add])

                dir_deleted = all_deleted and no_added
                if dir_deleted:
                    self.logger.debug('local_dir %s not in %s' % (local_dir, dirs_with_add))
                    self.logger.debug('set_repos_path: %s' % set_repos_path)
                return dir_deleted

            local_dir_files = dict(del_dir_files)
            for local_dir, local_files in local_dir_files.items():
                if is_dir_deleted(local_dir, local_files):
                    self.logger.debug('deleting %s' % local_dir)
                    parent_dir, dir_name = os.path.split(local_dir)[0], local_dir
                    del del_dir_files[local_dir]
                    parent_dir_files = del_dir_files.get(parent_dir, [])
                    parent_dir_files.append(dir_name)
                    del_dir_files[parent_dir] = parent_dir_files
                    recursive_detect_empty_dir = True

        self.logger.debug('del_dir_files after empty dir detection: %s' % pformat(del_dir_files))
        for local_dir, local_files in del_dir_files.items():
            for lf in local_files:
                self.target.svn.run_update(lf)
                self.target.svn.run_remove(lf)
                files_to_submit.append(lf)

                if lf in self.svn_versioned_directories:
                    del self.svn_versioned_directories[lf]

        return files_to_submit

    def svn_replicate_change(self, p4_change, change_files):

        '''
        self.logger.error('wc status')
        wc_status = self.target.svn.run_status(self.target.get_root_folder())
        if wc_status:
            for fs in wc_status:
                print_data('status', fs)
        '''
        acts_update_in_advance = ('edit', 'integrate', 'delete', 'move/delete')

        fixed_files_to_upd_in_advance = [cf.fixedLocalFile for cf in change_files
                                         if cf.action in acts_update_in_advance]
        files_to_upd_in_advance = [cf.localFile for cf in change_files
                                   if cf.action in acts_update_in_advance]

        p4_rev = p4_change.get('change')
        self.svn_update_files(fixed_files_to_upd_in_advance)
        self.p4_sync_files(files_to_upd_in_advance, p4_rev)

        '''
        dirs_to_upd = set([os.path.split(fn)[0]
                           for fn in fixed_files_to_upd_in_advance])
        self.target.update_changed_files(dirs_to_upd, 'HEAD',
                                         update_arg='--set-depth empty')
        self.p4_sync_files(files_to_upd_in_advance, p4_rev)
        self.svn_add_files(fixed_files_to_upd_in_advance)
        self.svn_update_files(fixed_files_to_upd_in_advance,
                              update_arg='--accept mf')
        '''

        files_to_delete = [cf for cf in change_files
                           if cf.action in ['delete', 'move/delete',]]
        files_to_add = [cf for cf in change_files
                           if cf.action in ['add', 'branch', 'move/add',]]
        change_files_non_del = [cf for cf in change_files
                                if cf not in files_to_delete]

        files_to_submit = self.svn_replicate_delete(files_to_delete,
                                                    files_to_add)

        files_to_submit += self.svn_replicate_add(files_to_add, p4_rev)

        #files_to_submit = []
        for cf in change_files_non_del:
            tracked_path = None

            self.logger.info('replicating %s' % pformat(cf))

            if cf.action in ['add', 'branch', 'move/add']:
                pass
            elif cf.action in ['edit', 'integrate']:
                tracked_path = self.svn_replicate_action_edit(cf)
            elif cf.action in ['delete', 'move/delete']:
                pass
            else:
                self.logger.error(pformat(change_files))
                msg = 'unsupported action: %s' % cf.action
                raise NotImplementedError(msg)

            if tracked_path:
                files_to_submit.extend(tracked_path)

        orig_submitter = p4_change.get('user')
        orig_submit_time = p4_change.get('time')
        orig_desc = p4_change.get('desc')
        orig_rev = p4_change.get('change')
        orig_srv = self.source.P4PORT

        self.logger.debug('files_to_submit: %s' % files_to_submit)
        new_rev = self.target.submit_opened_files(files_to_submit,
                                                  orig_desc, orig_rev,
                                                  orig_srv,
                                                  orig_submitter,
                                                  orig_submit_time)
        return new_rev

    def replicate(self):
        self.calc_start_changelist()

        self.target.svn_checkout_workingcopy()
        p4_changes = self.source.get_changes_to_replicate()

        p4_change_nums = [p['change'] for p in p4_changes]
        self.logger.info('Changes to replicate: %s' % p4_change_nums)

        if self.cli_arguments.dry_run:
            self.target.disconnect()
            return p4_change_nums

        try:
            num_revisions_to_rep = len(p4_changes)
            for idx, p4_change in enumerate(p4_changes):
                p4_revision = p4_change['change']
                self.logger.info('replicating %s' % p4_revision)

                change_files = self.source.get_change(p4_revision)
                svn_revision = self.svn_replicate_change(p4_change, change_files)

                self.logger.info('Replicated : %s -> %s, %d of %d' % (
                    p4_revision, svn_revision, idx+1, num_revisions_to_rep))
        except (P4ToSvnException, RepP4Exception, RepSvnException) as e:
            self.logger.error(e)
            self.logger.error(traceback.format_exc())
            raise e
        except Exception, e:
            self.logger.error(e)
            self.logger.error(traceback.format_exc())
            raise e
        finally:
            self.target.disconnect()


def PerforceToSubversion():
    p4_to_svn = P4ToSvn()

    with working_in_dir(p4_to_svn.source.get_root_folder()):
        return p4_to_svn.replicate()

