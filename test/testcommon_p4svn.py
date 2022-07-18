#!/usr/bin/python3

'''test replication of depots in svn repository.
'''

import os
import re
import shutil
import tempfile
import P4SvnReplicate as P4Svn
from testcommon import (BUILD_TEST_P4D_USER,
                        BuildTestException,
                        scriptRootDir,)
from lib.p4server import P4Server
from lib.buildcommon import get_dir_file_hash
from lib.buildlogger import getLogger
from lib.SvnPython import SvnPython
from replicationunittest import (run_replication_in_container)
from testcommon_svnp4 import (update_p4d_changed_files,
                              update_svn_changed_files,)

logger = getLogger(__name__)
logger.setLevel('INFO')


def replicate_P4SvnReplicate(src_mapping, dst_mapping,
                             src_docker_cli, dst_docker_cli,
                             **kwargs):
    '''generate cfg and call P4P4Replicate.replicate() to replicate

    @param src_mapping [in] list of (dst_depot, './...')
    @param dst_mapping [in] list of (src_repository, '')
    @param src_docker_cli [in] instance of DockerClient, container
    should be up and running
    @param dst_docker_cli [in] target instance of DockerClient
    @param src_counter [in] optional int, last replicated change id
    @param replicate_change_num [in] optional int, number of changes to replicate
    @param source_last_changeset [in] optional int, last changeset to replicate
    '''
    p4_user = BUILD_TEST_P4D_USER
    svn_user = ''
    svn_passwd = ''
    src_ip = src_docker_cli.get_container_ip_addr()
    dst_ip = dst_docker_cli.get_container_ip_addr()

    def create_ws_mapping_file(ws_mapping):
        cfgFd, cfgPath = tempfile.mkstemp(
            suffix='.cfg', text=True, dir=os.path.join(
                scriptRootDir, 'test/replication'))
        os.write(cfgFd, str.encode(
            '\n'.join([' '.join(_) for _ in ws_mapping])))
        os.close(cfgFd)
        return cfgPath

    class ReplicateCmdArgs:
        pass

    src_counter = kwargs.get('src_counter', 0)
    replicate_change_num = kwargs.get('replicate_change_num', 0)
    source_last_changeset = kwargs.get('source_last_changeset', None)
    ws_root = kwargs.get('ws_root')
    if not ws_root:
        ws_root = tempfile.mkdtemp(
            prefix='buildtest', dir=os.path.join(
                scriptRootDir, 'test/replication'))

    args = ReplicateCmdArgs()
    args.source_port = '%s:1666' % src_ip
    args.source_user = p4_user
    args.source_passwd = ' '
    args.source_counter = src_counter
    args.source_workspace_view_cfgfile = create_ws_mapping_file(src_mapping)

    args.target_port = 'svn://%s:3690/repos' % dst_ip
    args.target_user = svn_user
    args.target_passwd = svn_passwd
    args.target_workspace_view_cfgfile = create_ws_mapping_file(dst_mapping)

    args.workspace_root = ws_root
    args.maximum = None if replicate_change_num == 0 else replicate_change_num
    args.source_last_changeset = source_last_changeset
    #args.replicate_user_and_timestamp = True
    args.logging_color_format = 'console'
    args.verbose = 'INFO'

    try:
        if os.environ.get("TEST_IN_HOST"):
            P4Svn.replicate(args)
        else:
            script = './P4SvnReplicate.py'
            run_replication_in_container(script, args)
    finally:
        os.unlink(args.source_workspace_view_cfgfile)
        os.unlink(args.target_workspace_view_cfgfile)
        shutil.rmtree(ws_root)


def get_p4_revision_from_svn_changelog(svn, svn_revision):
    output = svn.run_log(start_rev=svn_revision, end_rev=svn_revision)[0]
    message = output['message']

    last_line = message.split('\n')[-1]
    re_pattern = r'r(?P<revision>[0-9]+)\|(?P<submitter>.+)\|(?P<submittime>.+)'

    match = re.match(re_pattern, last_line)
    if match:
        return match.group('revision')
    return 0


def verify_changes(src_p4d, dst_svn, src_root, dst_root, svn_project_subdir,
                   src_changes, dst_changes):
    '''Verify if files modified by src/dst_changes have the same contents

    @param src_svn source svn server instance
    @param dst_p4d target p4d server instance
    @param src_root source svn working copy directory
    @param dst_root target p4 workspace directory
    @param svn_project_subdir project subdir
    @param src_changes, list of svn changesets
    @param dst_changes, list of p4 changelists
    '''

    src_depot_abspath_map = src_p4d.get_depot_path_map()

    src_file_hash = {}
    dst_file_hash = {}

    #src_dst_changes = zip(src_changes, dst_changes)
    # for src_change, dst_change in src_dst_changes:
    for dst_change in dst_changes:
        src_change = get_p4_revision_from_svn_changelog(dst_svn, dst_change)
        if not src_change:
            continue

        if src_change not in src_changes:
            raise BuildTestException('%s not in src p4 changes' % src_change)

        logger.info('verifying p4 change %s' % src_change)

        src_files, src_msg = update_p4d_changed_files(src_p4d,
                                                      src_root,
                                                      src_change,
                                                      src_depot_abspath_map)
        src_file_hash = get_dir_file_hash(src_root, detect_dir=True)

        dst_files, dst_msg = update_svn_changed_files(
            dst_svn, dst_change, dst_root)
        if svn_project_subdir:
            logger.debug('svn_project_subdir: %s' % svn_project_subdir)
            svn_project_subdir_path = os.path.join(
                dst_root, svn_project_subdir[1:])
            dst_file_hash = get_dir_file_hash(svn_project_subdir_path,
                                              exclude=['.svn', ],
                                              detect_dir=True)
        else:
            dst_file_hash = get_dir_file_hash(dst_root,
                                              exclude=['.svn', ],
                                              detect_dir=True)

        src_msg_lines = src_msg.split('\n')
        dst_msg_lines = dst_msg.split('\n')
        src_msg_lines = list(map(str.strip, src_msg_lines))
        dst_msg_lines = list(map(str.strip, dst_msg_lines))
        # remove empty lines
        src_msg_lines = [_f for _f in src_msg_lines if _f]
        dst_msg_lines = [_f for _f in dst_msg_lines if _f]

        if not set(src_msg_lines).issubset(set(dst_msg_lines)):
            logger.error('src message: %s' % src_msg_lines)
            logger.error('dst message: %s' % dst_msg_lines)
            raise BuildTestException('commit message not correctly replicated')

        # pprint(src_file_hash)
        # pprint(dst_file_hash)
        if src_file_hash != dst_file_hash:
            for src_f, src_v in list(src_file_hash.items()):
                dst_f = src_f
                dst_v = dst_file_hash.get(src_f)
                if src_v != dst_v:
                    src_f = os.path.normpath(os.path.join(src_root, src_f))
                    dst_f = os.path.normpath(os.path.join(dst_root, dst_f))
                    logger.error('%s : %s' % (src_f, src_v))
                    logger.error('%s : %s' % (dst_f, dst_v))
            raise BuildTestException('replication failed')


def verify_replication(src_mapping, dst_mapping,
                       src_docker_cli, dst_docker_cli,
                       **kwargs):
    '''simple verification for Svn2P4 replication

    @param src_mapping, perforce view mapping
    @param dst_mapping, ((src_repo_dir, './...')) mapping, we use the
                        same format as p4 mapping for simplicity
    @param src_docker_cli, source docker instance
    @param dst_docker_cli, target docker instance
    @param src_counter, optional, source counter changeset
    @param replicate_change_num, optional, number of changes to replicate

    '''
    src_counter = int(kwargs.get('src_counter', 0))
    replicate_change_num = kwargs.get('replicate_change_num', 0)
    source_last_changeset = kwargs.get('source_last_changeset', 0)

    p4_user = BUILD_TEST_P4D_USER
    svn_user = ''
    svn_pass = ''
    src_ip = src_docker_cli.get_container_ip_addr()
    dst_ip = dst_docker_cli.get_container_ip_addr()
    svn_dir = dst_mapping[0][0]

    src_root = tempfile.mkdtemp(prefix='buildtest_src')
    dst_root = tempfile.mkdtemp(prefix='buildtest_dst')

    src_p4d = P4Server('%s:1666' % src_ip, p4_user)
    dst_svn = SvnPython('svn://%s:3690/repos' % dst_ip,
                        svn_user, svn_pass, dst_root)

    #src_svn.checkout_working_copy(svn_dir, src_counter, depth='infinity')
    svn_project_dir = '/' + [d for d in svn_dir.split('/') if d][0]
    svn_project_subdir = ''
    if svn_project_dir != svn_dir:
        svn_project_subdir = svn_dir[len(svn_project_dir):]
    dst_svn.checkout_working_copy(svn_project_dir, 0, depth='infinity')

    src_ws_mapping = list(map(P4Server.WorkspaceMapping._make, src_mapping))
    src_p4d.create_workspace(src_ws_mapping, ws_root=src_root)

    src_start_change = src_counter

    try:
        dst_start_change = 0
        src_changes = src_p4d.run_changes('-l',
                                          '...@%d,#head' % src_start_change)
        src_changes = [c['change'] for c in src_changes]
        dst_changes = dst_svn.get_revision_list(svn_dir,
                                                start_rev=dst_start_change)

        src_changes.reverse()
        if src_changes and str(src_changes[0]) == str(src_start_change):
            src_changes = src_changes[1:]

        # compare only the 'replicate_change_num' changes
        if replicate_change_num:
            src_changes = src_changes[:replicate_change_num]

        if source_last_changeset:
            idx = src_changes.index(str(source_last_changeset))
            src_changes = src_changes[:idx + 1]

        dst_changes = dst_changes[-len(src_changes):]
        #print('src->dst : %s' % pformat(zip(src_changes, dst_changes)))

        verify_changes(
            src_p4d,
            dst_svn,
            src_root,
            dst_root,
            svn_project_subdir,
            src_changes,
            dst_changes)
    finally:
        logger.info('src root: %s' % src_root)
        logger.info('dst root: %s' % dst_root)

        dst_svn.client = None
        src_p4d.delete_workspace()
        shutil.rmtree(src_root)
        shutil.rmtree(dst_root)
