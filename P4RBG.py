#!/usr/bin/python3

import argparse

from lib.buildlogger import getLogger
from lib.P4ReleaseBranchGenerate import release_branch_generate
logger = getLogger(__name__)


def getArguments():
    '''Get cli arguments. '''

    script_description = '''Script to generate release branch'''

    argparser = argparse.ArgumentParser(description=script_description)

    # configuration of src and target workspaces
    srcGroup = argparser.add_argument_group('source', 'source workspace sepc')
    # Commenting following variable as it is not being used
#    tgtGroup = argparser.add_argument_group('target', 'target workspace sepc')

    srcGroup.add_argument('--p4-port', required=True,
                          help='server:portnum, e.g. Perforce:1666')
    srcGroup.add_argument('--p4-user', required=True,
                          help='perforce user')
    srcGroup.add_argument('--p4-passwd', required=True,
                          help='user password')
    srcGroup.add_argument('--source-branch-dir', required=True,
                          help='p4 depot location of source branch')
    srcGroup.add_argument('--target-branch-dir', required=True,
                          help='p4 depot location of target branch')

    # extra config of workspace
    argparser.add_argument('-m', '--maximum', type=int,
                           help='maximum number of change to replicate')

    # last changelist to copy
    srcGroup.add_argument('--source-last-changeset', default=None, type=int,
                          help='last changeset to copy, default #head')

    # general config
    argparser.add_argument(
        '--replicate-user-and-timestamp',
        action='store_true',
        help='Enable replication of user and timestamp '
        'of source changelist. NOTE! needs "admin" '
        'access for this operation.')
    argparser.add_argument(
        '--repopulate-change-properties',
        action='store_true',
        help='back-fill copied changeslist with original '
        'submitter and timestamp of source changelist. '
        'NOTE! also needs "admin" access for this operation.')
    argparser.add_argument('--dry-run', action='store_true',
                           help='print the revisions to copy, but not copy')
    argparser.add_argument('-v', '--verbose', default='INFO',
                           choices=('DEBUG', 'INFO', 'WARNING',
                                    'ERROR', 'CRITICAL'),
                           help="Set level of logging")

    return argparser.parse_args()


def branch_generate():
    args = getArguments()

    release_branch_generate(
        args.p4_port,
        args.p4_user,
        args.p4_passwd,
        args.source_branch_dir,
        args.target_branch_dir,
        replicate_user_and_timestamp=args.replicate_user_and_timestamp,
        repopulate_change_properties=args.repopulate_change_properties,
        maximum=args.maximum,
        source_last_revision=args.source_last_changeset,
        dry_run=args.dry_run,
        verbose=args.verbose)


if __name__ == '__main__':
    branch_generate()
