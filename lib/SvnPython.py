#!/usr/bin/python3
# -*- coding: utf-8 -*-
# A Python interface to Subversion (SVN)

import os
import sys
import shlex
import time

from pprint import pprint
from subprocess import Popen, PIPE
import xml.etree.ElementTree as ET

from .buildlogger import getLogger
# from .localestring import (convert_curr_locale_to_unicode_str,
#                           convert_utf8_to_curr_locale,
#                           convert_unicode_to_current_locale)

import pysvn
from pysvn import (opt_revision_kind, ClientError)


class SvnPythonException(Exception):
    def __init__(self, arg):
        self.arg = arg

    def __str__(self):
        return str(self.arg)


def flatten(v):
    sub_list = list()

#    if isinstance(v, str):
    if isinstance(v, str):
        #        v = v.encode('utf8')
        v = shlex.split(v)
        sub_list = [s for s in v]
    elif hasattr(v, '__iter__'):
        for i in v:
            sub_list.extend(flatten(i))
    else:
        raise SvnPythonException('flatten error: unhandled type')

    return sub_list


def createDictFromElement(element):
    '''Create dictionary from xml ElementTree

    @param element list of "element tree" instance
    @return dictionary instance converted from xml element tree
    '''
    if not isinstance(element, list):
        raise TypeError

    if len(element) > 1:
        return [createDictFromElement([elem]) for elem in element]

    elem_dict = {}
    if not element:
        return elem_dict

    element = element[0]
    elem_dict.update(dict(list(element.items())))

    children = list(element)
    if not children:
        if elem_dict:
            elem_dict[element.tag] = element.text
            return elem_dict
        else:
            return element.text

    cld_tags = {cld.tag for cld in children}
    for cld_tag in cld_tags:
        children_with_same_tag = element.findall(cld_tag)
        elem_dict[cld_tag] = createDictFromElement(children_with_same_tag)

    return elem_dict


def wantsOutputAsDictList(args):
    if not isinstance(args, tuple):
        raise TypeError
    if '--list' in args:
        argList = list(args)
        argList.remove('--list')
        argList.append('--xml')
        newArgs = tuple(argList)
        return newArgs
    return None


def outputAsDictList(xml):
    root = ET.fromstring(xml)
    output = createDictFromElement(root.findall('*'))
    return output


class SvnPython(object):

    def __init__(self, repo_url, user, password, wc_root=None, verbose='INFO'):
        self.repo_url = repo_url
        self.username = user
        self.password = password
        self.wc_root = wc_root
        self.verbose = verbose

        self.logger = getLogger(repo_url)
        self.logger.setLevel(self.verbose)

        self.create_pysvn_client()

    def create_pysvn_client(self):
        self.client = pysvn.Client()

        #self.client.callback_get_log_message = self.callback_get_Log_Message
        self.client.callback_notify = self.callback_notify
        self.client.callback_cancel = self.callback_cancel
        self.client.callback_ssl_client_cert_password_prompt = self.callback_ssl_client_cert_password_prompt
        self.client.callback_ssl_client_cert_prompt = self.callback_ssl_client_cert_prompt
        self.client.callback_ssl_server_prompt = self.callback_ssl_server_prompt
        self.client.callback_ssl_server_trust_prompt = self.callback_ssl_server_trust_prompt
        self.client.callback_get_login = self.callback_get_login

    # pysvn callbacks
    def callback_get_login(self, realm, username, may_save):
        '''callback_get_login is called each time subversion needs a username
        and password in the realm to access a repository and has no
        cached credentials.
        '''
        self.logger.info('svn callback callback_get_login')
        ret_code = True
        save_in_config_dir = False
        return ret_code, self.username, self.password, save_in_config_dir

    def callback_notify(self, event_dict):
        self.logger.info('svn callback callback_notify')
        for k, v in event_dict.items():
            self.logger.debug('%s: %s' % (k, v))

    def callback_cancel(self):
        self.logger.debug('svn callback callback_cancel')
        return False

    def callback_ssl_client_cert_password_prompt(self, realm, may_save):
        self.logger.info(
            'svn callback callback_ssl_client_cert_password_prompt')
        ret_code = True
        save = True
        return ret_code, self.password, save

    def callback_ssl_client_cert_prompt(self, realm, may_save):
        self.logger.info('svn callback callback_ssl_client_cert_prompt')
        raise SvnPythonException('not expected to see this, yet.')

    def callback_ssl_server_prompt(self):
        self.logger.info('svn callback callback_ssl_server_prompt')

    def callback_ssl_server_trust_prompt(self, trust_data):
        self.logger.info('svn callback callback_ssl_server_trust_prompt')
        for key, value in trust_data.items():
            self.logger.info('%s: %s' % (key, value))
        return True, trust_data['failures'], True

    def _run(self, sub_cmd, *cmdArgs):
        cmdList = ['svn', '--non-interactive']

        if self.username is not None:
            cmdList.extend(['--username', self.username])
        if self.password is not None:
            cmdList.extend(['--password', self.password])

        cmdList.append(sub_cmd)
        flattened = flatten(cmdArgs)
        cmdList.extend(flattened)

        self.logger.debug(' '.join(cmdList))
        num_try = 3
        while num_try > 0:
            process = Popen(cmdList, stdout=PIPE, stderr=PIPE)
            stdout, stderr = process.communicate()

            if not stderr:
                return stdout
            if 'Unable to connect to a repository at URL' in stderr.decode():
                # probably a network glitch, try again
                num_try -= 1
                time.sleep(1)
                continue

            raise SvnPythonException(stderr)

        raise SvnPythonException(stderr)

    def _run_check_list(self, sub_cmd, *args):
        # look for --list optional output form
        flat_args = tuple(flatten(args))
        new_args = wantsOutputAsDictList(flat_args)
        if new_args is not None:
            args = new_args
        out = self._run(sub_cmd, args)
        if new_args is not None:
            return outputAsDictList(out)
        return out

    def __getattr__(self, name):
        if name.startswith("run_"):
            cmd = name[len("run_"):]
            cli_func = getattr(self.client, cmd)
            return lambda *args, **kargs: cli_func(*args, **kargs)
        else:
            if name in dir(self.client):
                cli_func = getattr(self.client, name)
                return lambda *args, **kargs: cli_func(*args, **kargs)
            else:
                self.logger.error('attr %s not found' % name)

    def run_version(self, quiet):
        cmd = '--version'
        if quiet:
            cmd += ' --quiet'
        out = self._run(cmd)
        return out.strip()

    def run_copy(self, src_url_or_path, dest_url_or_path, rev=None):
        # convert_curr_locale_to_unicode_str(src_url_or_path)
        src_url_or_path = src_url_or_path
        # convert_curr_locale_to_unicode_str(dest_url_or_path)
        dest_url_or_path = dest_url_or_path

        if rev:
            rev = pysvn.Revision(opt_revision_kind.number, rev)
        else:
            rev = pysvn.Revision(opt_revision_kind.head)

        return self.client.copy(src_url_or_path, dest_url_or_path, rev)

    def run_log(self, path=None, start_rev=0, end_rev=None, limit=0):
        self.logger.debug('%s, %s, %d' % (path, self.wc_root, start_rev))
#        if path:
#            path = convert_curr_locale_to_unicode_str(path)
        revision_start = pysvn.Revision(opt_revision_kind.head)
        if end_rev:
            end_rev = int(end_rev)
            revision_start = pysvn.Revision(opt_revision_kind.number, end_rev)

        revision_end = pysvn.Revision(opt_revision_kind.number, start_rev)
        if not path:
            path = self.wc_root

#        path = convert_curr_locale_to_unicode_str(path)
        logs = self.client.log(path, revision_start=revision_start,
                               revision_end=revision_end,
                               discover_changed_paths=True,
                               limit=limit)

        logs = sorted(logs, key=lambda log: log.revision.number)

        for log in logs:
            # convert_utf8_to_curr_locale(log.get('message', ''))
            log['message'] = log.get('message', '')
            # for cp in log.changed_paths:
            #     cp['path'] = convert_utf8_to_curr_locale(cp['path'])

        return logs

    def get_revision_list(self, svn_dir, start_rev=0):
        '''Get list of revision number of changesets that have affected
        svn_dir

        @param svn_dir string relative directory to url repo
        @return list of revision numbers
        '''
#        svn_dir = convert_curr_locale_to_unicode_str(svn_dir)
        # get all changesets
        url_path = '%s%s' % (self.repo_url, svn_dir)
        if start_rev:
            start_rev = int(start_rev)

        rev_logs = self.run_log(url_path, start_rev=start_rev)

        # extract revision numbers
        revisions = [log.revision.number for log in rev_logs]
        self.logger.debug(revisions)

        # sort the list to start from small numbers
        revisions.sort()

        return revisions

    def checkout_working_copy(
            self,
            svn_dir,
            revision=0,
            depth=None,
            target_dir=None):
        '''checkout a working copy for svn_dir in self.ws_root

        If no revision given, we find and checkout the 1st revision of
        changeset that affected the directory and checkout.
        If revision is -1, we get the last revision

        @param svn_dir string relative directory to repos
        @param revision revision to checkout
        '''

        if revision == 0:
            revisions = self.get_revision_list(svn_dir)
            revision = revisions[revision]
        elif revision == -1:
            url_path = '%s%s' % (self.repo_url, svn_dir)
            revisions = self.run_log(url_path, limit=1)
            revision = revisions[revision].revision.number

        if not target_dir:
            target_dir = self.wc_root

        url = '%s%s' % (self.repo_url, svn_dir)
        if depth:
            # call the command to get the job done
            cmd_args = "-r %s --depth %s %s '%s'" % (str(revision),
                                                     depth, url, target_dir)
            sub_cmd = 'checkout'
            self._run(sub_cmd, cmd_args)
        else:
            revision = pysvn.Revision(pysvn.opt_revision_kind.number,
                                      revision)

            self.run_checkout(url, target_dir, revision=revision)

    def run_info(self, paths):
        #        paths = convert_curr_locale_to_unicode_str(paths)
        return self.client.info(paths)

    def run_info2(self, paths, rev_num=None):
        #        paths = convert_curr_locale_to_unicode_str(paths)
        revision = pysvn.Revision(pysvn.opt_revision_kind.head)
        if rev_num:
            revision = pysvn.Revision(pysvn.opt_revision_kind.number,
                                      rev_num)

        '''
        if peg_revs:
            peg_revs = [pysvn.Revision(pysvn.opt_revision_kind.number,
                                       rev) for rev in peg_revs]
        else:
            peg_revs = [revision]*len(paths)
        '''
        peg_revs = [revision] * len(paths)

        if isinstance(paths, list):
            info = []
            for file_path, peg_rev in zip(paths, peg_revs):
                file_info = self.client.info2(file_path,
                                              revision=revision,
                                              peg_revision=peg_rev,
                                              recurse=False)
                info.append(file_info)
            return info
        else:
            return self.client.info2(paths, revision)

    def run_list(self, path, rev_num=None, peg_rev=None, depth=None):
        #        path = convert_curr_locale_to_unicode_str(path)

        revision = pysvn.Revision(pysvn.opt_revision_kind.head)
        if rev_num:
            revision = pysvn.Revision(pysvn.opt_revision_kind.number, rev_num)

        if peg_rev:
            peg_rev = pysvn.Revision(pysvn.opt_revision_kind.number, peg_rev)
        else:
            peg_rev = revision

        if depth:
            properties = self.client.list(path, revision=revision,
                                          peg_revision=peg_rev, depth=depth)
        else:
            properties = self.client.list(path, revision=revision,
                                          peg_revision=peg_rev)

        # for fi in properties:
        #     fi[0]['repos_path'] = convert_unicode_to_current_locale(fi[0]['repos_path'])

        return properties

    def run_add(self, files, *args, **kwargs):
        files = files  # convert_curr_locale_to_unicode_str(files)
        return self.client.add(files, *args, **kwargs)

    def run_cmd_with_args(self, sub_cmd, args_str):
        #        args_str = convert_curr_locale_to_unicode_str(args_str)
        return self._run(sub_cmd, args_str)

    def run_move(self, from_file, to_file):
     #       from_file = convert_curr_locale_to_unicode_str(from_file)
     #       to_file = convert_curr_locale_to_unicode_str(to_file)
        return self.client.move(from_file, to_file)

    def run_remove(self, filelist, *args, **kwargs):
        #        filelist = convert_curr_locale_to_unicode_str(filelist)
        return self.client.remove(filelist, *args, **kwargs)

    def run_checkin(self, files, desc):
     #       files = convert_curr_locale_to_unicode_str(files)
      #      desc =  convert_curr_locale_to_unicode_str(desc)
        return self.client.checkin(files, desc)

    def run_propget(self, prop_name, file_path):
       # file_path = file_path #convert_curr_locale_to_unicode_str(file_path)
        return self.client.propget(prop_name, file_path)

    def run_propdel(self, prop_name, file_path):
        #    file_path = convert_curr_locale_to_unicode_str(file_path)
        return self.client.propdel(prop_name, file_path)

    def run_propset(self, prop_name, prop_value, file_path):
     #   file_path = convert_curr_locale_to_unicode_str(file_path)
        return self.client.propset(prop_name, prop_value, file_path)

    def run_proplist(self, path, rev_num=None, peg_rev=None):
      #  path = convert_curr_locale_to_unicode_str(path)
        revision = pysvn.Revision(pysvn.opt_revision_kind.working)
        if rev_num:
            revision = pysvn.Revision(pysvn.opt_revision_kind.number, rev_num)

        if not peg_rev:
            peg_rev = revision
        else:
            peg_rev = pysvn.Revision(pysvn.opt_revision_kind.number, peg_rev)
        properties = self.client.proplist(path, revision=revision,
                                          peg_revision=peg_rev)

        return properties

    def run_update(self, files_to_upd, revision='HEAD', peg_revs=None,
                   update_arg=None):
        self.logger.debug('updating %s, %s' % (files_to_upd, update_arg))

#        files_to_upd = convert_curr_locale_to_unicode_str(files_to_upd)
        if isinstance(files_to_upd, str):
            files_to_upd = [files_to_upd]

        if not revision:
            revision = 'HEAD'
        if not update_arg:
            update_arg = ''
        if not peg_revs:
            peg_revs = [''] * len(files_to_upd)

        def shellquote(s):
            return "'" + s.replace("'", "'\\''") + "'"

        # use single quote to handle special file names.
        files_to_upd = sorted(files_to_upd, key=len)
        files_to_upd_single_quoted = [
            shellquote(
                "%s@%s" %
                (f, peg_rev)) for f, peg_rev in zip(
                files_to_upd, peg_revs)]
        files_to_upd_joined = ' '.join(files_to_upd_single_quoted)

        cmd_args = '-r %s --parents %s %s' % (str(revision),
                                              files_to_upd_joined,
                                              update_arg)

        sub_cmd = 'update'
        self.logger.info('updating %s' % cmd_args)
        self._run(sub_cmd, cmd_args)


if __name__ == '__main__':
    logger = getLogger(__name__)
    url = ''
    user = ''
    passwd = ''
    wc_root = '/tmp/symlink'
    #config_dir = '/tmp/symlink_config'
    svn_dir = '/bigtop/trunk'
    #svn = SvnPython(url, user, passwd, config_dir)
    svn = SvnPython(url, user, passwd, wc_root)
    svn.checkout_working_copy(svn_dir, depth='empty')
    files_to_update = ['/bigtop-tests/test-artifacts/sqoop/src'
                       '/main/groovy/org/apache/bigtop/itest/integration'
                       '/sqoop/IntegrationTestSqoopHBase.groovy',
                       '/bigtop-tests/test-artifacts/sqoop/src/main'
                       '/resources/hbase-sqoop/create-table.hxt', ]
    files_to_update = [os.path.join(wc_root, to_update[1:])
                       for to_update in files_to_update]
    svn.run_update(files_to_update, 948)

    svn_logs = svn.run_log(start_rev=948, end_rev=948, limit=2)
    #assert svn_logs[0].revision.number == 948
    #assert svn_logs[1].revision.number == 949
    logger.info('run_log ' + '*' * 80)
    pprint(svn_logs)
    for log in svn_logs:
        for k, v in log.items():
            print('%s: %s' % (k, v))
        continue
        changed_paths = log['changed_paths']
        for path in changed_paths:
            for k, v in path.items():
                print(('%s: %s' % (k, v)))
        print(('length of changed paths: %d' % len(changed_paths)))

    if True:
        statuss = svn.run_status(svn.wc_root)
        logger.info('run_status ' + '*' * 80)
        for status in statuss:
            for k, v in status.items():
                print(('%s: %s' % (k, v)))

        info = svn.run_info(svn.wc_root)
        logger.info('run_info ' + '*' * 80)
        for k, v in info.items():
            print(('%s: %s' % (k, v)))
        rev = info['revision']
        print((rev.number))
