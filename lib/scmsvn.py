#!/usr/bin/python3
# -*- coding: utf-8 -*-

'''Replication svn implementation

https://confluence.wargaming.net/display/WA/3.1.2+WGRepo+-+SVN+Publishing+Tool
'''

import os
import _pickle as pickle
import re
import sys
import shlex
import shutil
from urllib.parse import urlparse, urljoin, urlunparse
from pprint import pprint, pformat

import pysvn

from .buildlogger import getLogger
from .buildcommon import get_common_stem, print_data, generate_random_str, working_in_dir
from .SvnPython import SvnPython, SvnPythonException
from .scmrep import ReplicationSCM, ReplicationException

from P4 import Map as P4Map


class RepSvnException(ReplicationException):
    pass


class ReplicationSvn(ReplicationSCM):
    def __init__(self, section, cfg_parser, cli_arguments, verbose='DEBUG'):
        self.option_properties = [
            #(property_name, is_optional)
            ('SVN_REPO_LABEL', False),
            ('SVN_PROJECT_DIR', False),
            ('SVN_CLIENT_ROOT', False),
            ('COUNTER', True),
            ('ENDCHANGE', True),
            ('SVN_USER', True),
            ('SVN_PASSWD', True),
            ('SVN_REPO_URL', True),
            ('SVN_VIEW_MAPPING', True), ]

        super(ReplicationSvn, self).__init__(section, cfg_parser)

        self.svn = None
        self.section = section
        self.counter = 0
        if self.COUNTER:
            self.counter = int(self.COUNTER)

        self.cli_arguments = cli_arguments
        self.logger = getLogger(self.SVN_REPO_LABEL)
        self.logger.setLevel(verbose)

        self._create_exclude_view_map()

    def _create_exclude_view_map(self):
        self.view_map = None
        if not hasattr(self, 'SVN_VIEW_MAPPING') or not self.SVN_VIEW_MAPPING:
            return

        with open(self.SVN_VIEW_MAPPING, 'rt') as f:
            view_mapping = list(f)
        self.replicate_view_mapping = [l.strip() for l in view_mapping]

        self.additional_dirs = []

        svn_root = self.SVN_CLIENT_ROOT
        mapping_str = [
            '/%s/...  %s/...' %
            (self.replicate_view_mapping[0], svn_root)]
        for m in self.replicate_view_mapping[1:]:
            if m.endswith('/'):
                m = m[:-1]

            if m.startswith('-/') or m.startswith('+/'):
                m_sign = m[0]
                m_path = m[1:]
                if m_sign == '+':
                    self.additional_dirs.append(m_path)

                leave_dir = os.path.split(m)[1]
                random_str = generate_random_str(10)
                exc_dir = '%s/%s  %s/%s_dir_%s' % (m_sign, m_path, svn_root,
                                                   random_str, leave_dir)
                exc_files = '%s/%s/...  %s/%s_file_%s/...' % (m_sign, m_path,
                                                              svn_root,
                                                              random_str,
                                                              leave_dir)
                mapping_str.extend([exc_dir, exc_files])
            else:
                msg = '"%s" not supported in svn view mapping' % m
                raise RepSvnException(msg)

        self.logger.info('svn view mapping: %s' % mapping_str)
        self.view_map = P4Map(mapping_str)

    def __str__(self):
        return '[%s SVN_REPO = %s COUNTER = %s]' % (
            self.section, self.SVN_REPO_LABEL, self.COUNTER)

    def get_root_folder(self):
        return self.SVN_CLIENT_ROOT

    def _verify_root_folder(self):
        wc_root = self.get_root_folder()

        if not wc_root:
            raise RepSvnException('svn working copy root not configured')

        wc_root_abs = os.path.abspath(wc_root)
        if not os.path.isdir(wc_root_abs):
            msg = '%s does not exist or is not directory.' % wc_root_abs
            raise RepSvnException(msg)

        svnFile = os.path.join(wc_root_abs, '.svn')
        if not os.path.isdir(svnFile):
            msg = '%s has no svn working copy. No .svn dir.' % wc_root_abs
            raise RepSvnException(msg)

    def connect(self):
        '''Create svn instance
        '''
        # self._verify_root_folder()
        self.svn = SvnPython(self.SVN_REPO_URL,
                             self.SVN_USER,
                             self.SVN_PASSWD,
                             self.get_root_folder())

    def disconnect(self):
        '''Create svn instance
        '''
        self.svn.client = None

    def get_changes_to_replicate(self):
        """end_change, int, last changelist to be replicated
        """
        svn_revs = self.get_revision_numbers(self.counter)
        if svn_revs and self.counter == svn_revs[0]:
            svn_revs = svn_revs[1:]

        if self.cli_arguments.maximum:
            svn_revs = svn_revs[:self.cli_arguments.maximum]

        if self.ENDCHANGE:
            last_changeset = int(self.ENDCHANGE)
            if last_changeset in svn_revs:
                idx_of_last_changeset = svn_revs.index(last_changeset)
                # +1 for inclusive
                svn_revs = svn_revs[:idx_of_last_changeset + 1]
            else:
                err_msg = '%d not in svn revisions: %s' % (last_changeset,
                                                           svn_revs)
                raise RepSvnException(err_msg)

        return svn_revs

    def get_commit_message_of_rev(self, rev='head', num_of_rev=1):
        if rev == 'head':
            # if rev is None, run_log will assume end_rev is 'head'
            rev = None

        project_dir = self.SVN_PROJECT_DIR
        repo_url = self.SVN_REPO_URL
        try:
            rev_logs = self.svn.run_log(repo_url + project_dir,
                                        end_rev=rev,
                                        limit=num_of_rev)
        except pysvn.ClientError as e:
            if 'File not found' in str(e):
                return []
            raise

        messages = [l['message'] for l in rev_logs]

        return messages

    def get_revision_numbers(self, start_rev):
        '''Get list of revisions starting from start_rev

        @param start_rev integer of starting revision
        @return list of assending revisions of svn root directory
                starting from start_rev
        '''
        revs = self.svn.get_revision_list(self.SVN_PROJECT_DIR,
                                          start_rev=start_rev)
        return revs

    def verify_svn_update(self, changed_abspaths):
        '''verify if all files in changed_abspaths have been updated

        @param changed_abspaths list of svn_change
        '''
        full_files_to_update = [p.path for p in changed_abspaths]

        # Verify updates, files should be updated or raise an exception
        for cp in changed_abspaths:
            f = cp.path
            if os.path.isfile(f) or os.path.islink(f) or os.path.isdir(f):
                continue

            if cp['action'] != 'D' and not cp.get('externals'):
                raise RepSvnException('%s is not updated properly' % f)

    def get_files_to_add(self, changed_abspaths):
        files_to_add = [p['path'] for p in changed_abspaths
                        if p['action'] == 'A']

        if len(files_to_add) > 1000:
            wc_root = self.get_root_folder()
            stem_files_to_add = get_common_stem(files_to_add, wc_root)
            self.logger.info('%s, %s' % (wc_root, stem_files_to_add))
            files_to_add = stem_files_to_add

        # remove directories cannot simply remove directories, need to
        # detect "svn:externals" before removing "added" directory.
        '''
        files_to_add_sorted = sorted(files_to_add, key=len)
        dirs_to_add = []
        for f2a in files_to_add_sorted:
            if any([f.startswith(f2a + '/') for f in files_to_add_sorted]):
                files_to_add.remove(f2a)
                continue
        '''
        return files_to_add

    def get_files_to_del(self, changed_abspaths):
        files_to_del = [p['path'] for p in changed_abspaths
                        if p['action'] == 'D']

        return files_to_del

    def get_files_to_rep(self, changed_abspaths):
        files_to_rep = [p['path'] for p in changed_abspaths
                        if p['action'] == 'R']
        return files_to_rep

    def get_external_dir(self, external_prop, mod_dir):
        '''
        http://svnbook.red-bean.com/en/1.7/svn.advanced.externals.html
        '''
        def is_url(cfg_path):
            has_scheme = urlparse(cfg_path).scheme is not ''
            return has_scheme

        externals = []

        if not external_prop:
            return externals

        repo_url = self.SVN_REPO_URL
        project_dir = self.SVN_PROJECT_DIR
        project_url = os.path.join(repo_url, project_dir[1:])
        mod_dir_rel = mod_dir[len(self.get_root_folder()) + 1:]
        parent_url = os.path.join(project_url, mod_dir_rel)

        for external_prop_line in external_prop.strip().split('\n'):
            src_url = src_rev = dst_dir = None

            external_config_paths = shlex.split(external_prop_line)
            for ext_cfg_path in external_config_paths:
                if is_url(ext_cfg_path):
                    src_url = ext_cfg_path
                    continue

                external_prefixes = ['../', '^/', '/', '//']
                if any([ext_cfg_path.startswith(ext_prefix)
                        for ext_prefix in external_prefixes]):
                    if ext_cfg_path.startswith('../'):
                        src_url = os.path.join(parent_url, ext_cfg_path)
                        src_url_parse = list(urlparse(src_url))
                        src_url_parse[2] = os.path.normpath(src_url_parse[2])
                        src_url = urlunparse(src_url_parse)

                    if ext_cfg_path.startswith('^/'):
                        src_url = os.path.join(repo_url, ext_cfg_path[2:])
                        src_url_parse = list(urlparse(src_url))
                        src_url_parse[2] = os.path.normpath(src_url_parse[2])
                        src_url = urlunparse(src_url_parse)

                    if ext_cfg_path.startswith('//'):
                        msg = 'svn external starting with "//", not yet supported'
                        raise RepSvnException(msg)

                    if ext_cfg_path.startswith('/'):
                        repo_url_parse = list(urlparse(repo_url))
                        repo_url_parse[2] = ext_cfg_path
                        src_url = urlunparse(repo_url_parse)

                    continue

                if ext_cfg_path.startswith('-r'):
                    self.logger.warning('%s is external' % ext_cfg_path)
                    src_rev = ext_cfg_path[2:]

                    #msg = 'svn external revision %s, not yet supported' % src_rev
                    #raise RepSvnException(msg)

                    continue

                dst_dir = os.path.join(mod_dir, ext_cfg_path)

            peg_rev = None
            if '@' in src_url and src_url[-1] != '@':
                src_url, peg_rev = src_url.split('@')
            externals.append((src_url, peg_rev, src_rev, dst_dir))

        return externals

    def checkout_externals(self, ext_url, peg_rev, rev, abs_todir, **kwargs):
        '''checkout svn:externals,
        '''
        result = False
        # checkout external
        try:
            url = ext_url
            if peg_rev:
                url += '@%s' % peg_rev

            depth = '--depth infinity'
            if kwargs.get('depth'):
                depth = '--depth %s' % kwargs.get('depth')

            cmd_args = "%s %s '%s'" % (depth, url, abs_todir)

            if rev:
                cmd_args = '-r %s %s' % (rev, cmd_args)

            sub_cmd = 'checkout'
            self.logger.info('checking out %s to %s' % (url, abs_todir))
            out = self.svn.run_cmd_with_args(sub_cmd, cmd_args)
            self.logger.info('checked out %s, %s' % (url, out))
            result = True
        except Exception as e:
            if 'is already a working copy for a different URL' in str(e):
                self.logger.warning(
                    '%s failed, (%s), remove and retry' %
                    (cmd_args, e))
                shutil.rmtree(abs_todir)
                self.svn.run_cmd_with_args(sub_cmd, cmd_args)
            elif "doesn't exist" in str(e):
                self.logger.error(
                    'Aborted, failed to checkout %s, %s' %
                    (url, e))
            elif "E155004" in str(e) or "E155037" in str(e):
                # locked
                self.logger.warning(
                    '%s failed,(%s), cleanup and retry' %
                    (cmd_args, e))
                self.svn.run_cleanup(abs_todir)
                out = self.svn.run(sub_cmd, cmd_args)
                self.logger.info('checked out %s, %s' % (url, out))
                result = True
            else:
                raise e

        return result

    def update_modified_dirs(self, changed_abspaths, modified_dirs, rev):
        rev = int(rev)
        prev_rev = rev - 1
        externals_to_checkout = set()
        for mod_dir in modified_dirs:
            mod_dir_url = self.translate_abspath_to_repopath([mod_dir])[0]
            prev_props = None
            try:
                prev_props = self.svn.run_proplist(mod_dir_url, prev_rev, rev)
            except Exception as e:
                if 'Unable to find repository location for' not in str(e):
                    raise

            curr_props = self.svn.run_proplist(mod_dir_url, rev, rev)

            prev_external = curr_external = None
            if prev_props:
                prop_dict = prev_props[0][1]
                prev_external = prop_dict.get('svn:externals')
            if curr_props:
                prop_dict = curr_props[0][1]
                curr_external = prop_dict.get('svn:externals')

            # remove record from changed_abspaths, the directory is
            # going to be re-added with modified new 'action's
            for idx, ca in enumerate(changed_abspaths):
                if ca['path'] == mod_dir:
                    del changed_abspaths[idx]
                    break

            if prev_external != curr_external:
                prev_externals = self.get_external_dir(prev_external, mod_dir)
                curr_externals = self.get_external_dir(curr_external, mod_dir)

                prev_externals = set(prev_externals)
                curr_externals = set(curr_externals)

                common_externals = prev_externals & curr_externals
                prev_externals = prev_externals - common_externals
                curr_externals = curr_externals - common_externals

                self.logger.warning('prev_externals: %s' % prev_externals)
                self.logger.warning('curr_externals: %s' % curr_externals)

                if self.cli_arguments.svn_ignore_externals:
                    msg = 'Change of externals ignored by cli argument'
                    self.logger.warning(msg)
                    continue

                # add to change log so that they could be
                # added/removed
                for _, _, _, prev_absdir in prev_externals:
                    path_to_del = {'path': prev_absdir, 'action': 'D'}
                    path_to_del = pysvn.PysvnLogChangedPath(path_to_del)
                    changed_abspaths.append(path_to_del)

                for _, _, _, curr_absdir in curr_externals:
                    for cp in changed_abspaths:
                        if curr_absdir == cp['path'] and cp['action'] == 'D':
                            cp['action'] = 'R'
                            break

                    path_to_add = {'path': curr_absdir, 'action': 'A',
                                   'externals': True}
                    path_to_add = pysvn.PysvnLogChangedPath(path_to_add)
                    changed_abspaths.append(path_to_add)

                externals_to_checkout |= curr_externals

        return externals_to_checkout

    def generate_cache_fileinfo_filename(self):
        cache_file = self.SVN_REPO_URL + self.SVN_PROJECT_DIR
        cache_file = cache_file.replace(':', '')
        cache_file = cache_file.replace('/', '_')

        tmp_dir = os.environ.get('TMPDIR', '/tmp')
        return os.path.join(tmp_dir, cache_file)

    def get_cache_fileinfo(self):
        cache_file = self.generate_cache_fileinfo_filename()

        file_kind_dict = dict()
        if os.path.isfile(cache_file):
            with open(cache_file, 'rb') as f:
                file_kind_dict = pickle.load(f)

        return file_kind_dict

    def update_cache_fileinfo(self, file_kind_dict):
        cache_file = self.generate_cache_fileinfo_filename()
        with open(cache_file, 'wb') as f:
            f.write(pickle.dumps(file_kind_dict))
#            pickle.dump(file_kind_dict.decode("utf-8"), f)

    def get_repofile_kind(self, files_to_mod, rev):
        #paths_to_check = [f for f in files_to_mod if f not in self.svn_path_kinds]
        paths_to_check = []
        svn_path_kinds = self.get_cache_fileinfo()

        urls_to_mod = self.translate_abspath_to_repopath(files_to_mod)
        for url, p in zip(urls_to_mod, files_to_mod):
            k = '%s@%s' % (url.rstrip('/'), rev)
            kind = svn_path_kinds.get(k)
            if kind:
                #self.logger.info('%s fileinfo found in cache: %s' % (k, kind))
                pass
            else:
                paths_to_check.append(p)

        dirs_to_check = set()
        for f in sorted(paths_to_check, key=len, reverse=True):
            if f not in dirs_to_check:
                path_dir, _ = os.path.split(f)
                dirs_to_check.add(path_dir)

        repo_url = self.SVN_REPO_URL

        urls_to_check = self.translate_abspath_to_repopath(list(dirs_to_check))
        for idx, url in enumerate(urls_to_check):
            msg = 'Getting info of %s@%s(%d/%d)' % (url, rev, idx + 1,
                                                    len(urls_to_check))
            self.logger.info(msg)
            files_list_info = self.svn.run_list(url, rev, rev)
            for fi in files_list_info:
                file_url = os.path.join(repo_url, fi[0]['repos_path'][1:])
                file_kind = fi[0]['kind']

                k = '%s@%s' % (file_url.rstrip('/'), rev)
                if file_kind == pysvn.node_kind.dir:
                    svn_path_kinds[k] = 'd'
                elif file_kind == pysvn.node_kind.file:
                    svn_path_kinds[k] = 'f'

        self.update_cache_fileinfo(svn_path_kinds)

        return svn_path_kinds

    def get_files_to_mod(self, changed_abspaths, rev):
        files_to_mod = [p['path'] for p in changed_abspaths
                        if p['action'] == 'M']

        svn_path_kinds = self.get_repofile_kind(files_to_mod, rev)

        urls_to_mod = self.translate_abspath_to_repopath(files_to_mod)

        # get info of paths
        modified_dirs = []
        modified_files = []
        for idx, file_url in enumerate(urls_to_mod):
            k = '%s@%s' % (file_url.rstrip('/'), rev)
            file_kind = svn_path_kinds.get(k)

            if file_kind == 'f':
                modified_files.append(files_to_mod[idx])
            elif file_kind == 'd':
                modified_dirs.append(files_to_mod[idx])
            else:
                raise RepSvnException('incorrect file kind')

        externals = []
        if modified_dirs:
            externals = self.update_modified_dirs(changed_abspaths,
                                                  modified_dirs, rev)

        return modified_files, externals

    def update_changed_files_in_group(self, changed_files, rev, peg_revs=None,
                                      update_arg=None):
        if not changed_files:
            return changed_files

        num_of_files = len(changed_files)
        gs = 200

        updated_files = []
        for idx in range(gs, num_of_files + gs, gs):
            files_group = changed_files[idx - gs:idx]
            updated = self.update_changed_files(files_group,
                                                rev=rev,
                                                peg_revs=peg_revs,
                                                update_arg=update_arg)
            updated_files.extend(updated)

        return updated_files

    def update_changed_files(self, changed_files, rev, peg_revs=None,
                             update_arg=None):
        '''Update files in changed_path to @rev and sanity-check the update
        '''
        if not changed_files:
            return changed_files

        if not peg_revs:
            peg_revs = [rev] * len(changed_files)

        self.logger.debug('changed files: %s' % pformat(changed_files))
        try:
            self.svn.run_update(changed_files, rev, peg_revs=peg_revs,
                                update_arg=update_arg)
        except SvnPythonException as e:
            '''https://svn.apache.org/repos/asf/subversion/branches/1.8.x/subversion/libsvn_client/update.c

            468   /* We handle externals after the update is complete, so that
            469      handling external items (and any errors therefrom) doesn't delay
            470      the primary operation.  */

            "svn update" handles externals at the end of the process,
            so when we see this error, it means that update of other
            files has been done, but update of externals
            failed. There's nothing we can do for it, we can safely
            ignore this exception.
            '''
            if 'Error handling externals definition for' in str(e):
                self.logger.error(
                    'updating svn external failed(%s), keep going' %
                    e)
                return changed_files

            # handle missing nodes
            missing_node_pat = "The node '(?P<missing>.*)' was not found"
            missing_node_result = re.search(missing_node_pat, str(e))
            self.logger.error(
                'missing node result: %s' %
                pformat(missing_node_result))
            if missing_node_result:
                changed_files_existant = []
                for cf in changed_files:
                    file_info = None
                    try:
                        file_info = self.svn.run_info2(cf)
                    except pysvn.ClientError as ce:
                        pass

                    if file_info:
                        changed_files_existant.append(cf)

                self.logger.warning(
                    'changed_files: %s' %
                    pformat(changed_files))
                self.logger.warning(
                    'changed_files_exi: %s' %
                    pformat(changed_files_existant))

                return self.update_changed_files(changed_files_existant, rev,
                                                 peg_revs, update_arg)

            raise e

        return changed_files

    def cleanup_externals(self):
        '''We have to cleanup externals after submitting a change, otherwise
        we may have trouble updating a new changeset which has
        modified files in the same directory as externals.
        '''
        wc_root = self.get_root_folder()
        svn_st = self.svn.run_status(wc_root)
        for svn_file_st in svn_st:
            if svn_file_st.is_versioned == 0:
                if os.path.isdir(svn_file_st.path):
                    shutil.rmtree(svn_file_st.path)
                else:
                    os.remove(svn_file_st.path)

    def remove_excluded_files(self):
        '''If parent of a directory that should be excluded is "added", all
        files in parent directory will also be updated. in this case
        we can only exclude, by removing, them after the update.

        e.g. in svn log we have:
        A   /repo/project/parent
        A   /repo/project/parent/bin

        but "/repo/project/parent/bin" should be excluded.
        '''
        wc_root = self.get_root_folder()
        project_dir = self.SVN_PROJECT_DIR

        for walk_root, dirs, files in os.walk(wc_root):
            # for name in dirs + files:
            for name in files:
                file_full_path = os.path.join(walk_root, name)
                rel_repo_path = os.path.join(
                    project_dir, file_full_path[len(wc_root) + 1:])

                if self.is_in_cur_project(rel_repo_path, project_dir):
                    continue

                if name in dirs:
                    shutil.rmtree(file_full_path)
                elif name in files:
                    os.remove(file_full_path)

                self.logger.error('%s' % file_full_path)
                if '.svn' not in file_full_path:
                    pass
                    #raise Exception('%s is removed' % file_full_path)

    def update_changed_paths(self, changed_abspaths, rev):
        '''Update files in changed_path to @rev and sanity-check the update
        '''
        to_add = self.get_files_to_add(changed_abspaths)
        to_del = self.get_files_to_del(changed_abspaths)
        to_rep = self.get_files_to_rep(changed_abspaths)
        to_mod, externals = self.get_files_to_mod(changed_abspaths, rev)

        to_update = to_add + to_del + to_rep
        if to_update:
            self.update_changed_files_in_group(
                to_update, rev, update_arg='--set-depth infinity')

        if to_mod:
            self.update_changed_files_in_group(to_mod, rev)

        self.logger.info('externals to checkout: %s' % externals)
        project_dir = self.SVN_PROJECT_DIR
        wc_dir = self.get_root_folder()
        for ext in externals:
            ext_src_url, peg_rev, rev, abs_todir = ext
            rel_repo_path = os.path.join(
                project_dir, abs_todir[len(wc_dir) + 1:])

            '''exclude files from svn:externals

            1) use svn list to get file info of svn:external
            2) test if all files in svn:external can pass exclusion test
            3) if so, checkout the whole directory
            4) otherwise, checkout an empty svn repo and then update
            files that passed the exclusion test
            '''
            try:
                list_depth = pysvn.depth.infinity
                files_list_info = self.svn.run_list(ext_src_url, rev,
                                                    peg_rev, depth=list_depth)
            except pysvn.ClientError as e:
                if 'non-existent' in str(e):
                    continue
                raise

            # get external project root directory
            ext_content_paths = [fi[0]['repos_path'] for fi in files_list_info]
            ext_content_paths = sorted(ext_content_paths, key=len)
            ext_proj_dir = ext_content_paths.pop(0)
            if not all([content_path.startswith(ext_proj_dir)
                        for content_path in ext_content_paths]):
                msg = 'some path does not starts with %s' % ext_proj_dir
                raise RepSvnException(msg)

            # we only care about files
            ext_content_paths = [fi[0]['repos_path'] for fi in files_list_info
                                 if pysvn.node_kind.file == fi[0]['kind']]
            ext_to_files = [os.path.join(rel_repo_path,
                                         ext_content_path[len(ext_proj_dir) + 1:])
                            for ext_content_path in ext_content_paths]

            self.logger.debug('ext_to_files: %s' % ext_to_files)
            ext_cont_in_view = [self.is_in_cur_project(ext_dir, project_dir)
                                for ext_dir in ext_to_files]
            self.logger.debug('ext_cont_in_view: %s' % ext_cont_in_view)

            if all(ext_cont_in_view):
                self.checkout_externals(ext_src_url, peg_rev, rev, abs_todir,
                                        depth='infinity')
            else:
                self.checkout_externals(ext_src_url, peg_rev, rev, abs_todir,
                                        depth='empty')
                changed_files = [ext_file[len(rel_repo_path) + 1:]
                                 for ext_file in ext_to_files
                                 if self.is_in_cur_project(ext_file, project_dir)]
                peg_revs = []
                if peg_rev:
                    peg_revs = [peg_rev] * len(changed_files)
                self.logger.debug('changed files: %s' % changed_files)
                self.logger.debug('abs_todir: %s' % abs_todir)
                with working_in_dir(abs_todir):
                    self.svn.run_update(
                        changed_files, revision=rev, peg_revs=peg_revs)

        self.remove_excluded_files()

        return True

    def translate_repopath_to_abspath(self, changed_paths):
        '''translate repo path of changed_paths to abs path
        '''
        project_dir = self.SVN_PROJECT_DIR
        wc_dir = self.get_root_folder()

        changed_abspaths = changed_paths[:]
        for p in changed_abspaths:
            # translate repo path to abs path
            # get relative path to working copy root
            path = p['path']
            path = path[len(project_dir):]
            abs_path = os.path.join(wc_dir, path[1:])
            p['path'] = abs_path

        return changed_abspaths

    def translate_abspath_to_repopath(self, changed_paths):
        '''translate abs path of changed_paths to url repo path
        '''
        repo_url = self.SVN_REPO_URL
        project_dir = self.SVN_PROJECT_DIR
        wc_dir = self.get_root_folder()

        changed_urlpaths = []
        for path in changed_paths:
            url_path = path[len(wc_dir):]
            url_path = os.path.join(project_dir, url_path[1:])
            url_path = os.path.join(repo_url, url_path[1:])
            changed_urlpaths.append(url_path)

        return changed_urlpaths

    def is_in_cur_project(self, path, project_dir):
        '''file is in current project if it startswith project path
        of contains project path
        '''
        cp = os.path.normpath(path)
        pd = os.path.normpath(project_dir)
        if cp == pd:
            return True

        if len(cp) < len(pd):
            longer_dir = os.path.split(pd)[0]
            if longer_dir.startswith(cp):
                return True

        translated_path = self.view_map.translate('/%s' % cp)

        in_curr_view = translated_path is not None
        if not in_curr_view:
            self.logger.warning('%s is excluded' % cp)

        return in_curr_view

    def exclude_paths_not_in_curr_project(self, changed_paths, project_dir):
        '''exclude changed paths that are not in current project

        @param changed_paths list of dictionary of record of changed paths
        @return filtered list of paths
        '''
        def cp_in_cur_proj(cp): return self.is_in_cur_project(
            cp['path'], project_dir)
        changed_paths_in_project = list(filter(cp_in_cur_proj, changed_paths))
        return changed_paths_in_project

    def fix_R_action_without_add(self, changed_abspaths):
        '''fix standalone "R" entry in svn log output.

        A "R", for Replace, entry in svn log is usually followed by an "A",
        for addition, of the same file/directory.

        We can, though rarely, see "R" entries in output of "svn log"
        with no accompanying "A" entry. In this case, we have to
        manually add one.
        '''
        replace_entries = [
            cp for cp in changed_abspaths if cp['action'] == 'R']
        add_paths = (cp['path'] for cp in changed_abspaths
                     if cp['action'] == 'A')

        fixed_changed_paths = changed_abspaths[:]
        for idx, r in enumerate(replace_entries):
            replace_path = r['path']
            if replace_path in add_paths:
                continue

            new_add_entry = pysvn.PysvnLog(r)
            new_add_entry['action'] = 'A'
            fixed_changed_paths.append(new_add_entry)

        return fixed_changed_paths

    def update_to_revision(self, rev):
        '''update modified files in rev in working copy

        @param rev
        return modified files and next revision number
        '''
        project_dir = self.SVN_PROJECT_DIR
        self.logger.info('Updating %s to r%d' % (project_dir, rev))

        # get list of changed files/directories of this revision
        svn_rev_log = self.svn.run_log(start_rev=rev, end_rev=rev)[0]

        changed_paths = svn_rev_log['changed_paths']
        # exclude those not related to current project/directory
        paths_in_project = self.exclude_paths_not_in_curr_project(
            changed_paths, project_dir)

        # translate from repo path to abspath
        changed_abspaths = self.translate_repopath_to_abspath(paths_in_project)

        changed_abspaths = self.fix_R_action_without_add(changed_abspaths)

        self.update_changed_paths(changed_abspaths, rev)
        self.verify_svn_update(changed_abspaths)

        svn_rev_log['changed_paths'] = changed_abspaths

        return svn_rev_log

    def get_commit_msg(self, svn_rev_log):
        msg = svn_rev_log.get('message')

        if msg is None:
            msg = 'No description specified.'
            raise RepSvnException(msg)

        return msg

    def submit_opened_files(self, files_to_submit, desc, src_rev,
                            src_srv, orig_submitter, orig_submit_time):
        '''run submit if any file opened

        description would be modified to indicate replication.
        @param desc, description of original change
        @param src_rev source revision replicated
        @param src_srv from which server this change is replicated
        @return new changelist number if there are opened files, otherwise None.
        '''
        desc = self.format_replicate_desc(desc, src_rev, src_srv,
                                          orig_submitter, orig_submit_time)

        self.logger.info('svn run checkin desc: %s' % desc)
        new_rev = self.svn.run_checkin(files_to_submit, desc)

        if new_rev:
            return new_rev.number
        else:
            return None

    def svn_checkout_workingcopy(self):
        # checkout working copy
        project_dir = self.SVN_PROJECT_DIR
        svn_root = self.SVN_CLIENT_ROOT
        repo_url = self.SVN_REPO_URL
        user = self.SVN_USER
        passwd = self.SVN_PASSWD
        svn = SvnPython(repo_url, user, passwd, svn_root)

        has_existing_wc = os.path.isdir(os.path.join(svn_root, '.svn'))
        if has_existing_wc:
            self.logger.info('%s already has a working copy' % svn_root)
            return

        try:
            svn.checkout_working_copy(project_dir, self.counter,
                                      depth='empty')
        except pysvn.ClientError as e:
            if 'File not found' not in str(e):
                raise

            # if target svn directory does not exist, add it and
            # checkout again.
            svn_root = svn_root
            svn_proj_dir = project_dir

            svn.checkout_working_copy('/', revision=-1, depth='empty')

            project_dir_list = [_f for _f in project_dir.split('/') if _f]
            project_fs_dir = os.path.join(svn_root, project_dir[1:])
            project_fs_dir_root = os.path.join(svn_root, project_dir_list[0])
            os.makedirs(project_fs_dir)
            svn.run_add(project_fs_dir_root)
            svn.run_checkin(project_fs_dir_root, 'adding %s' % project_dir)

            shutil.rmtree(os.path.join(svn_root, '.svn'))
            shutil.rmtree(project_fs_dir_root)

            # checkout again
            svn.checkout_working_copy(project_dir, self.counter,
                                      depth='empty')
            svn.client = None
