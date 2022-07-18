#!/usr/bin/python3

'''This script will be used to help identify branch points for feature
branches of WOT/WOWS

BENG-1790
'''
import argparse
import os

from lib.buildlogger import getLogger
from lib.p4server import P4Server
from lib.SvnPython import SvnPython
from lib.scmrep import get_revision_from_desc

logger = getLogger(__name__)


def get_arguments():
    '''Get cli arguments.
    @return args
    '''
    src_scm = 'SVN'
    dst_scm = 'P4'
    script_description = '''find svn branch src directory from perforce depot.

    This script
    1) reads src project dir and p4 depot of replicated branches form cli arguments,
    2) get log of first revision of src project dir,
    3) get its "copyfrom" branch and revision,
    4) and try to locate "copyfrom" branch/rev in target p4 depot.'''

    argparser = argparse.ArgumentParser(description=script_description)

    # configuration of src and target workspaces
    srcGroup = argparser.add_argument_group('source', 'source workspace sepc')
    tgtGroup = argparser.add_argument_group('target', 'target workspace sepc')

    src_example = 'svn://10.17.0.1:3690/repos'
    dst_example = 'Perforce:1666'
    srcGroup.add_argument('--source-port', required=True,
                          help='server:portnum, e.g. %s' % src_example)
    srcGroup.add_argument('--source-user', required=True,
                          help='source svn user')
    srcGroup.add_argument('--source-passwd', required=True,
                          help='source user password')
    srcGroup.add_argument('--source-project-dir', required=True,
                          help='project dir to be replicated, will be '
                          'concatenated after -source-port')

    tgtGroup.add_argument('--target-port', required=True,
                          help='server:portnum, e.g. %s' % dst_example)
    tgtGroup.add_argument('--target-user', required=True,
                          help='target perforce user')
    tgtGroup.add_argument('--target-passwd', required=True,
                          help='target user password')
    tgtGroup.add_argument('--target-rep-branch-root', required=True,
                          help='target depot for already replicated branches'
                          ', e.g. "//wows/remote"')

    # general config
    argparser.add_argument('-v', '--verbose', default='INFO',
                           choices=('DEBUG', 'INFO', 'WARNING',
                                    'ERROR', 'CRITICAL'),
                           help="Set level of logging")

    return argparser.parse_args()


def get_src_svn_branch_revision(svn, svn_proj_url):
    '''Get the log of 1st revision of src branch, return copyfrom_path,
    copyfrom_revision if any.

    @param svn, SvnPython instance
    @param svn_proj_url, string, svn url of project
    '''
    svn_1st_rev_log = svn.run_log(svn_proj_url)[0]
    changed_paths = svn_1st_rev_log['changed_paths']
    copyfrom_path = changed_paths[0]['copyfrom_path']
    branch_1st_rev = svn_1st_rev_log.revision.number

    if not copyfrom_path:
        logger.info(f'1st revision of {svn_proj_url} is not a branch operation')
        return None, None

    copyfrom_revision = changed_paths[0]['copyfrom_revision'].number
    return copyfrom_path, copyfrom_revision, branch_1st_rev


def get_copyfrom_branch_copy_revision(
        svn, svn_copyfrom_url, copyfrom_revision):
    # get "copyfrom" branch revisions
    # copyfrom_revision doesn't have to be in "copyfrom" branch
    # revisions. It could be somewhere between two "copyfrom" revisions.
    # e.g. in "copyfrom" branch, we have revision
    # r12301, r12302, r12350, r12399, r12400
    # it's possible that new branch was created at r12345, which was a
    # revision related to other branches.
    #
    # In this case, we return the biggest one of revisions that are
    # smaller than copyfrom_revision.
    svn_copy_from_revs = svn.run_log(svn_copyfrom_url,
                                     start_rev=1,
                                     end_rev=copyfrom_revision,
                                     limit=1)
    revs = [l.revision.number for l in svn_copy_from_revs]
    logger.info(f'Branched from {svn_copyfrom_url}@{copyfrom_revision}, closest rev in {svn_copyfrom_url} is {revs}')
    branch_revision = None
    if copyfrom_revision in revs:
        branch_revision = copyfrom_revision
    else:
        for src_rev in reversed(revs):
            if src_rev <= copyfrom_revision:
                branch_revision = src_rev
                break

    return branch_revision


def get_revision_num_from_desc(desc):
    default_description_rep_info_pattern = {
        'formatter': (
            'Imported from {srcserver}\n'
            'r{revision}|{submitter}|{submittime}'), 'extracter': (
                'Imported from (?P<srcserver>.+)\n'
                'r(?P<revision>[0-9]+)\|(?P<submitter>.+)\|(?P<submittime>.+)')}

    old_svnp4_rep_pattern = {
        'formatter': None, 'extracter': (
            'Automated import from SVN:\n+'
            'r(?P<revision>[0-9]+)\|(?P<submitter>.+)\|(?P<submittime>.+)')}

    old_svnp4_rep_reconcile_pattern = {
        'formatter': None, 'extracter': (
            'update perforce to match svn revision (?P<revision1>[0-9]+)\n+'
            'r(?P<revision>[0-9]+)\|(?P<submitter>.+)\|(?P<submittime>.+)')}

    for pat in [default_description_rep_info_pattern,
                old_svnp4_rep_pattern,
                old_svnp4_rep_reconcile_pattern, ]:
        rev = get_revision_from_desc(desc, pattern=pat)
        if rev:
            return rev

    return 0


def detect_branch_point(args):
    svn_repo_url, svn_user, svn_passwd = (args.source_port,
                                          args.source_user,
                                          args.source_passwd)
    p4_port, p4_user, p4_passwd = (args.target_port, args.target_user,
                                   args.target_passwd)
    svn_project_dir = args.source_project_dir.strip()

    # get src branch info
    svn = SvnPython(svn_repo_url, svn_user, svn_passwd, '/tmp/arbitrary_dir')
    svn_proj_url = os.path.join(svn_repo_url, svn_project_dir[1:])
    copyfrom_path, copyfrom_revision, branch_1st_rev = get_src_svn_branch_revision(
        svn, svn_proj_url)
    if not copyfrom_path:
        msg = '1st revision is not a branch'
        logger.error(msg)
        return
    logger.info(f'src svn branch is copied from {copyfrom_path}@{copyfrom_revision}')

    svn_copyfrom_url = os.path.join(svn_repo_url, copyfrom_path[1:])
    branch_revision = get_copyfrom_branch_copy_revision(svn, svn_copyfrom_url,
                                                        copyfrom_revision)
    if branch_revision is None:
        msg = 'failed to find copyfrom_rev in svn ' \
              f'"from" branch : {branch_revision} ({revs})'
        logger.error(msg)
        return

    p4_branch_dir = None
    p4_branch_rev = None
    # look for corresponding changelist in p4 depot
    dst_p4 = P4Server(p4_port, p4_user, p4_passwd)
    p4_replicated_dirs = dst_p4.run_dirs(args.target_rep_branch_root + '/*')
    logger.debug(f'p4_replicated_dirs: {p4_replicated_dirs}')
    for d in [d.get('dir') for d in p4_replicated_dirs]:
        change = dst_p4.run_changes('-m1', '-l', '%s/...' % d)[0]
        if not change:
            continue

        if svn_repo_url not in change['desc']:
            logger.debug(f"{svn_repo_url} not found in {change['desc']}")
            continue

        logger.info(f'{svn_repo_url} found in {d}')

        changes = dst_p4.run_changes('-l', '%s/...' % d)
        for c in changes:
            desc = c['desc']

            #replicated_rev = get_revision_from_desc(desc)
            replicated_rev = get_revision_num_from_desc(desc)
            if int(replicated_rev) == branch_revision:
                p4_branch_dir = d
                p4_branch_rev = c['change']
                break

        if p4_branch_dir and p4_branch_rev:
            break

    if not p4_branch_dir:
        return None

    branch_from = f'{p4_branch_dir}/...@{p4_branch_rev}'
    return branch_from, branch_1st_rev


if __name__ == '__main__':
    args = get_arguments()
    logger.setLevel(args.verbose)

    branch_from, branch_1st_rev = detect_branch_point(args)
    msg = f'Please try to branch from {branch_from}. '
    msg += f'And use {branch_1st_rev} as --source-counter in replication job'
    logger.info(msg)
