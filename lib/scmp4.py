#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import re
import shlex
import shutil
import stat
import uuid

from datetime import datetime
from pprint import pprint, pformat

from .buildlogger import getLogger
from P4 import P4, P4Exception, Resolver, Map
from .p4server import P4Server
from .scmrep import ReplicationSCM, ReplicationException


def check_if_known_issue(error_msg):
    KNOWN_ISSUES = ['Out of date files must be resolved or reverted', 'Merges still pending -- use', 'Unexpected revs:']
    for msg in KNOWN_ISSUES:
        if msg in str(error_msg):
            return True
    return False


class RepP4Exception(ReplicationException):
    pass


class ChangeRevision:
    def __init__(self, r, a, t, d, l):
        self.rev = r
        self.action = a
        self.type = t
        self.depotFile = d
        self.localFile = l
        self.integrations = []
        self.fixedLocalFile = ChangeRevision.convert_ascii_to_p4wildcard(l)

    @staticmethod
    def convert_p4wildcard_to_ascii(file_path):
        '''convert special characters in file names for p4 commands

        https://www.perforce.com/perforce/r12.1/manuals/cmdref/o.fspecs.html
        '''
        ascii_p4fixed = file_path
        ascii_p4fixed = ascii_p4fixed.replace("%", "%25")
        ascii_p4fixed = ascii_p4fixed.replace("@", "%40")
        ascii_p4fixed = ascii_p4fixed.replace("#", "%23")
        ascii_p4fixed = ascii_p4fixed.replace("*", "%2A")

        return ascii_p4fixed

    @staticmethod
    def convert_ascii_to_p4wildcard(ascii_path):
        '''convert ascii expanded file name to p4 wild cards

        p4 uses ascii expansion internally to handle paths that have
        wild cards. When we need to talk with os file system, we still
        need their original names.
        '''
        char_p4fixed = ascii_path
        char_p4fixed = char_p4fixed.replace("%25", "%")
        char_p4fixed = char_p4fixed.replace("%40", "@")
        char_p4fixed = char_p4fixed.replace("%23", "#")
        char_p4fixed = char_p4fixed.replace("%2A", "*")

        return char_p4fixed

    def __repr__(self):
        return ' '.join(['rev = {} '.format(self.rev),
                         'action = {} '.format(self.action),
                         'type = {} '.format(self.type),
                         'depotFile = {} '.format(self.depotFile),
                         'localFile = {} '.format(self.localFile), ])


class ReplicationP4(ReplicationSCM):

    def __init__(self, section, cfg_parser, cli_arguments, verbose='INFO'):
        self.option_properties = [
            ('P4CLIENT', False),
            ('P4MASKCLIENT', True),
            ('EMPTY_FILE', True),
            ('P4USER', False),
            ('P4PORT', False),
            ('COUNTER', True),
            ('ENDCHANGE', True),
            ('P4PASSWD', True), ]
        super(ReplicationP4, self).__init__(section, cfg_parser)

        # only used by target p4config instance
        self.section = section
        self.src_p4 = None
        self.counter = 0
        if self.COUNTER:
            self.counter = int(self.COUNTER)
        self.cli_arguments = cli_arguments
        self.logger = getLogger('ReplicationP4')
        self.logger.setLevel(verbose)

    def __str__(self):
        return '[%s P4PORT=%s P4CLIENT=%s P4USER=%s]' % (
            self.section, self.P4PORT, self.P4CLIENT, self.P4USER)

    def connect(self):
        self.p4 = P4Server(self.P4PORT, self.P4USER, self.P4PASSWD,
                           log_level=self.cli_arguments.verbose)
        self.p4.exception_level = P4.RAISE_ERROR
        self.p4.client = self.P4CLIENT

        clientspec = self.p4.fetch_client(self.p4.client)

        self.stream = clientspec.get('Stream')

        self.root = clientspec._root
        self.p4.cwd = self.root
        self.clientmap = Map(clientspec._view)

        ctr = Map('//%s/...  %s/...' % (clientspec._client,
                                        clientspec._root))
        self.localmap = Map.join(self.clientmap, ctr)
        self.depotmap = self.localmap.reverse()

        self.maskdepotmap = None
        if self.P4MASKCLIENT:
            maskclientspec = self.p4.fetch_client(self.P4MASKCLIENT)
            maskclientmap = Map(maskclientspec._view)
            ctr = Map('//%s/...  %s/...' % (maskclientspec._client,
                                            maskclientspec._root))
            masklocalmap = Map.join(maskclientmap, ctr)
            self.maskdepotmap = masklocalmap.reverse()

    def disconnect(self):
        self.p4.disconnect()

    def get_root_folder(self):
        clientspec = self.p4.fetch_client(self.p4.client)
        return clientspec['Root']

    def verifyCounter(self):
        change = self.p4.run_changes('-m1', '...')
        self.changeNumber = (int(change[0]['change']) if change else 0)
        return self.counter <= self.changeNumber

    def get_changes_to_replicate(self):
        """end_change, int, last changelist to be replicated
        """
        end_change = int(self.ENDCHANGE) if self.ENDCHANGE else None
        range_start = '@%d' % self.counter
        range_end = ('@%d' % end_change) if end_change else '#head'
        rev_range = '...%s,%s' % (range_start, range_end)
        changes = self.p4.run_changes('-l', rev_range)

        changes.reverse()
        if changes and str(changes[0]['change']) == str(self.counter):
            changes = changes[1:]

        if self.cli_arguments.maximum:
            changes = changes[:self.cli_arguments.maximum]

        return changes

    def get_base_change_to_replicate(self):
        """Get the counter changelist to replicate
        """
        rev_range = '...@%d,@%d' % (self.counter, self.counter)
        changes = self.p4.run_changes('-l', rev_range)
        return changes[0]

    def is_p4_directory(self, path):
        p4 = self.p4

        out = p4.run_dirs(path)
        is_p4_dir = len(out) > 0 and out[0]['dir']

        return is_p4_dir

    def get_commit_message_of_rev(self, rev='head', num_of_rev=1):
        '''Get commit message of last revision

        @param rev, rev num or 'head'
        @param num_of_rev, number of revisions to get
        @return list of string of commit messages, in changelist num
        ascending order.
        '''
        if rev == 'head':
            rev = '...#head'
        else:
            rev = '...@%s' % rev

        changes = self.p4.run_changes('-l', '-m', str(num_of_rev), rev)
        descs = [l['desc'] for l in changes]
        descs.reverse()

        return descs

    def resetWorkspace(self):
        self.p4.run_sync('-f', '...#none')

    def revertChanges(self):
        self.p4.run_revert('...')

    def reorder_change_revisions(self, change_revisions):
        '''process move/deletes last because hopefully they are a natural
        side-effect of move/adds in the same changelist

        process move/adds second to last in case the source file has
        another modification in the same changelist

        @param change_revisions list of change revisions

        '''
        def sort_add_del(change_rev):
            if change_rev.action == 'move/delete':
                return 2
            if change_rev.action == 'move/add':
                return 1
            return 0

        return change_revisions.sort(key=sort_add_del)

    def sync_to_change(self, changelist):
        '''sync workspace to changelist

        @param changelist string of changelist
        '''
        return self.p4.run_sync('-f', '...@%s,%s' % (changelist, changelist))

    def get_filelogs(self, depot_files):
        '''get filelog of depot_files

        @param depot_files list of strings of files
        @return dictionary of {depot_file:filelog}
        '''
        # remove None and '' from list
        depot_files = [fn for fn in depot_files if fn]
        # remove duplicate
        depot_files = list(set(depot_files))

        # we get results for this num of files each loop
        num_files_per_run = 255

        if len(depot_files) > num_files_per_run:
            # append Nones so that we don't lose any file when using zip()
            depot_files_extended = depot_files[:]
            depot_files_extended.extend([None] * (num_files_per_run - 1))
            depot_files_iter = iter(depot_files_extended)
            # divide list in to list of lists of 100 files
            depot_files_groups = list(
                zip(*([depot_files_iter] * num_files_per_run)))
        else:
            depot_files_groups = [depot_files, ]

        tdf_file_logs = {}
        for tdfs in depot_files_groups:
            tdfs = [_f for _f in tdfs if _f]
            if not tdfs:
                continue

            file_logs = self.p4.run_filelog('-m1', tdfs)

            if len(tdfs) == len(file_logs):
                tdf_file_logs.update(dict(list(zip(tdfs, file_logs))))
            else:
                depotFile_in_warning = [fl_w[:-len(' - no such file(s).')]
                                        for fl_w in self.p4.warnings]

                tdfs_exist = []
                for dfs_depotFile in tdfs:
                    dfs_depotFile_path = dfs_depotFile.split('#')[0]
                    if dfs_depotFile_path in depotFile_in_warning:
                        tdf_file_logs[dfs_depotFile] = None
                    else:
                        tdfs_exist.append(dfs_depotFile)

                tdf_file_logs.update(dict(list(zip(tdfs_exist, file_logs))))

        if len(tdf_file_logs) != len(depot_files):
            raise RepP4Exception('len(filelogs) != len(depotfiles)')
        return tdf_file_logs

    def get_integrations_to_replicate(self, depotFile, rev, filelog):
        '''get integrations of revision of depotFile

        @param depotFile string of depot file path
        @param rev string revision number
        @return list of integrations
        '''
        revision = filelog.revisions[0]
        integs = []

        integ_to_actions = ('copy into', 'branch into', 'edit into',
                            'add into', 'delete into', 'merge into',
                            'moved into', 'ignored by', 'undone by')
        integ_from_actions = ('copy from', 'branch from', 'edit from',
                              'delete from', 'add from', 'merge from',
                              'moved from', 'ignored', 'undid')

        # use reversed() here because the order of integration records
        # from run_filelog() is opposite to what we get from command
        # "p4 filelog"
        for integ in reversed(revision.integrations):
            # check integration revision numbers
            if integ.srev >= integ.erev:
                msg = 'Unexpected revs: %s#%s %s' % (depotFile, rev, integ)
                raise RepP4Exception(msg)

            # srev is the revision _before_ the first contributor
            # and we want it to be the revision of the first
            # contributor
            integ.srev = integ.srev + 1

            # check integration how
            if integ.how in integ_to_actions:
                continue

            if integ.how in integ_from_actions:
                integ.localFile = self.localmap.translate(integ.file)
                integs.append(integ)
                continue

            msg = 'Unexpected how: %s#%s %s' % (depotFile, rev, integ)
            raise RepP4Exception(msg)

        return integs

    def get_change(self, changelist, sync_result=None):
        '''get description of changed files in a changelist

        @param changelist changelist number as a string
        @return list of change_revisions
        '''
        change_desc = self.p4.run_describe(changelist)[-1]
        local_files = [self.localmap.translate(df)
                       for df in change_desc['depotFile']]
        # If source server is case sensitive, ignore hack
        if self.p4.server_case_insensitive:
            if sync_result:
                # Hack, data in run_describe is incorrect, get the correct one from
                # the sync command
                # run this function only if source is case insensetive.
                new_local_files = []
                for s_file in sync_result:
                    new_local_files.append(s_file['clientFile'])

                # Make sure the order stays the same
                df_lower_list = [df.lower() for df in new_local_files]
                for fp in local_files:
                    if fp and (fp.lower() in df_lower_list):
                        local_files[local_files.index(fp)] = new_local_files[df_lower_list.index(fp.lower())]

                change_desc['depotFile'] = []

            for df in local_files:
                if df:
                    change_desc['depotFile'].append(
                        self.depotmap.translate(df))
                else:
                    change_desc['depotFile'].append(df)

        changed_file_rec = list(zip(local_files, change_desc['depotFile'],
                                    change_desc['action'],
                                    change_desc['rev'],
                                    change_desc['type']))
        # if local_file is None, this file is not in current branch,
        # should not care about it.
        changed_file_rec_in_branch = [
            cfr for cfr in changed_file_rec if cfr[0]]

        depot_file_revs = [
            '%s#%s' %
            (depot_file,
             rev) for _,
            depot_file,
            _,
            rev,
            _ in changed_file_rec_in_branch]
        changed_filelogs = self.get_filelogs(depot_file_revs)

        change_files = []
        for localFile, depotFile, action, rev, ftype in changed_file_rec_in_branch:
            chRev = ChangeRevision(rev, action, ftype, depotFile, localFile)

            supported_actions = ('add', 'branch', 'integrate', 'edit',
                                 'delete', 'move/delete', 'move/add', 'purge')
            if action not in supported_actions:
                raise RepP4Exception('Unsupported change action, %s' % action)

            filelog = changed_filelogs['%s#%s' % (depotFile, rev)]

            integs = self.get_integrations_to_replicate(depotFile, rev,
                                                        filelog)
            chRev.integrations.extend(integs)

            change_files.append(chRev)

        self.reorder_change_revisions(change_files)

        return change_files

    def inWarnings(self, text):
        if self.p4.warnings:
            for warning in self.p4.warnings:
                if text in warning:
                    self.logger.error(warning)
                    return True
        return False

    def checkWarnings(self, where):
        warnings = self.p4.warnings
        if warnings:
            self.logger.warning('warning in %s : %s' % (where, warnings))
            return warnings

        return []

    def checkErrors(self, where):
        errors = self.p4.errors
        if errors:
            self.logger.error('error in %s : %s' % (where, errors))
            return True

        return False

    def getDepotFile(self, localFile):
        if not localFile:
            return None

        return self.depotmap.translate(localFile)

    def inMaskDepot(self, localFile):
        if not localFile:
            return False

        if not self.maskdepotmap:
            return True

        return self.maskdepotmap.translate(localFile) is not None

    def file_in_workspace(self, local_file):
        in_mask_depot = self.inMaskDepot(local_file)
        in_target_depot = self.getDepotFile(local_file) is not None

        return in_mask_depot and in_target_depot

    def exclude_files_not_in_workspace(self, changed_files):
        files_in_ws = []

        for f in changed_files:
            local_file = f.localFile

            if self.file_in_workspace(local_file):
                files_in_ws.append(f)
                continue

            msg = "Skipping %s which is not in target workspace" % local_file
            self.logger.warning(msg)
            continue

        return files_in_ws

    def get_target_depotfile(self, changed_files):
        '''Add targetDepotFile in ChangeRevision, and do some checks

        called in target p4
        '''
        changed_files_with_targetdepot = changed_files[:]
        for f in changed_files_with_targetdepot:
            # depot path of file in target p4
            f.targetDepotFile = self.getDepotFile(f.localFile)

            for integ in f.integrations:
                # depot path of integration partner file in target p4
                integ.targetDepotFile = self.getDepotFile(integ.localFile)

        return changed_files_with_targetdepot

    def verify_depotfile_revisions(self, changed_files):
        '''verify depot file revisions

        If number of nonexisting file exceeds 50 or average time to
        run filelog exceeds 20ms, we stop.

        If we have 100,000 files to verify and average time to run
        filelog is 20 milliseconds, it's going to take less than ~33
        minutes to finish. Otherwise it's going to take too much time
        and cause connection timeout.

        @param changed_files list of ChangeRevisions

        '''
        target_depot_files = [f.targetDepotFile for f in changed_files]
        target_depot_files += [integ.targetDepotFile
                               for cf in changed_files
                               for integ in cf.integrations
                               if integ.targetDepotFile]

        tdf_file_logs = self.get_filelogs(target_depot_files)

        for idx, f in enumerate(changed_files):
            # scream if src revision doesn't equal target revision +1
            revision = 0

            filelog = tdf_file_logs.get(f.targetDepotFile)

            if filelog:
                revision = filelog.revisions[0].rev

            if revision + 1 > int(f.rev):
                msg = 'File in source depot {}#{} should be 1 revision ahead ' \
                      'of in target depot {}#{}. Error, target file should never be a revision ahead of source. revert'
                msg = msg.format(
                    f.depotFile,
                    f.rev,
                    f.targetDepotFile,
                    revision)
                self.p4.run_revert('...')
                raise RepP4Exception(msg)

            elif revision + 1 != int(f.rev):
                msg = 'File in source depot {}#{} should be 1 revision ahead ' \
                      'of in target depot {}#{}. Error ignored and progressing.'
                msg = msg.format(
                    f.depotFile,
                    f.rev,
                    f.targetDepotFile,
                    revision)
                self.logger.warning(msg)

            for integ in f.integrations:
                # depot path of integration partner file in target p4
                if not integ.targetDepotFile:
                    continue

                '''revision of integration partner file in target depot should be
                greater than or equal to erev which is end revision of
                the partner file in source depot.
                '''
                target_revision = 0
                filelog = tdf_file_logs.get(integ.targetDepotFile)
                if filelog:
                    target_revision = filelog.revisions[0].rev
                if target_revision < integ.erev:
                    msg = 'Integration source file {}#{} is older than ' \
                          'target file {}#{}.  Error ignored and proceeding.'
                    msg = msg.format(integ.file, integ.erev,
                                     integ.targetDepotFile, target_revision)
                    self.logger.warning(msg)

    def replicate_change_action_purge(self, file_change_rev, sourcePort):
        localFile = file_change_rev.localFile

        self.p4.run_sync('-k', localFile)

        try:
            localfile_fstat = self.p4.run_fstat('-Or', '-m1', localFile)
        except RepP4Exception:
            localfile_fstat = []

        if localfile_fstat:
            if not os.path.exists(localFile):
                self.p4.run_sync('-f', localFile)

            self.logger.warning("this file is supposed to exist, %s", os.path.exists(localFile))
            self.p4.run_edit('-t', file_change_rev.type, localFile)
        else:
            msg = ('%s does not exist in target depot, '
                   'ignoring it.' %
                   file_change_rev.fixedLocalFile)
            self.logger.warning(msg)
            # self.p4.run_add('-ft', file_change_rev.type,
            #                 file_change_rev.fixedLocalFile)

        self.checkWarnings(file_change_rev.action)

    def replicate_change_action_edit(self, file_change_rev, sourcePort):
        localFile = file_change_rev.localFile

        if file_change_rev.integrations:
            # This is an integration followed by an edit.
            tempFile = os.path.join(os.path.split(localFile)[0],
                                    str(uuid.uuid4()))
            shutil.copyfile(file_change_rev.fixedLocalFile, tempFile)

            file_change_rev.action = 'integrate'
            self.replicateIntegration(file_change_rev, sourcePort)
            self.checkWarnings('integrate (edit)')
            file_change_rev.action = 'edit'
            # run edit without changing filetype first then reopen and
            # change the filetype failing to do so results in random
            # silent failure to actually open for edit
            self.p4.run_sync('-k', localFile)
            self.p4.run_edit(localFile)
            self.checkWarnings('edit (edit)')
            self.p4.run_reopen('-t', file_change_rev.type, localFile)
            self.checkWarnings('reopen (reopen)')
            shutil.copyfile(tempFile, file_change_rev.fixedLocalFile)
            os.remove(tempFile)
        else:
            self.p4.run_sync('-k', localFile)

            try:
                localfile_fstat = self.p4.run_fstat('-Or', '-m1', localFile)
            except RepP4Exception:
                localfile_fstat = []

            if localfile_fstat:
                self.p4.run_edit('-t', file_change_rev.type, localFile)
            else:
                msg = ('%s does not exist in target depot, '
                       'adding instead of editing it.' %
                       file_change_rev.fixedLocalFile)
                self.logger.warning(msg)
                self.p4.run_add('-ft', file_change_rev.type,
                                file_change_rev.fixedLocalFile)

            self.checkWarnings(file_change_rev.action)

    def force_replicate_ignore_action(self, file_change_rev, sourcePort):
        localFile = file_change_rev.localFile
        self.p4.run_sync('-k', localFile)

        try:
            localfile_fstat = self.p4.run_fstat('-Or', '-m1', localFile)
        except RepP4Exception:
            localfile_fstat = []

        if localfile_fstat:
            if not os.path.exists(localFile):
                self.p4.run_delete('-v', localFile)
            else:
                self.p4.run_edit('-t', file_change_rev.type, localFile)
        else:
            msg = ('%s does not exist in target depot, '
                   'adding instead of editing it.' %
                   file_change_rev.fixedLocalFile)
            self.logger.warning(msg)
            self.p4.run_add('-ft', file_change_rev.type,
                            file_change_rev.fixedLocalFile)

        self.checkWarnings(file_change_rev.action)

    def replicate_change_action_add(self, file_change_rev, sourcePort):
        f = file_change_rev

        if f.integrations:
            if f.integrations[0].how == 'add from':
                self.logger.debug('Add from (add)')
                # This is a re-add
                self.replicateIntegration(f, sourcePort)
                self.checkWarnings('add from (add)')
            if f.integrations[0].how == 'ignored':
                self.p4.run_add('-ft', f.type, f.fixedLocalFile)
                self.checkWarnings(f.action)
            else:
                # This is a branch followed by an edit.
                tempFile = os.path.join(os.path.split(f.localFile)[0],
                                        str(uuid.uuid4()))
                shutil.copyfile(f.fixedLocalFile, tempFile)

                f.action = 'branch'
                self.replicateIntegration(f, sourcePort)
                self.checkWarnings('branch (add)')

                fstats = self.p4.run_fstat('-Or', '-m1', f.localFile)
                if fstats:
                    fstat = fstats[0]
                    f.action = 'add'
                    # If this action was converted from branch->add
                    # there's nothing to do as the local file is already
                    # correct
                    # print("foo = " + fstat['action'])
                    # and a subsequent call to edit will fail as the file
                    # is already marked for add
                    if fstat['action'] != 'add':
                        self.p4.run_edit('-t', f.type, f.localFile)
                        self.checkWarnings('edit (add)')
                        shutil.copyfile(tempFile, f.fixedLocalFile)
                else:
                    # The file is missing, need to re-add
                    self.p4.run_add('-ft', f.type, f.fixedLocalFile)
                    self.checkWarnings(f.action)

                os.remove(tempFile)
        else:
            self.p4.run_add('-ft', f.type, f.fixedLocalFile)
            self.checkWarnings(f.action)

    def replicate_change_action_del(self, file_change_rev, sourcePort):
        if file_change_rev.integrations:
            self.replicateIntegration(file_change_rev, sourcePort)
            self.checkWarnings('integrate (delete)')
        else:
            self.logger.debug('Delete without integration')

            # If the file to be deleted is already deleted, do
            # nothing, even the fscheck.
            localFile = file_change_rev.localFile
            fstats = self.p4.run_fstat('-Or', '-m1', localFile)
            if not fstats or fstats[0].get('headAction') == 'delete':
                msg = 'Ignored deletion %s, already-deleted' % localFile
                self.logger.warning(msg)
                return

            self.p4.run_delete('-v', localFile)
            self.checkWarnings(file_change_rev.action)

    def replicate_change_action_branch(self, file_change_rev, sourcePort):
        if file_change_rev.integrations:
            self.replicateIntegration(file_change_rev, sourcePort)
            self.checkWarnings(file_change_rev.action)
        else:
            self.p4.run_add('-ft', file_change_rev.type,
                            file_change_rev.fixedLocalFile)
            self.checkWarnings('add (branch)')

    def replicate_change_action_integrate(self, file_change_rev, sourcePort):
        if file_change_rev.integrations:
            self.replicateIntegration(file_change_rev, sourcePort)
            self.checkWarnings(file_change_rev.action)
        else:
            if os.path.isfile(file_change_rev.fixedLocalFile):
                self.p4.run_sync('-k', file_change_rev.localFile)
                self.p4.run_edit('-t', file_change_rev.type,
                                 file_change_rev.localFile)
                warnings = self.checkWarnings('edit (integrate)')
                fn = file_change_rev.fixedLocalFile[len(self.root) + 1:]
                file_not_on_client = any(
                    [('file(s) not on client.' in w and fn in w) for w in warnings])
                if file_not_on_client:
                    self.logger.warning(
                        'Cannot edit %s, not on client, adding it' % fn)
                    self.p4.run_add('-ft', file_change_rev.type,
                                    file_change_rev.fixedLocalFile)
            else:
                self.p4.run_delete('-v', file_change_rev.localFile)
                self.checkWarnings('delete (integrate)')

    def replicate_change_action_move_add(self, file_change_rev, sourcePort):
        if file_change_rev.integrations:
            self._replicate_move(file_change_rev, sourcePort)
        else:
            self.p4.run_add('-ft', file_change_rev.type,
                            file_change_rev.fixedLocalFile)
            self.checkWarnings('add (move/add)')

    def replicate_change_action_move_del(self, file_change_rev, sourcePort):
        if file_change_rev.integrations:
            self.replicateIntegration(file_change_rev, sourcePort)
            self.checkWarnings('integrate (delete)')
        else:
            self.p4.run_delete('-v', file_change_rev.localFile)
            self.checkWarnings(file_change_rev.action)

    def verify_replicate_action(self, file_change_rev):
        fstats = self.p4.run_fstat('-m1', file_change_rev.targetDepotFile)
        if not fstats:
            msg = 'Failed to retrieve fstat for %s' % file_change_rev.targetDepotFile
            # raise RepP4Exception(msg)
            self.logger.error(msg)
            return

        if 'action' not in fstats[0]:
            msg = 'Failed to replicate "%s" for target %s' % (
                file_change_rev.action, file_change_rev.targetDepotFile)
            raise RepP4Exception(msg)

    def add_base(
            self,
            src_changelist,
            p4_change,
            sourceP4):
        sourcePort = sourceP4.p4.port
        """ This will add the main folder
        """
        dirs = self.p4.run_dirs(os.path.join(self.p4.cwd, "*"))
        if dirs:
            msg = '%s path alrady exists in depot, base should be replicate to an empty destination' % (self.p4.cwd)
            raise RepP4Exception(msg)

        sourceP4.sync_to_change(src_changelist)
        self.p4.run('add', os.path.join(self.p4.cwd, "..."))
        # submit change
        orig_submitter = p4_change.get('user')
        orig_submit_time = p4_change.get('time')
        try:
            new_change = self.submit_opened_files(p4_change['desc'],
                                          p4_change['change'],
                                          sourcePort,
                                          orig_submitter,
                                          orig_submit_time)
        except P4Exception as e:
            self.logger.error(e)
            raise e

        return new_change

    def replicate_change(
            self,
            src_changelist,
            files_change_rev,
            p4_change,
            sourceP4):
        sourcePort = sourceP4.p4.port
        """This is the heart of it all. Replicate all changes according to
        their description
        """
        # exclude files that are not in current workspace
        files_to_rep = self.exclude_files_not_in_workspace(files_change_rev)
        files_to_rep = self.get_target_depotfile(files_to_rep)
        self.verify_depotfile_revisions(files_to_rep)

        action_to_func = {'edit': self.replicate_change_action_edit,
                          'add': self.replicate_change_action_add,
                          'delete': self.replicate_change_action_del,
                          'branch': self.replicate_change_action_branch,
                          'integrate': self.replicate_change_action_integrate,
                          'move/add': self.replicate_change_action_move_add,
                          'move/delete': self.replicate_change_action_move_del,
                          'purge': self.replicate_change_action_purge,
        }

        for file_change_rev in files_to_rep:
            self.logger.debug('replay p4 action: %s' % file_change_rev)

            # If source p4 server runs in unicode mode but target p4
            # doesn't, we should change file type to text.

            # in unicode mode, p4 automatical encodes filenames and
            # file contents in the encoding method specified by
            # p4.charset(p4python) or P4CHARSET(shell commands), while
            # file types(got from 'p4 describe') are 'unicode'.  We
            # cannot just submit the file as 'unicode' to a
            # non-unicode p4 server.
            rep_unicode_type = 'unicode' in file_change_rev.type
            if not self.p4.is_unicode_server() and rep_unicode_type:
                orig_filetype = file_change_rev.type
                self.logger.debug('orig_filetype: %s' % orig_filetype)
                file_change_rev.type = orig_filetype.replace('unicode',
                                                             'text')

            action_func = action_to_func.get(file_change_rev.action)
            if not action_func:
                msg = 'Unexpected "%s" for %s#%s.' % (file_change_rev.action,
                                                      file_change_rev.depotFile,
                                                      file_change_rev.rev)
                raise RepP4Exception(msg)

            action_func(file_change_rev, sourcePort)

            # self.verify_replicate_action(file_change_rev)

        # submit change
        orig_submitter = p4_change.get('user')
        orig_submit_time = p4_change.get('time')
        try:
            new_change = self.submit_opened_files(p4_change['desc'],
                                                  p4_change['change'],
                                                  sourcePort,
                                                  orig_submitter,
                                                  orig_submit_time)
        except P4Exception as e:
            self.logger.error(e)
            if not check_if_known_issue(e):
                raise e
            else:
                fail_changelist = (
                    re.search(
                        r'p4 submit -c (\d+)',
                        str(e).strip())).group(1)
                # Igrnore integration and use edit/add/remove instead
                self.p4.run_revert('...')
                self.p4.run('change', '-d', fail_changelist)
                sourceP4.sync_to_change(src_changelist)

                action_to_func['integrate'] = self.force_replicate_ignore_action

                for file_change_rev in files_to_rep:
                    self.logger.warning(files_to_rep)
                    self.logger.debug('replay p4 action: %s' % file_change_rev)
                    rep_unicode_type = 'unicode' in file_change_rev.type
                    if not self.p4.is_unicode_server() and rep_unicode_type:
                        orig_filetype = file_change_rev.type
                        self.logger.debug('orig_filetype: %s' % orig_filetype)
                        file_change_rev.type = orig_filetype.replace('unicode',
                                                                     'text')

                    action_func = action_to_func.get(file_change_rev.action)
                    if not action_func:
                        msg = 'Unexpected "%s" for %s#%s.' % (file_change_rev.action,
                                                              file_change_rev.depotFile,
                                                              file_change_rev.rev)
                        raise RepP4Exception(msg)

                    action_func(file_change_rev, sourcePort)

                new_change = self.submit_opened_files(
                    "ReplicationBot: Warning, couldn't submit this change as an integration, using edit/add/remove instead\n\n" + p4_change['desc'],
                    p4_change['change'],
                    sourcePort,
                    orig_submitter,
                    orig_submit_time)

        if self.cli_arguments.replicate_user_and_timestamp:
            self.update_change(new_change, orig_submitter, orig_submit_time)

        return new_change

    def get_revision_from_desc(self, filename):
        raise NotImplementedError()

    def is_new_revision(self, filename, new_rev):
        '''detect if rev is a new revision that hasn't yet been replicated.

        TODO: currently broken but good to have

        since the description was created in an automated manner,
        one should be able to parse the description for the
        revision number that created/edited the P4 file
        '''
        replicated_rev = self.get_revision_from_desc(filename)
        if replicated_rev is None:
            # first replication
            return

        if replicated_rev < new_rev:
            return

        msg = 'Cannot rep %d while %d is already in' % (new_rev,
                                                        replicated_rev)
        raise RepP4Exception(msg)

    def submit_opened_files(self, desc, src_rev, src_srv,
                            orig_submitter, orig_submit_time):
        '''run submit if any file opened

        description would be modified to indicate replication.
        @param desc, description of original change
        @param src_rev source revision replicated
        @param src_srv from which server this change is replicated
        @return new changelist number if there are opened files, otherwise None.
        '''
        opened = self.p4.run_opened()
        if not opened:
            return

        # remove #review from commit message
        # They trigger Swarm behaviour, and if it's #review-XXXX it
        # actually updates an existing review.
        desc = desc.replace('#review', '# review')

        desc = self.format_replicate_desc(desc, src_rev, src_srv,
                                          orig_submitter, orig_submit_time)

        result_lines = self.p4.run_submit('-d', desc)
        for result in result_lines:
            if 'submittedChange' in result:
                new_change = result['submittedChange']

        self.reverifyRevisions(result_lines)

        return new_change

    def update_change(self, new_changelist, orig_user, orig_date):
        '''update change with original user and date

        @param new_changelist new changelist num
        @param orig_user, string of user of original change
        @param orig_date, string of date of original change
        '''
        if not new_changelist or not orig_user or not orig_date:
            return

        # need to update the user and time stamp
        new_change = self.p4.fetch_change(new_changelist)

        new_change._user = orig_user
        orig_change_date = int(orig_date)

        # date in change is in epoch time, we need it in canonical form
        orig_utc_datetime = datetime.utcfromtimestamp(orig_change_date)
        new_change._date = orig_utc_datetime.strftime("%Y/%m/%d %H:%M:%S")

        self.logger.debug('%s %s' % (new_change._user, new_change._date))
        try:
            self.p4.save_change(new_change, '-f')

        except P4Exception:
            self.logger.error('"admin" perm needed for "p4 change -f"')
            raise

    def reverifyRevisions(self, result):
        revisionsToVerify = ["%s#%s,%s" % (x['refreshFile'], x['refreshRev'],
                                           x['refreshRev'])
                             for x in result
                             if 'refreshFile' in x]
        if revisionsToVerify:
            try:
                self.p4.run_verify('-qv', revisionsToVerify)

            except P4Exception as e:
                if "You don't have permission for this operation" not in str(
                        e):
                    raise

    def checkIntegration(self, file_change_rev, expectedResolveAction):
        localFile, targetDepotFile, action = (file_change_rev.localFile,
                                              file_change_rev.targetDepotFile,
                                              file_change_rev.action)

        fstats = self.p4.run_fstat('-Or', '-m1', localFile)
        if not fstats:
            msg = 'Failed to retrieve fstat for %s' % targetDepotFile
            raise RepP4Exception(msg)

        fstat = fstats[0]
        if 'action' not in fstat:
            pprint(fstats)
            msg = 'Failed to replicate action "%s" into ' \
                  'target %s' % (action, targetDepotFile)
            raise RepP4Exception(msg)

        if fstat['action'] != action:
            msg = 'Unexpected action "%s" for file %s. ' \
                  'Expected "%s"' % (fstat['action'], targetDepotFile, action)
            raise RepP4Exception(msg)

        resolveActions = fstat['resolveAction']
        msg = 'Unexpected resolveActions %s for file %s. ' \
              'Expected "%s"', (str(resolveActions),
                                targetDepotFile,
                                expectedResolveAction)

        num_integration = len(file_change_rev.integrations)
        if (len(resolveActions) < 1 or len(resolveActions) > num_integration + 1):
            raise RepP4Exception(msg)

        def resolve_action_variants(resolve_action):
            '''we consider the resolve actions in one group the same.  E.g. if
            target file was deleted before integration, resolve action
            'copy from' would become 'branch from'.
            '''
            acceptable_resolve_action_variants = (
                ('copy from', 'branch from'),)
            for variants in acceptable_resolve_action_variants:
                if resolve_action in variants:
                    return variants
            return (resolve_action, )

        resolve_actions = resolve_action_variants(expectedResolveAction)
        self.logger.debug("%s %s" % (expectedResolveAction, resolve_actions))
        if any(ra in resolveActions for ra in resolve_actions):
            pass
        else:
            raise RepP4Exception(msg)

        if (len(resolveActions) > num_integration and resolveActions[-1] != 'resolved'):
            raise RepP4Exception(msg)

    def translate_integration(self, src_integ, sourcePort):
        '''Sometimes, revisions of target files do not match that in src p4d,
        probably caused by 'obliterate' or inconsecurative
        replication.

        When detecting this, we need to find the correct revisions of
        target depot file for integration.

        # src_rev -> src_change -> dst_change -> dst_rev
        '''
        dst_depotFile, src_start_rev, src_end_rev = (src_integ.targetDepotFile,
                                                     src_integ.srev,
                                                     src_integ.erev)

        if not dst_depotFile or not src_integ.file:
            return

        src_p4 = self.src_p4
        dst_p4 = self.p4

        if not src_p4:
            return

        src_filelog = src_p4.run_filelog('-l', src_integ.file)
        dst_filelog = dst_p4.run_filelog('-l', src_integ.targetDepotFile)

        if not dst_filelog:
            msg = 'no file log for %s' % src_integ.targetDepotFile
            self.logger.warning(msg)
            raise RepP4Exception(msg)

        if not src_filelog:
            msg = 'no file log for %s' % src_integ.file
            self.logger.warning(msg)
            raise RepP4Exception(msg)

        def dt_to_epoch(dt):
            return (dt - datetime.utcfromtimestamp(0)).total_seconds()

        src_rev_changes = [(rev.rev, rev.change, dt_to_epoch(
            rev.time), rev.user) for rev in src_filelog[0].revisions]

        # find exact match of src srev/erev
        src_end_change = None
        src_end_user = None
        src_end_time = None

        src_start_change = None
        src_start_user = None
        src_start_time = None
        for rev, change, submit_time, submit_user in src_rev_changes:
            if rev == src_end_rev:
                src_end_change = change
                src_end_user = submit_user
                src_end_time = submit_time
            if rev == src_start_rev:
                src_start_change = change
                src_start_user = submit_user
                src_start_time = submit_time

        dst_rev_desc = [(rev.rev, rev.desc)
                        for rev in dst_filelog[0].revisions]
        # find exact match of dst erev
        dst_end_rev = None
        src_end_change_desc_prefix = self.format_replication_info(
            src_end_change, sourcePort, src_end_user, src_end_time)
        for rev, desc in dst_rev_desc:
            if src_end_change_desc_prefix in desc:
                dst_end_rev = rev

        dst_rev_desc.reverse()
        # find nearest of dst srev if no exact match
        dst_start_rev = dst_end_rev
        dst_start_rev_desc_prefix = self.format_replication_info(
            src_start_change, sourcePort, src_start_user, src_start_time)
        for rev, desc in dst_rev_desc:
            if dst_start_rev_desc_prefix in desc:
                dst_start_rev = rev

        if (src_integ.srev != dst_start_rev or src_integ.erev != dst_end_rev):
            msg = '%s srev/erev: %s/%s, now: %s/%s' % (dst_depotFile,
                                                       src_start_rev,
                                                       src_end_rev,
                                                       str(dst_start_rev),
                                                       str(dst_end_rev))
            self.logger.warning(msg)

        if dst_end_rev is None:
            src_rev_changes.reverse()
            dst_rev_desc_prev = [(rev, desc.split('\n')[0])
                                 for rev, desc in dst_rev_desc]
            msg = '\nsrc revs/changes: %s\n' % str(src_rev_changes)
            msg += 'dst revs/descs: %s' % str(dst_rev_desc_prev)
            self.logger.warning(msg)
            msg = 'Integration %s#%s not in target depot.' % (dst_depotFile,
                                                              src_end_rev)
            self.logger.warning(msg)
            raise RepP4Exception(msg)
        src_integ.srev = str(dst_start_rev)
        src_integ.erev = str(dst_end_rev)

    def _no_integrate(self, file_change_rev, integ):
        ftype, action, localFile, fixedLocalFile = (file_change_rev.type,
                                                    file_change_rev.action,
                                                    file_change_rev.localFile,
                                                    file_change_rev.fixedLocalFile)

        if integ.how in ('branch from', 'add from'):
            self.p4.run_add('-ft', ftype, fixedLocalFile)
        elif integ.how in ('delete from'):
            self.p4.run_delete('-v', localFile)
        elif integ.how in ('copy from'):
            self.logger.info("copy from: %s" % localFile)
            # handle edge case of ignored integration becoming a delete
            fstats = self.p4.run_fstat('-Or', '-m1', localFile)
            if fstats:
                fstat = fstats[0]
                if 'action' in fstat and fstat['action'] == 'delete':
                    self.p4.run_revert('-k', localFile)
                    self.p4.run_add('-ft', ftype, localFile)
                else:
                    self.p4.run_sync('-k', localFile)
                    self.p4.run_edit('-t', ftype, localFile)
            else:
                self.p4.run_add('-ft', ftype, fixedLocalFile)
        elif integ.how in ('merge from', 'edit from'):
            self.logger.info("mf|ef " + localFile)
            self.p4.run_sync('-k', localFile)
            self.p4.run_edit('-t', ftype, localFile)
        elif integ.how in ('ignored'):
            self.logger.info("ignored : %s %s " % (action, fixedLocalFile))
            self.p4.run_sync('-k', localFile)
            self.p4.run_edit(localFile)
        else:
            msg = 'Unexpected action %s for %s#%s' % (
                integ.how, file_change_rev.depotFile, file_change_rev.rev)
            raise RepP4Exception(msg)

    def replicate_file_integrate(self, file_change_rev, integ):
        if (self.cli_arguments.nointegrate or not integ.localFile or not integ.targetDepotFile):
            self._no_integrate(file_change_rev, integ)
            return

        partner = integ
        localFile, fixedLocalFile = (file_change_rev.localFile,
                                     file_change_rev.fixedLocalFile)
        partner_file_rev = '%s#%s,#%s' % (partner.targetDepotFile,
                                          partner.srev, partner.erev)

        if partner.how not in (
                'undid') and partner.targetDepotFile == self.depotmap.translate(localFile):
            # If file and partner file are the same, p4 integrate
            # doesn't work.
            partner.how = 'copy from'
        if not self.cli_arguments.allowmerge and partner.how == 'merge from':
            partner.how = 'edit from'

        if partner.how in ('add from'):
            self.p4.run_sync('-k', '%s#%s' %
                             (partner.targetDepotFile, partner.erev))
            self.p4.run_add('-ft', file_change_rev.type, fixedLocalFile)
        elif (partner.how in ('copy from') and partner.targetDepotFile == file_change_rev.targetDepotFile):
            # If file and partner file are the same, p4 integrate doesn't work.
            self.p4.run_sync('-k', file_change_rev.targetDepotFile)
            cmd = '-f "%s"#%s "%s"' % (partner.targetDepotFile,
                                       partner.erev,
                                       file_change_rev.targetDepotFile)
            self.p4.run_copy(shlex.split(cmd))

            # do not check integration
            return
        elif partner.how in ('branch from', 'delete from', 'copy from'):
            self.p4.run_integrate('-f', '-t', '-Rb', '-Rd', '-Di',
                                  partner_file_rev, localFile)
            self.p4.run_resolve('-at')
        elif partner.how in ('ignored'):
            self.p4.run_sync('-f', localFile)  # to avoid tamper checking

            self.p4.run_integrate('-f', '-t', '-Rb', '-Rd', '-Di',
                                  partner_file_rev, localFile)
            self.p4.run_resolve('-ay')
        elif partner.how in ('merge from'):
            self.p4.run_sync('-f', localFile)  # to avoid tamper checking
            if not os.path.isfile(localFile):
                partner_file_rev = '%s#%s' % (partner.targetDepotFile,
                                              partner.erev)
            self.p4.run_integrate(partner_file_rev, localFile)

            class MyResolver(Resolver):
                def resolve(self, mergeData):
                    return 'am'

            myResolver = MyResolver()
            self.p4.run_resolve(resolver=myResolver)

        elif partner.how in ('edit from'):
            tempFile = os.path.join(os.path.split(localFile)[0],
                                    str(uuid.uuid4()))
            shutil.copyfile(fixedLocalFile, tempFile)

            self.p4.run_sync('-f', localFile)  # to avoid tamper checking
            self.p4.run_integrate('-f', partner_file_rev, localFile)

            class MyResolver(Resolver):
                def __init__(self, edit_path):
                    self.edit_path = edit_path

                def resolve(self, mergeData):
                    os.remove(mergeData.result_path)
                    os.rename(self.edit_path, mergeData.result_path)
                    return 'ae'

            myResolver = MyResolver(tempFile)
            self.p4.run_resolve(resolver=myResolver)
            os.unlink(tempFile)
        elif partner.how in ('undid'):
            self.p4.run_undo(partner_file_rev)
        else:
            msg = 'Unexpected integration action %s' % partner.how
            raise RepP4Exception(msg)

        self.checkIntegration(file_change_rev, partner.how)

    def replicateIntegration(self, file_change_rev, source_port):
        if not file_change_rev.integrations:
            msg = 'No integration for %s#%s' % (file_change_rev.depotFile,
                                                file_change_rev.rev)
            raise RepP4Exception(msg)

        integrations = file_change_rev.integrations[:]

        if len(integrations) > 1:
            msg = 'integrations: %s' % pformat(integrations)
            self.logger.warning(msg)

        integ = integrations.pop()
        while integ.how == 'ignored' and integrations:
            integ = integrations.pop()

        if file_change_rev.action == 'delete':
            while not integ.how.startswith('delete') and integrations:
                integ = integrations.pop()

        try:
            if (not self.cli_arguments.nointegrate and integ.localFile and integ.targetDepotFile):
                self.translate_integration(integ, source_port)

        except RepP4Exception:
            msg = 'Abort integration, just add/edit the file.'
            self.logger.warning(msg)

            # add/edit/modify filetype
            self.p4.run_add('-ft', file_change_rev.type,
                            file_change_rev.fixedLocalFile)
            self.p4.run_edit(file_change_rev.localFile)
            self.p4.run_reopen('-t', file_change_rev.type,
                               file_change_rev.localFile)
            return

        self.replicate_file_integrate(file_change_rev, integ)

    def _replicate_move(self, file_change_rev, source_port):
        num_integs = len(file_change_rev.integrations)

        localFile_dir = os.path.split(file_change_rev.localFile)[0]
        tempFile = os.path.join(localFile_dir, str(uuid.uuid4()))
        shutil.copyfile(file_change_rev.fixedLocalFile, tempFile)

        # if the localFile doesn't exist in the depot, make it writeable
        fstats = self.p4.run_fstat('-m1', file_change_rev.localFile)
        if fstats:
            fstats = fstats[0]

        # fstats is neither 'delete' nor 'move/delete'
        file_exists_in_target = fstats and 'delete' not in fstats['headAction']
        if not file_exists_in_target:
            st = os.stat(file_change_rev.fixedLocalFile)
            os.chmod(file_change_rev.fixedLocalFile,
                     st.st_mode | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)

        if num_integs > 1:
            msg = '%s has multiple integrations: %s' % (
                file_change_rev.depotFile, file_change_rev.integrations)
            self.logger.warning(msg)

            # fall back to "edit" or "add"
            if file_exists_in_target:
                self.p4.run_edit(
                    '-k',
                    '-t',
                    file_change_rev.type,
                    file_change_rev.localFile)
                self.checkWarnings('edit (from)')
                shutil.copyfile(tempFile, file_change_rev.fixedLocalFile)
            else:
                self.p4.run_add(
                    '-ft',
                    file_change_rev.type,
                    file_change_rev.fixedLocalFile)

            return

        moved = False
        # sort integrations by "how", integrate 'moved from' first
        file_change_rev.integrations.sort(
            key=lambda x: not x.how.startswith('moved'))

        for idx, integ in enumerate(file_change_rev.integrations):
            self.logger.info('move integation index = %d' % idx)
            target_has_correct_revison = True
            try:
                self.translate_integration(integ, source_port)
            except RepP4Exception:
                target_has_correct_revison = False

            move_from_last_revision_of_file = True
            if integ.targetDepotFile and integ.how == 'moved from':
                integ_erev = int(integ.erev)
                movefrom_file = integ.targetDepotFile
                movefrom_file_filelog = self.p4.run_filelog(
                    '-m1', '%s#head' % movefrom_file)
                if not movefrom_file_filelog:
                    msg = 'Move from some non-exist file %d' \
                          'Add/delete instead of move/add move/delete' % (
                              integ_erev)
                    self.logger.error(msg)
                    move_from_last_revision_of_file = False
                else:
                    movefrom_file_headrev = movefrom_file_filelog[0].revisions[0].rev
                    if integ_erev < movefrom_file_headrev:
                        msg = 'Move from some non-last-revision of file %d < %s%d' \
                              'Add/delete instead of move/add move/delete' % (
                                  integ_erev, movefrom_file, movefrom_file_headrev)
                        self.logger.error(msg)
                        move_from_last_revision_of_file = False

            if (not self.cli_arguments.nointegrate and integ.localFile and integ.targetDepotFile and target_has_correct_revison and move_from_last_revision_of_file):
                self.logger.debug('integ.how = "%s"', integ.how)
                if integ.how in ('moved from'):
                    self.logger.debug(file_change_rev.localFile)
                    self.logger.debug('%s moved from %s', (file_change_rev.localFile, integ))
                    self.p4.run_sync(
                        '-f',
                        '{}#{}'.format(
                            integ.targetDepotFile,
                            integ.erev))
                    self.p4.run_edit(integ.targetDepotFile)
                    self.p4.run_move('-k', integ.targetDepotFile,
                                     file_change_rev.localFile)
                    moved = True

                    self.logger.debug(
                        'checkIntegration' + file_change_rev.depotFile)
                    self.checkIntegration(file_change_rev, integ.how)
                    self.logger.debug('checkIntegration - passed')
                else:
                    self.replicate_file_integrate(file_change_rev, integ)
            else:
                self.logger.info('integ.how = ' + integ.how)
                self.logger.info('replicateMove - else ' + file_change_rev.localFile)
                if integ.how in ('moved from'):
                    self.p4.run_add(
                        '-ft',
                        file_change_rev.type,
                        file_change_rev.fixedLocalFile)
                elif integ.how in ('branch from', 'merge from'):
                    # self.p4.run_edit('-k', '-t', file_change_rev.type, file_change_rev.localFile)
                    # self.checkWarnings('edit (move)')
                    shutil.copyfile(tempFile, file_change_rev.fixedLocalFile)
                elif integ.how in ('edit from'):
                    self.p4.run_edit(
                        '-k',
                        '-t',
                        file_change_rev.type,
                        file_change_rev.localFile)
                    self.checkWarnings('edit (from)')
                    shutil.copyfile(tempFile, file_change_rev.fixedLocalFile)
                elif integ.how in ('copy from') and moved:
                    continue
                elif integ.how in ('copy from') and not moved:
                    continue
                else:
                    msg = 'Unexpected action %s for %s#%s' % (
                        integ.how, file_change_rev.depotFile, file_change_rev.rev)
                    raise RepP4Exception()

        self.checkWarnings(file_change_rev.action)
