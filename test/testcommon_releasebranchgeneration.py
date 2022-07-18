import os
import shutil
import tempfile

from .testcommon import (BUILD_TEST_P4D_USER,
                         BuildTestException,)
from .testcommon_svnp4 import (get_dir_file_hash,)
from lib.p4server import P4Server
from lib.buildlogger import getLogger

# global variables
logger = getLogger(__name__)
logger.setLevel('INFO')


def verify_replication(src_dir, dst_dir, docker_cli,
                       src_counter=0, **kwargs):
    p4_user = BUILD_TEST_P4D_USER
    ip = docker_cli.get_container_ip_addr()
    src_p4 = P4Server('%s:1666' % ip, p4_user)
    dst_p4 = P4Server('%s:1666' % ip, p4_user)

    src_root = tempfile.mkdtemp(prefix='buildtest')
    dst_root = tempfile.mkdtemp(prefix='buildtest')

    src_mapping = list(
        map(P4Server.WorkspaceMapping._make, [(src_dir, './...'), ]))
    dst_mapping = list(
        map(P4Server.WorkspaceMapping._make, [(dst_dir, './...'), ]))
    src_p4.create_workspace(src_mapping, ws_root=src_root)
    dst_p4.create_workspace(dst_mapping, ws_root=dst_root)

    replicate_change_num = kwargs.get('maximum', 0)
    src_start_change = int(src_counter) + 1

    replicate_user_and_timestamp = kwargs.get(
        'replicate_user_and_timestamp', False)

    src_last_change = kwargs.get('source_last_revision', None)
    if not src_last_change:
        src_last_change = '#head'
    else:
        src_last_change = '@%d' % src_last_change

    dst_start_change = 0
    try:
        dst_start_change = 0
        src_changes = src_p4.run_changes(
            '-l', './...@%d,%s' %
            (src_start_change, src_last_change))
        dst_changes = dst_p4.run_changes(
            '-l', './...@%d,#head' %
            dst_start_change)

        src_changes.reverse()
        dst_changes.reverse()

        # compare only the 'replicate_change_num' changes
        if replicate_change_num:
            src_changes = src_changes[:replicate_change_num]
        dst_changes = dst_changes[-len(src_changes):]

        verify_changes(src_p4, dst_p4, src_changes, dst_changes,
                       src_root, dst_root, replicate_user_and_timestamp)
    finally:
        logger.info('src_root: %s' % src_root)
        logger.info('dst_root: %s' % dst_root)
        import time
        try:
            time.sleep(0)
        except BaseException:
            pass
        src_p4.delete_workspace()
        dst_p4.delete_workspace()

        shutil.rmtree(src_root)
        shutil.rmtree(dst_root)


def verify_changes(src_p4, dst_p4, src_changes, dst_changes, src_root,
                   dst_root, replicate_user_and_timestamp):
    '''verify if two change sets contain basically same contents

    @param src_p4 [in] source p4server
    @param dst_p4 [in] destination p4server
    @param src_changes [in] source change set
    @param dst_changes [in] destination change set
    '''
    # at least two change sets should have same number of changes
    change_num = len(src_changes)
    if change_num != len(dst_changes):
        msg = '# of src(%d) != dst(%d)' % (change_num, len(dst_changes))
        raise BuildTestException(msg)

    # mapping from depot to abs path
    src_depot_abspath_map = src_p4.get_depot_path_map()
    dst_depot_abspath_map = dst_p4.get_depot_path_map()
    # mapping from depot to path relative to /tmp
    src_depot_tmppath_map = src_p4.get_depot_path_map(root='/tmp')
    dst_depot_tmppath_map = dst_p4.get_depot_path_map(root='/tmp')

    for change_idx in range(change_num):
        src_change_id = src_changes[change_idx]['change']
        dst_change_id = dst_changes[change_idx]['change']
        logger.info('Verifying change(%s)->change(%s)' % (src_change_id,
                                                          dst_change_id))

        # sync to the same state in two workspaces
        src_p4.run_sync('-f', '...@%s' % src_change_id)
        dst_p4.run_sync('-f', '...@%s' % dst_change_id)

        src_desc = src_p4.run_describe(src_change_id)[-1]
        dst_desc = dst_p4.run_describe(dst_change_id)[-1]

        verify_change_files(src_root, dst_root)

        if replicate_user_and_timestamp:
            src_user = src_changes[change_idx]['user']
            dst_user = dst_changes[change_idx]['user']
            src_time = src_changes[change_idx]['time']
            dst_time = dst_changes[change_idx]['time']

            logger.info('%s, %s =? %s, %s' % (src_user, src_time,
                                              dst_user, dst_time))

            if src_user != dst_user:
                err_msg = 'src user != dst user(%s != %s)' % (
                    src_user, dst_user)
                raise BuildTestException(err_msg)

            if src_time != dst_time:
                err_msg = 'src time != dst time(%s != %s)' % (
                    src_time, dst_time)
                raise BuildTestException(err_msg)


def verify_change_files(src_root, dst_root):
    '''check existance and contents of files of src/dst changes
    '''
    src_file_hash = get_dir_file_hash(src_root)
    dst_file_hash = get_dir_file_hash(dst_root)

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
