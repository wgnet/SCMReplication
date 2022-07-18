#!/usr/bin/python3

'''test replication of depots in svn repository.
'''

import os
import shutil
import tempfile
from contextlib import contextmanager
from testcommon import (BUILD_TEST_P4D_USER,
                        BuildTestException,
                        scriptRootDir,)
from lib.p4server import P4Server
from lib.buildcommon import (working_in_dir, get_dir_file_hash,
                             remove_dir_contents,
                             generate_random_str,)
from lib.buildlogger import getLogger
from lib.SvnPython import SvnPython
from replicationunittest import run_replication_in_container

logger = getLogger(__name__)
logger.setLevel('INFO')


def create_ws_mapping_file(ws_mapping):
    cfgFd, cfgPath = tempfile.mkstemp(
        suffix='.cfg', text=True, dir=os.path.join(
            scriptRootDir, './test/replication'))
    os.write(cfgFd, str.encode('\n'.join([' '.join(_) for _ in ws_mapping])))
    os.close(cfgFd)
    return cfgPath


def replicate_SvnP4Replicate(src_mapping, dst_mapping,
                             src_docker_cli, dst_docker_cli,
                             **kwargs):
    '''generate cfg and call P4P4Replicate.replicate() to replicate

    @param src_mapping [in] list of (src_repository, '')
    @param dst_mapping [in] list of (dst_depot, './...')
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

    class ReplicateCmdArgs:
        pass

    prefix_repinfo = kwargs.get('prefix_repinfo', False)
    src_counter = kwargs.get('src_counter', 0)
    replicate_change_num = kwargs.get('replicate_change_num', 0)
    source_last_changeset = kwargs.get('source_last_changeset', None)
    svn_ignore_externals = kwargs.get('svn_ignore_externals', None)
    ws_root = kwargs.get('ws_root')
    if not ws_root:
        ws_root = tempfile.mkdtemp(
            prefix='buildtest', dir=os.path.join(
                scriptRootDir, './test/replication'))

    args = ReplicateCmdArgs()
    args.source_port = 'svn://%s:3690/repos' % src_ip
    args.source_user = svn_user
    args.source_passwd = svn_passwd
    args.source_counter = src_counter
    args.source_workspace_view_cfgfile = create_ws_mapping_file(src_mapping)
    if svn_ignore_externals is not None:
        args.svn_ignore_externals = svn_ignore_externals

    args.target_port = '%s:1666' % dst_ip
    args.target_user = p4_user
    args.target_passwd = ' '
    args.target_workspace_view_cfgfile = create_ws_mapping_file(dst_mapping)

    args.workspace_root = ws_root
    args.maximum = None if replicate_change_num == 0 else replicate_change_num
    args.source_last_changeset = source_last_changeset
    args.replicate_user_and_timestamp = True
    args.prefix_description_with_replication_info = prefix_repinfo
    args.logging_color_format = 'console'
    args.verbose = 'INFO'

    try:
        if os.environ.get("TEST_IN_HOST"):
            import SvnP4Replicate as SvnP4
            SvnP4.replicate(args)
        else:
            script = './SvnP4Replicate.py'
            run_replication_in_container(script, args)
    finally:
        shutil.rmtree(ws_root)
        os.remove(args.source_workspace_view_cfgfile)
        os.remove(args.target_workspace_view_cfgfile)

    return args


def update_svn_changed_files(svn, changeset, ws_root,
                             svn_ignore_externals=False):
    '''update svn working copy to changeset and return changed files.

    @param svn, SvnPython instance
    @param changeset, svn changeset to update to
    @param ws_root, svn working copy directory
    @return file paths modified by this changeset.
    '''
    try:
        update_arg = ''
        if svn_ignore_externals:
            update_arg = '--ignore-externals'
        svn.run_update(ws_root, changeset, update_arg=update_arg)
    except Exception as e:
        logger.error('updating %s@%s, got %s' % (ws_root, changeset, str(e)))
        pass

    output = svn.run_log(start_rev=changeset, end_rev=changeset)[0]
    message = output['message']
    paths = output['changed_paths']

    wc_info = svn.run_info2(ws_root)
    project_dir = '/' + wc_info[0][0]
    '''
    for info in wc_info:
        logger.info('wc_info of %s' % info[0])
        for k in info[1].keys():
            logger.info( 'wc_info1.%s: %s' % (k, getattr(info[1], k)))
    '''

    # remove files that are not in current project
    paths = [p for p in paths if p['path'].startswith(project_dir)]

    svn_paths = []
    for p in paths:
        action, path = p['action'], p['path']
        abs_path = ws_root + path[len(project_dir):]
        kind = 'dir' if os.path.isdir(abs_path) else 'file'
        if kind == 'file' and action != 'D':
            svn_paths.append(abs_path)
        elif False:
            logger.warning('excluded: %s' % p)

    return svn_paths, message


def update_p4d_changed_files(p4d, ws_root, changelist, depot_path_map):
    '''update p4 workspace to changelist and return changed files.

    @param p4d, p4server instance
    @param ws_root, workspace directory
    @param changelist, changelist to update to
    @param depot_path_map, p4 depot to abspath mapping
    @return file paths modified by this changelist
    '''
    remove_dir_contents(ws_root)
    p4d.run_sync('-f', '...@%s' % changelist)
    p4_desc = p4d.run_describe(changelist)[-1]

    actions = p4_desc['action']
    depotFiles = p4_desc['depotFile']
    message = p4_desc['desc']

    for idx, action in enumerate(actions):
        if action == 'delete':
            depotFiles[idx] = None

    def translate_p4_filename(fn):
        fn = fn.replace("%40", "@")
        fn = fn.replace("%23", "#")
        fn = fn.replace("%2A", "*")
        fn = fn.replace("%25", "%")
        return fn

    depotFiles = [_f for _f in depotFiles if _f]
    depotFiles = list(map(translate_p4_filename, depotFiles))

    p4_paths = list(map(depot_path_map.translate, depotFiles))

    return p4_paths, message


def verify_changes(src_svn, dst_p4d, src_root, dst_root,
                   svn_project_subdir, src_changes, dst_changes,
                   prefix_repinfo, svn_ignore_externals,
                   excluded_subdirs, excluded_files):
    '''Verify if files modified by src/dst_changes have the same contents

    @param src_svn source svn server instance
    @param dst_p4d target p4d server instance
    @param src_root source svn working copy directory
    @param dst_root target p4 workspace directory
    @param svn_project_subdir project subdir
    @param src_changes, list of svn changesets
    @param dst_changes, list of p4 changelists
    @param prefix_repinfo, repinfo is placed before commit message
    '''

    dst_changes_iter = iter(dst_changes)
    src_changes_iter = iter(src_changes)

    dst_depot_abspath_map = dst_p4d.get_depot_path_map()

    src_file_hash = {}
    dst_file_hash = {}

    excluded_subdirs.append('.svn')
    for dst_change in dst_changes_iter:
        logger.info('verifying p4 change %s' % dst_change)

        dst_files, dst_msg = update_p4d_changed_files(
            dst_p4d, dst_root, dst_change, dst_depot_abspath_map)
        dst_file_hash = get_dir_file_hash(dst_root, detect_dir=False)

        # verify that source change is a deletion
        p4_change_deleted_everything = not dst_file_hash

        new_src_file_hash = None
        while ((not new_src_file_hash) or
               (src_file_hash and new_src_file_hash == src_file_hash)):
            src_change = next(src_changes_iter)
            logger.info('against svn change %s' % src_change)

            src_files, src_msg = update_svn_changed_files(
                src_svn, src_change, src_root, svn_ignore_externals=svn_ignore_externals)

            if svn_project_subdir:
                logger.info('svn_project_subdir: %s' % svn_project_subdir)
                svn_project_subdir_path = os.path.join(
                    src_root, svn_project_subdir[1:])
                new_src_file_hash = get_dir_file_hash(
                    svn_project_subdir_path,
                    exclude=excluded_subdirs,
                    detect_dir=False,
                    excluded_files=excluded_files)
            else:
                new_src_file_hash = get_dir_file_hash(
                    src_root,
                    exclude=excluded_subdirs,
                    detect_dir=False,
                    excluded_files=excluded_files)
            if p4_change_deleted_everything:
                if new_src_file_hash:
                    raise BuildTestException('svn changed is not deletion')
                else:
                    break

        src_msg_lines = src_msg.split('\n')
        dst_msg_lines = dst_msg.split('\n')
        src_msg_lines = list(map(str.strip, src_msg_lines))
        dst_msg_lines = list(map(str.strip, dst_msg_lines))
        # remove empty lines
        src_msg_lines = [_f for _f in src_msg_lines if _f]
        dst_msg_lines = [_f for _f in dst_msg_lines if _f]

        rep_info = 'r%d|' % src_change
        if all([rep_info not in l for l in dst_msg_lines]):
            logger.error('rep info: %s' % rep_info)
            logger.error('dst msg lines: %s' % dst_msg_lines)
            raise BuildTestException('commit message not correctly replicated')

        if all(['#review' not in l for l in src_msg_lines]):
            orig_msg_line_num = len(src_msg_lines)
            if prefix_repinfo:
                rep_msg = dst_msg_lines[-orig_msg_line_num:]
            else:
                rep_msg = dst_msg_lines[:orig_msg_line_num]

            if src_msg_lines != rep_msg:
                logger.error('src message: %s' % src_msg_lines)
                logger.error('dst message: %s' % dst_msg_lines)
                raise BuildTestException(
                    'commit message not correctly replicated')

        '''
        if (not set(src_msg_lines).issubset(set(dst_msg_lines)) and
            all(['#review' not in l for l in src_msg_lines])):
            logger.error('src message: %s' % src_msg_lines)
            logger.error('dst message: %s' % dst_msg_lines)
            raise BuildTestException('commit message not correctly replicated')
        '''

        src_file_hash = new_src_file_hash

        if src_file_hash != dst_file_hash:
            src_len = len(src_file_hash)
            dst_len = len(dst_file_hash)
            if src_len >= dst_len:
                (more_, less_, m_root, l_root) = (src_file_hash,
                                                  dst_file_hash,
                                                  src_root,
                                                  dst_root)
            else:
                (more_, less_, m_root, l_root) = (dst_file_hash,
                                                  src_file_hash,
                                                  dst_root,
                                                  src_root)

            for m_f, m_v in list(more_.items()):
                l_f = m_f[:]
                l_v = less_.get(l_f)
                m_f = os.path.normpath(os.path.join(m_root, m_f))
                l_f = os.path.normpath(os.path.join(l_root, l_f))
                if m_v != l_v:
                    logger.error('%s : %s' % (m_f, m_v))
                    logger.error('%s : %s' % (l_f, l_v))
            raise BuildTestException('replication failed')

    try:
        next(src_changes_iter)
    except BaseException:
        pass
    else:
        raise BuildTestException('replication failed')


def get_svn_rev_list(svn_docker_cli, svn_dir):
    svn_user = ''
    svn_pass = ''
    svn_ip = svn_docker_cli.get_container_ip_addr()
    svn = SvnPython(
        'svn://%s:3690/repos' %
        svn_ip,
        svn_user,
        svn_pass,
        svn_dir)
    svn_changes = svn.get_revision_list(svn_dir)
    svn.client = None
    return svn_changes


def verify_replication(src_mapping, dst_mapping,
                       src_docker_cli, dst_docker_cli,
                       **kwargs):
    '''simple verification for Svn2P4 replication

    @param src_mapping, ((src_repo_dir, './...')) mapping, we use the
           same format as p4 mapping for simplicity
    @param dst_mapping, perforce view mapping
    @param src_docker_cli, source docker instance
    @param dst_docker_cli, target docker instance
    @param src_counter, optional, source counter changeset
    @param replicate_change_num, optional, number of changes to replicate

    '''
    src_counter = int(kwargs.get('src_counter', 0))
    replicate_change_num = kwargs.get('replicate_change_num', 0)
    source_last_changeset = kwargs.get('source_last_changeset', 0)
    prefix_repinfo = kwargs.get('prefix_repinfo', False)
    svn_ignore_externals = kwargs.get('svn_ignore_externals', False)
    excluded_subdirs = kwargs.get('excluded_subdirs', [])
    excluded_files = kwargs.get('excluded_files', [])

    p4_user = BUILD_TEST_P4D_USER
    svn_user = ''
    svn_pass = ''
    src_ip = src_docker_cli.get_container_ip_addr()
    dst_ip = dst_docker_cli.get_container_ip_addr()
    svn_dir = src_mapping[0][0]

    src_root = tempfile.mkdtemp(prefix='buildtest_src_')
    dst_root = tempfile.mkdtemp(prefix='buildtest_dst_')

    src_svn = SvnPython('svn://%s:3690/repos' % src_ip,
                        svn_user, svn_pass, src_root)
    dst_p4d = P4Server('%s:1666' % dst_ip, p4_user)

    #src_svn.checkout_working_copy(svn_dir, src_counter, depth='infinity')
    svn_project_dir = '/' + [d for d in svn_dir.split('/') if d][0]
    svn_project_subdir = ''
    if svn_project_dir != svn_dir:
        svn_project_subdir = svn_dir[len(svn_project_dir):]
    try:
        src_svn.checkout_working_copy(svn_project_dir, 0, depth='infinity')
    except BaseException:
        pass
    dst_ws_mapping = list(map(P4Server.WorkspaceMapping._make, dst_mapping))
    dst_p4d.create_workspace(dst_ws_mapping, ws_root=dst_root)

    src_start_change = src_counter

    try:
        dst_start_change = 0
        src_changes = src_svn.get_revision_list(svn_dir,
                                                start_rev=src_start_change)
        if src_changes and src_changes[0] == src_counter:
            src_changes = src_changes[1:]

        if not src_changes:
            return

        dst_changes = dst_p4d.run_changes('-l',
                                          '...@%d,#head' % dst_start_change)
        dst_changes = [c['change'] for c in dst_changes]

        dst_changes.reverse()

        # compare only the 'replicate_change_num' changes
        if replicate_change_num:
            src_changes = src_changes[:replicate_change_num]

        if source_last_changeset:
            idx = src_changes.index(source_last_changeset)
            src_changes = src_changes[:idx + 1]

        dst_changes = dst_changes[-len(src_changes):]

        verify_changes(src_svn, dst_p4d, src_root, dst_root,
                       svn_project_subdir, src_changes, dst_changes,
                       prefix_repinfo, svn_ignore_externals,
                       excluded_subdirs, excluded_files)
    finally:
        logger.info('src root: %s' % src_root)
        src_svn.client = None
        dst_p4d.delete_workspace()
        shutil.rmtree(src_root)
        shutil.rmtree(dst_root)


@contextmanager
def get_svn_from_docker(docker_cli):
    svn_ip = docker_cli.get_container_ip_addr()
    svn_user = ''
    svn_pass = ''
    svn_root = tempfile.mkdtemp(prefix='buildtest_src')
    svn = SvnPython(
        'svn://%s:3690/repos' %
        svn_ip,
        svn_user,
        svn_pass,
        svn_root)

    # checkout empty svn repo
    svn.checkout_working_copy('/', revision=-1, depth='empty')
    with working_in_dir(svn_root):
        yield svn, svn_root
    shutil.rmtree(svn_root)


def svn_test_action_actions(docker_cli, project_dir, **kwargs):
    actions = kwargs.get('actions', [])
    dirname = kwargs.get('special_dirname', 'test_dir')
    filename = kwargs.get('special_filename', 'repo_test_file')
    commit_msg = kwargs.get('commit_msg', '')

    with get_svn_from_docker(docker_cli) as (svn, svn_root):
        # add project directory
        project_abs_dir = os.path.join(svn_root, project_dir[1:])
        os.mkdir(project_abs_dir)
        # add trunk directory
        trunk_dir = os.path.join(project_abs_dir, 'trunk')
        os.mkdir(trunk_dir)
        # add branch directory
        branch_dir = os.path.join(project_abs_dir, 'branches')
        os.mkdir(branch_dir)
        # add test directory
        test_dir = os.path.join(trunk_dir, dirname)
        os.mkdir(test_dir)
        test_file = os.path.join(test_dir, filename)

        act_str = 'add %s' % project_abs_dir
        svn.run_add(project_abs_dir)
        svn.run_checkin(project_abs_dir, act_str)
        last_rev = svn.get_revision_list(project_dir)[-1]

        act_str = 'add "%s"' % test_file
        with open(test_file, 'wt') as f:
            f.write(act_str)

        svn.run_add(test_file)
        svn.run_checkin(test_file, act_str)
        last_rev = svn.get_revision_list(project_dir)[-1]

        for action in actions:
            if action in ['add_file']:
                test_file = os.path.join(test_dir, generate_random_str())
                act_str = '%s %s' % (action, test_file)
                with open(test_file, 'wt') as f:
                    f.write(act_str)
                svn.run_checkin(test_file, act_str)

            if action in ['add_dir']:
                test_dir = os.path.join(trunk_dir, generate_random_str())
                os.mkdir(test_dir)

                test_file = os.path.join(test_dir, generate_random_str())
                with open(test_file, 'wt') as f:
                    f.write(act_str)
                act_str = '%s %s' % (action, test_dir)
                svn.run_add(test_dir)
                svn.run_checkin(test_dir, act_str)

            if action in ['edit']:
                act_str = '%s %s' % (action, test_file)
                with open(test_file, 'a') as f:
                    f.write(act_str)
                svn.run_checkin(test_file, act_str)

            if action in ['add_exec']:
                test_file = test_file + '_exec'
                act_str = '%s %s' % (action, test_file)
                with open(test_file, 'a') as f:
                    f.write(act_str)

                import stat
                f_st = os.lstat(test_file)
                f_st_mode = f_st.st_mode + (stat.S_IXGRP | stat.S_IXUSR)
                os.chmod(test_file, f_st_mode)

                svn.run_add(test_file)
                svn.run_checkin(test_file, act_str)

            if action in ['changing_exec']:
                test_file = test_file + '_exec'
                act_str = '%s %s' % (action, test_file)
                with open(test_file, 'wt') as f:
                    f.write(act_str)
                import stat
                f_st = os.lstat(test_file)
                f_st_mode = f_st.st_mode + (stat.S_IXGRP | stat.S_IXUSR)
                os.chmod(test_file, f_st_mode)

                svn.run_add(test_file)
                svn.run_checkin(test_file, act_str)

                for _ in range(4):
                    # remove exec bit
                    f_st = os.lstat(test_file)
                    f_st_mode = f_st.st_mode - (stat.S_IXGRP | stat.S_IXUSR)
                    os.chmod(test_file, f_st_mode)
                    with open(test_file, 'a') as f:
                        f.write('removed exec bits\n')
                    svn.run_propdel('svn:executable', test_file)
                    svn.run_checkin(test_file, 'removing executable bit')

                    # add exec bit
                    with open(test_file, 'a') as f:
                        f.write('added exec bits, again\n')
                    svn.run_propset('svn:executable', '*', test_file)
                    svn.run_checkin(test_file, 'set executable bit again')

            if action in ['symlink_rel']:
                # add a good relative symlink
                test_symlink_file = test_file + '_livelink'
                test_file_rel_path = os.path.join(
                    './', os.path.basename(test_file))
                act_str = '%s %s %s' % (
                    action, test_file_rel_path, test_symlink_file)
                os.symlink(test_file_rel_path, test_symlink_file)
                svn.run_add(test_symlink_file)
                svn.run_checkin(test_symlink_file, act_str)

                # add a dead relative symlink
                test_symlink_file = test_file + '_deadlink'
                test_file_rel_path = './some_file_does_not_exist'
                act_str = '%s %s %s' % (
                    action, test_file_rel_path, test_symlink_file)
                os.symlink(test_file_rel_path, test_symlink_file)
                svn.run_add(test_symlink_file)
                svn.run_checkin(test_symlink_file, act_str)

            if action in ['changing_symlink']:
                # add a good relative symlink
                test_symlink_file = test_file + '_changing_link'
                test_file_rel_path = os.path.join(
                    './', os.path.basename(test_file))
                act_str = '%s %s %s' % (
                    action, test_file_rel_path, test_symlink_file)
                os.symlink(test_file_rel_path, test_symlink_file)
                svn.run_add(test_symlink_file)
                svn.run_checkin(test_symlink_file, act_str)

                for _ in range(5):
                    # remove link
                    svn.run_propdel('svn:special', test_symlink_file)
                    os.remove(test_symlink_file)
                    act_str = 'removing symlink'
                    with open(test_symlink_file, 'a') as f:
                        f.write(act_str)
                    svn.run_checkin(test_symlink_file, act_str)

                    # add sym link
                    os.remove(test_symlink_file)
                    act_str = 'removing symlink'
                    os.symlink(test_file_rel_path, test_symlink_file)
                    svn.run_propset('svn:special', '*', test_symlink_file)
                    act_str = 'adding symlink'
                    svn.run_checkin(test_symlink_file, act_str)

            if action in ['symlink_abs']:
                # add a good absolute symlink
                test_symlink_file = test_file + '_livelink'
                act_str = '%s %s %s' % (action, test_file, test_symlink_file)
                os.symlink(test_file, test_symlink_file)
                svn.run_add(test_symlink_file)
                svn.run_checkin(test_symlink_file, act_str)

                # add a dead absolute symlink
                test_symlink_file = test_file + '_deadlink'
                test_file_abs_path = '/some_file_does_not_exist'
                act_str = '%s %s %s' % (action, test_file, test_symlink_file)
                os.symlink(test_file_abs_path, test_symlink_file)
                svn.run_add(test_symlink_file)
                svn.run_checkin(test_symlink_file, act_str)

                # add another dead relative symlink
                test_symlink_file = test_file + '_deadlink_1.bmp'
                #test_symlink_file = test_file + '_deadlink_1'
                test_file_abs_path = 'D:/Branches/0_WoT_Trunk/bin/tools/Click-o-matic/scripts/all_assets_load/3e556918ede44742b0627e7932cb7101.bmp'
                act_str = '%s %s %s' % (
                    action, test_file_abs_path, test_symlink_file)
                os.symlink(test_file_abs_path, test_symlink_file)
                svn.run_add(test_symlink_file)
                svn.run_checkin(test_symlink_file, act_str)

                # add a dir which has symlinks
                test_add_dir = os.path.join(test_dir, "add_dir_with_symlink")
                os.mkdir(test_add_dir)
                # add symlink
                test_symlink_file = os.path.join(test_add_dir, "deadlink.bmp")
                test_file_abs_path = 'C:/Branches/0_WoT_Trunk/bin/tools/Click-o-matic/scripts/all_assets_load/deadlink_target.bmp'
                act_str = '%s %s %s' % (
                    action, test_file_abs_path, test_symlink_file)
                os.symlink(test_file_abs_path, test_symlink_file)
                # and add normal file
                test_normal_file = os.path.join(test_add_dir, "normal.txt")
                with open(test_normal_file, 'a') as f:
                    f.write('add normal file')
                svn.run_add(test_add_dir)
                svn.run_checkin(test_add_dir, act_str)

            if action in ['move', 'rename']:
                test_file_new = test_file + '_new'
                svn.run_move(test_file, test_file_new)
                act_str = 'rename %s to %s' % (test_file, test_file_new)
                svn.run_checkin([test_file, test_file_new], act_str)
                test_file = test_file_new

            if action in ['copy_prev']:
                # edit, to create a new rev
                act_str = '%s %s' % (action, test_file)
                with open(test_file, 'a') as f:
                    f.write(act_str)
                svn.run_checkin(test_file, act_str)

                # get svn url
                wc_info = svn.run_info(svn_root)
                svn_url = wc_info['url']

                # and then copy a previous rev
                test_file_url = svn_url + test_file[len(svn_root):]
                test_file_url_prev_rev = '%s@%s' % (test_file_url, last_rev)
                test_file_new = test_file + '_new'
                cmd = '%s %s' % (test_file_url_prev_rev, test_file_new)

                svn.run_copy(test_file_url, test_file_new, last_rev)
                act_str = 'copying %s' % cmd
                svn.run_checkin([test_file_new], act_str)
                test_file = test_file_new

            if action in ['copy_latest']:
                test_file_new = test_file + '_copiedto'
                svn.run_copy(test_file, test_file_new)
                act_str = 'copy %s to %s' % (test_file, test_file_new)
                svn.run_checkin([test_file, test_file_new], act_str)
                test_file = test_file_new

            if action in ['branch']:
                branch = os.path.join(branch_dir, generate_random_str())
                svn.run_copy(trunk_dir, branch)
                svn.run_checkin(branch, 'branched')

            if action in ['replace_file']:
                svn.run_remove(test_file)
                act_str = 'replaced "%s"' % test_file
                with open(test_file, 'wt') as f:
                    f.write(act_str)
                svn.run_add(test_file)
                act_str = 'replaced %s' % (test_file)
                svn.run_checkin(test_file, act_str)

            if action in ['replace_dir_empty']:
                svn.run_update(test_dir)
                svn.run_remove(test_dir, force=True)

                os.mkdir(test_dir)
                svn.run_add(test_dir)
                act_str = 'replaced %s' % (test_dir)
                svn.run_checkin(test_dir, act_str)

            if action in ['replace_dir_new_file']:
                svn.run_update(test_dir)
                svn.run_remove(test_dir, force=True)

                os.mkdir(test_dir)
                test_file = os.path.join(test_dir, generate_random_str())
                with open(test_file, 'wt') as f:
                    f.write(act_str)
                svn.run_add(test_dir)
                act_str = 'replaced %s' % (test_dir)
                svn.run_checkin(test_dir, act_str)

            if action in ['replace_dir_same_file']:
                svn.run_update(test_dir)
                svn.run_remove(test_dir, force=True)

                os.mkdir(test_dir)
                #test_file = os.path.join(test_dir, 'repo_test_file')
                with open(test_file, 'wt') as f:
                    f.write(act_str + generate_random_str())
                svn.run_add(test_dir)
                act_str = 'replaced %s' % (test_dir)
                svn.run_checkin(test_dir, act_str)

            if action in ['replace_dir_same_file_one_more']:
                svn.run_update(test_dir)
                svn.run_remove(test_dir, force=True)

                os.mkdir(test_dir)
                with open(test_file, 'wt') as f:
                    f.write(act_str + generate_random_str())
                test_file = test_file + generate_random_str()
                with open(test_file, 'wt') as f:
                    f.write(act_str + generate_random_str())
                svn.run_add(test_dir)
                act_str = 'replaced %s' % (test_dir)
                svn.run_checkin(test_dir, act_str)

            if action in ['delete_file']:
                svn.run_remove(test_file)
                svn.run_checkin(test_file, 'deleted %s' % test_file)

            if action in ['delete_dir']:
                # Before deleting any directory, update it first. previous
                # changes may also update this directory.
                svn.run_update(test_dir)
                svn.run_remove(test_dir)
                svn.run_checkin(test_dir, 'deleted dir')

            last_rev = svn.get_revision_list(project_dir)[-1]
