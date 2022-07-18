#!/usr/bin/python3
# -*- coding: utf-8 -*-

# PerforceReplicate.py
#
# This python script replicates changelists from one perforce server
# to another perforce server.  It attempts to reproduce, as faithfully
# as possible the exact history of operations for every file.
#

##########################################################################
# This script was based on PerforceTransfer.py.  Original copyright notice follows.
##########################################################################
# Copyright (c) 2011 Sven Erik Knop, Perforce Software Ltd
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1.  Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
# 2.  Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the
#      distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL PERFORCE
# SOFTWARE, INC. BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# User contributed content on the Perforce Public Depot is not supported by Perforce,
# although it may be supported by its author. This applies to all contributions
# even those submitted by Perforce employees.
#


import argparse
import logging
import os
import re
import sys
import traceback
from pprint import pformat

from configparser import ConfigParser

from .buildlogger import getLogger
from P4 import P4Exception
from .scmp4 import (ReplicationP4, RepP4Exception)
from . import scm2scm

CONFIG = 'transfer.cfg'
GENERAL_SECTION = 'general'
SOURCE_SECTION = 'source'
TARGET_SECTION = 'target'

LOGGER_NAME = "transfer"


class P4TransferException(scm2scm.ReplicationException):
    pass


class P4Transfer(scm2scm.Replication):

    def __init__(self, *argv):
        self.cli_arguments = self.parse_cli_arguments()

        self.logger = getLogger(LOGGER_NAME)
        self.logger.setLevel(self.cli_arguments.verbose)
        self.create_config_parser()
        self.create_scms()

        # default replication info to be added in description of new changes
        # rep_info_formatter = 'Automated import from perforce ' \
        #                     'change {revision} from {srcserver}'
        # rep_info_extracter = 'Automated import from perforce ' \
        #                     'change (?P<revision>[0-9]+) from (?P<srcserver>.+)'
        # self.target.set_desc_rep_info_pattern(rep_info_formatter,
        #                                      rep_info_extracter)

    def parse_cli_arguments(self):
        parser = argparse.ArgumentParser(
            description="PerforceReplicate",
            epilog="Copyright (C) 2013 Sven Erik Knop, Perforce Software Ltd"
        )

        parser.add_argument('-n', '--dry-run', action='store_true',
                            help="Preview only, no transfer")
        parser.add_argument('-c', '--config', default=CONFIG,
                            help="Default is " + CONFIG)
        parser.add_argument('-m', '--maximum', default=None, type=int,
                            help="maximum number of changes to transfer")
        parser.add_argument('--base', action='store_true',
                            help="Add all files from the source to an empty destination")
        parser.add_argument(
            '-v',
            '--verbose',
            nargs='?',
            const="INFO",
            default="WARNING",
            choices=(
                'DEBUG',
                'WARNING',
                'INFO',
                'ERROR',
                'FATAL'),
            help="Various levels of debug output")
        parser.add_argument('-ni', '--nointegrate', action='store_true')
        parser.add_argument('-am', '--allowmerge', action='store_true')
        parser.add_argument(
            '--replicate-user-and-timestamp',
            action='store_true',
            help='Enable replication of user and timestamp '
            'of source changelist. NOTE! needs "admin" '
            'access for this operation')
        parser.add_argument(
            '--prefix-description-with-replication-info',
            action='store_true',
            help=(
                'if set, add replication info before original'
                ' description. by default, after it'))

        return parser.parse_args()

    def create_config_parser(self):
        '''create a config parser for cfg file
        '''
        self.parser = ConfigParser()
        self.parser.readfp(open(self.cli_arguments.config))

        if not self.parser.has_section(GENERAL_SECTION):
            return

        if self.parser.has_option(GENERAL_SECTION, "LOGFILE"):
            logfile = self.parser.get(GENERAL_SECTION, "LOGFILE")

            fh = logging.FileHandler(logfile)
            fh.setLevel(self.cli_arguments.verbose)

            log_fmt = '%(asctime)s - %(levelname)s - %(message)s'
            date_fmt = '%m/%d/%Y %H:%M:%S'
            formatter = logging.Formatter(log_fmt, datefmt=date_fmt)
            fh.setFormatter(formatter)

            self.logger.addHandler(fh)

    def verify_work_dir_root(self):
        '''Verify Svn working copy dir is the same as the p4 workspace
        '''
        src_ws_root = self.source.root
        dst_ws_root = self.target.root

        if src_ws_root != dst_ws_root:
            msg = 'src/dst workspace root directories must be the same'
            raise P4TransferException(msg)

    def get_latest_revision(self, src_p4, filename):
        self.logger.info("This is the filename: %s" % filename)
        try:
            revision_line = src_p4.run('files', filename)
        except P4Exception as e:
            self.logger.error(e)
        revision_number = revision_line[0]['rev']
        self.logger.info("Revision number is %s" % revision_number)
        return revision_number

    def ignoring_purged_revision(self, src_p4, change_rev):
        if re.search(r'\+.*S', change_rev.type):
            resultado = re.match(r'.*\+.*S(\d+)', change_rev.type)
            if resultado:
                allowed_revisions = int(resultado.group(1))
            else:
                allowed_revisions = 1
            revisions = int(change_rev.rev)
            latest_revision = int(self.get_latest_revision(src_p4, change_rev.localFile))
            if revisions <= latest_revision - allowed_revisions:
                return True
        return False

    def replication_sanity_check(self, src_p4, dst_p4,
                                 src_change_revs, dst_changelist):
        '''replication sanity check

        For now, we compare the "digest", i.e. md5, of replicated
        files with that from source p4 changes.

        @param src_change_revs ChangeRevision instances from source
        @param dst_changelist new changelist submited in target p4 depot
        '''
        if not dst_changelist:
            return

        if len(src_change_revs) > 2000:
            # if we have too many files, skip sanity check
            return

        if src_p4.is_unicode_server() != dst_p4.is_unicode_server():
            return

        self.logger.info('Verifying changelist %s' % dst_changelist)
        dst_describe = dst_p4.run_describe(dst_changelist)[0]

        changes_to_ignore = len([x for x in src_change_revs if self.ignoring_purged_revision(src_p4, x)])
        self.logger.info("Listing changes to ignore %s" % changes_to_ignore)
        src_depotfiles = ['%s#%s' % (src_change.depotFile, src_change.rev)
                          for src_change in src_change_revs
                          if (self.source.file_in_workspace(src_change.localFile) and self.target.file_in_workspace(src_change.localFile))]
        dst_depotfiles = ['%s#head' % fn for fn in dst_describe['depotFile']]

        src_fstats = src_p4.run_fstat('-Ol', '-m1', *src_depotfiles)
        dst_fstats = dst_p4.run_fstat('-Ol', '-m1', *dst_depotfiles)

        src_digests = [
            (os.path.split(
                self.source.localmap.translate(
                    fv.get('depotFile')))[1],
                fv.get('digest')) for fv in src_fstats]
        dst_digests = [
            (os.path.split(
                self.target.localmap.translate(
                    fv.get('depotFile')))[1],
                fv.get('digest')) for fv in dst_fstats]
        src_digests = [d for d in src_digests if d[1]]
        dst_digests = [d for d in dst_digests if d[1]]
        src_digests.sort()
        dst_digests.sort()

        if src_digests != dst_digests:
            distinct_digest = len(set(src_digests) - set(dst_digests))
            self.logger.info("The number of changes to ignore is: %s" % changes_to_ignore)
            if distinct_digest != changes_to_ignore:
                self.logger.info("The number of changes to ignore is out of range")
                # everything
                # ignore case difference
                src_digests = [(d[0].lower(), d[1]) for d in src_digests]
                dst_digests = [(d[0].lower(), d[1]) for d in dst_digests]
                if src_digests != dst_digests:
                    msg = '\nsrc digests %s != \ndst digests %s\n' % (pformat(src_digests),
                                                                      pformat(dst_digests))
                    self.logger.error(msg)
                    # diff
                    src_digest_set = set(src_digests)
                    dst_digest_set = set(dst_digests)
                    src_diff = src_digest_set - dst_digest_set
                    dst_diff = dst_digest_set - src_digest_set
                    msg = '\nsrc digests %s != \ndst digests %s\n' % (pformat(src_diff), pformat(dst_diff))
                    self.logger.error(msg)

                    msg = 'Please verify and obliterate ' \
                          'changelist %s if it is not a false negative' % dst_changelist
                    raise RepP4Exception(msg)

        self.logger.info("Verified p4 changelist %s" % dst_changelist)

    def create_scms(self):
        '''Create SCMs for replication

        self.parser should be instantiated before this method
        '''
        self.source = ReplicationP4(SOURCE_SECTION, self.parser,
                                    self.cli_arguments,
                                    self.cli_arguments.verbose)
        self.target = ReplicationP4(TARGET_SECTION, self.parser,
                                    self.cli_arguments,
                                    self.cli_arguments.verbose)

        self.source.connect()
        self.target.connect()
        self.verify_work_dir_root()

        # Record the Players
        self.logger.info(self.source)
        self.logger.info(self.target)

        self.target.src_p4 = self.source.p4

    def replicate(self):
        '''performs the replication between src and target
        '''
        self.calc_start_changelist()

        p4_changes = self.source.get_changes_to_replicate()

        num_changes = len(p4_changes)
        p4_change_nums = [p['change'] for p in p4_changes]

        if self.cli_arguments.base:
            self.logger.info('Sync source to : %s' % self.source.counter)
            self.source.sync_to_change(self.source.counter)
            self.target.add_base(self.source.counter, self.source.get_base_change_to_replicate(), self.source)
            return p4_change_nums

        self.logger.info('Changes to replicate: %s' % p4_change_nums)

        if self.cli_arguments.dry_run:
            self.source.disconnect()
            self.target.disconnect()
            return p4_change_nums
        try:
            for idx, p4_change in enumerate(p4_changes):
                src_changelist = p4_change['change']
                self.logger.info('Replicating : %s' % src_changelist)

                # get it, replicate it
                sync_result = self.source.sync_to_change(src_changelist)
                change_files = self.source.get_change(
                    src_changelist, sync_result)
                resultedChange = self.target.replicate_change(
                    src_changelist, change_files, p4_change, self.source)

                msg = "Replicated : %s -> %s, %d of %d" % (src_changelist,
                                                           resultedChange,
                                                           idx + 1,
                                                           num_changes)
                self.logger.info(msg)

                self.logger.info("List of files to be changed: %s", change_files)
                # sanity check
                self.replication_sanity_check(self.source.p4, self.target.p4,
                                              change_files, resultedChange)

        except (P4Exception, RepP4Exception, P4TransferException) as e:
            self.logger.error(e)
            self.logger.error(traceback.format_exc())

            raise
        finally:
            self.target.revertChanges()

            self.source.disconnect()
            self.target.disconnect()


def PerforceToPerforce():
    prog = P4Transfer(*sys.argv[1:])
    return prog.replicate()


if __name__ == '__main__':
    PerforceToPerforce()
