import os
import shutil
import sys
import tempfile
import P4P4Replicate as P4P4

from contextlib import contextmanager
from collections import namedtuple
from lib.buildcommon import get_dir_file_hash
from lib.buildlogger import getLogger
from lib.p4server import P4Server
from replicationunittest import (run_replication_in_container,
                                 BUILD_TEST_P4D_USER)

# add the path of scripts to sys.path to locate all scripts and libraries
filepath = os.path.abspath(__file__)
dirname = os.path.dirname
scriptRootDir = dirname(dirname(filepath))
sys.path.append(scriptRootDir)


# global variables
logger = getLogger(__name__)
logger.setLevel('INFO')


class BuildTestException(Exception):
    pass


def replicate_P4P4Replicate(src_mapping, dst_mapping,
                            src_docker_cli, dst_docker_cli, **kwargs):
    '''generate cfg and call P4P4Replicate.replicate() to replicate

    @param src_mapping [in] list of P4Server.WorkspaceMapping for src ws
    @param dst_mapping [in] list of P4Server.WorkspaceMapping for dst ws
    @param src_docker_cli [in] instance of DockerClient, container
    should be up and running
    @param dst_docker_cli [in] target instance of DockerClient
    @param src_counter [in] optional int, last replicated change id
    @param replicate_change_num [in] optional int, number of changes to replicate
    @param source_last_changeset [in] optional int, last changeset to replicate
    '''
    p4_user = BUILD_TEST_P4D_USER
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
    prefix_repinfo = kwargs.get('prefix_repinfo', False)
    if source_last_changeset:
        source_last_changeset = str(source_last_changeset)
    ws_root = kwargs.get('ws_root')
    if not ws_root:
        ws_root = tempfile.mkdtemp(
            prefix='buildtest', dir=os.path.join(
                scriptRootDir, 'test/replication'))

    source_p4_stream = kwargs.get('source_p4_stream')

    args = ReplicateCmdArgs()
    args.source_port = '%s:1666' % src_ip
    args.source_user = p4_user
    args.source_passwd = ' '
    args.source_counter = src_counter
    args.source_workspace_view_cfgfile = create_ws_mapping_file(src_mapping)

    args.target_port = '%s:1666' % dst_ip
    args.target_user = p4_user
    args.target_passwd = ' '
    args.target_workspace_view_cfgfile = create_ws_mapping_file(dst_mapping)
    args.target_empty_file = None

    args.workspace_root = ws_root
    args.maximum = None if replicate_change_num == 0 else replicate_change_num
    args.source_last_changeset = source_last_changeset
    args.uniqueid = None
    args.prefix_description_with_replication_info = prefix_repinfo
    args.replicate_user_and_timestamp = True
    args.logging_color_format = 'console'

    if source_p4_stream:
        args.source_p4_stream = source_p4_stream
    args.verbose = 'INFO'

    try:
        if os.environ.get("TEST_IN_HOST"):
            P4P4.replicate(args)
        else:
            script = './P4P4Replicate.py'
            run_replication_in_container(script, args)
    finally:
        shutil.rmtree(ws_root)
        os.remove(args.source_workspace_view_cfgfile)
        os.remove(args.target_workspace_view_cfgfile)


class VerifyChangeDescAttr(object):
    '''class to verify attributes of 'p4 describe changeid'
    '''
    nonexist = 'Non-exist'

    def __init__(self, src_p4, dst_p4, src_desc, dst_desc,
                 src_change_id, dst_change_id,
                 src_depot_map, dst_depot_map):
        self.src_p4 = src_p4
        self.dst_p4 = dst_p4
        self.src_id = src_change_id
        self.dst_id = dst_change_id
        self.src_desc = src_desc
        self.dst_desc = dst_desc
        self.src_depot_map = src_depot_map
        self.dst_depot_map = dst_depot_map

    def verify(self, attr_name):
        '''verify if src_desc[attr_name] matches dst_desc[attr_name]

        If _verify_{attr_name} method is defined, call it for
        comparison.  otherwise, default _verify_attr() would be used,
        which simply compares two values.
        '''
        src_attr = self.src_desc.get(attr_name, self.nonexist)
        dst_attr = self.dst_desc.get(attr_name, self.nonexist)

        if src_attr == dst_attr == self.nonexist:
            return

        # remove attr of src files that are not in workspace mapping
        if isinstance(src_attr, list) and isinstance(dst_attr, list):
            src_depotfiles = self.src_desc.get('depotFile')
            dst_depotfiles = self.dst_desc.get('depotFile')
            src_action = self.src_desc.get('action')
            dst_action = self.dst_desc.get('action')

            '''
            logger.error('comparing %s' % attr_name)
            logger.error('self.src_depot_map: %s' % self.src_depot_map)
            logger.error('self.dst_depot_map: %s' % self.dst_depot_map)
            logger.error('src # %s: %s' % (len(src_depotfiles), src_depotfiles))
            logger.error('dst # %s: %s' % (len(dst_depotfiles), dst_depotfiles))
            logger.error('src # %s: %s' % (len(src_attr), src_attr))
            logger.error('dst # %s: %s' % (len(dst_attr), dst_attr))
            '''

            src_depotfiles = [src_depotfiles[idx]
                              for idx in range(len(src_depotfiles))
                              if 'delete' not in src_action[idx]]
            dst_depotfiles = [dst_depotfiles[idx]
                              for idx in range(len(dst_depotfiles))
                              if 'delete' not in dst_action[idx]]

            src_file_attr = []
            dst_file_attr = []
            src_reverse_map = self.src_depot_map.reverse()
            for dst_attr_idx, df in enumerate(dst_depotfiles):
                local_file = self.dst_depot_map.translate(df)
                src_depot = src_reverse_map.translate(local_file)
                src_attr_idx = src_depotfiles.index(src_depot)

                dst_file_attr.append(dst_attr[dst_attr_idx])
                src_file_attr.append(src_attr[src_attr_idx])

            src_attr = src_file_attr
            dst_attr = dst_file_attr

        src_msg = 'src(%s) desc[%s]=%s' % (self.src_id, attr_name, src_attr)
        dst_msg = 'dst(%s) desc[%s]=%s' % (self.dst_id, attr_name, dst_attr)
        self.mismatchErr = 'change attr mismatch: \n%s, \n%s' % (
            src_msg, dst_msg)

        try:
            getattr(self, '_verify_' + attr_name.lower())(src_attr, dst_attr)
        except AttributeError:
            self._verify_attr(src_attr, dst_attr)

    def _verify_attr(self, src_attr, dst_attr):
        '''compares two values directly.

        The attributes are either strings or list of strings. We can
        compare their values directly.
        '''
        if src_attr != dst_attr:
            raise BuildTestException(self.mismatchErr)

    def _source_has_missing_rev(self, file_idx):
        # detect if there's any revision obliterated.
        src_depotfile = self.src_desc.get('depotFile')[file_idx]
        filelog = self.src_p4.run_filelog(src_depotfile)
        revisions = None
        for depotfile_log in filelog:
            if depotfile_log.depotFile == src_depotfile:
                revisions = depotfile_log.revisions
        revs = [rev.rev for rev in revisions]
        if revs and revs[0] != len(revs):
            logger.warning('%s revision obliterated, %s' % (src_depotfile,
                                                            str(revs)))
            return True
        return False

    def _verify_rev(self, src_attr, dst_attr):
        '''verify if 'rev' of 'p4 describe' are the same

        If any revision of src file is obliterated, we ignore the mismatch.
        '''
        for rev_idx in range(len(src_attr)):
            src_act = src_attr[rev_idx]
            dst_act = dst_attr[rev_idx]
            if src_act == dst_act:
                continue

            if self._source_has_missing_rev(rev_idx):
                continue

            raise BuildTestException(self.mismatchErr)

    def _verify_action(self, src_attr, dst_attr):
        '''verify if 'action' of 'p4 describe' are the same

        NOTE: If "branch" from directory not included in src depot,
        is 'add' acceptable
        '''
        for action_idx in range(len(src_attr)):
            src_act = src_attr[action_idx]
            dst_act = dst_attr[action_idx]
            if src_act == dst_act:
                continue

            # exception branch -> add
            if src_act == 'branch' and dst_act == 'add':
                continue

            # exception edit -> add, if obliterated
            if (self._source_has_missing_rev(action_idx) and
                src_act == 'edit' and
                    dst_act == 'add'):
                continue

            # exception integrate -> edit
            if src_act == 'integrate' and dst_act == 'edit':
                continue

            raise BuildTestException(self.mismatchErr)

    def _verify_desc(self, src_attr, dst_attr):
        '''verify if 'description' of 'p4 describe' are the same

        NOTE: In replicate script, when 'updateChange' a change, some
        white spaces are removed from change description. need to know
        if it's OK or not.
        '''
        src_desc_desc = set(map(str.strip, src_attr.split('\n')))
        dst_desc_desc = set(map(str.strip, dst_attr.split('\n')))
        if src_desc_desc.issubset(dst_desc_desc):
            # src description should be part of replicated description
            # if src_desc['desc'] not in dst_desc['desc']:
            return

        raise BuildTestException(self.mismatchErr)

    def _verify_fromfile(self, src_attr, dst_attr):
        '''verify if 'fromFile' of 'p4 describe' are the same

        'fromFile' is a list of depot files. so before
        comparison, we can't compare two depot files with
        different root
        '''
        src_filenames = list(map(os.path.basename, [_ for _ in src_attr if _]))
        dst_filenames = list(map(os.path.basename, [_ for _ in dst_attr if _]))
        if src_filenames != dst_filenames:
            raise BuildTestException(self.mismatchErr)

    def _verify_filesize(self, src_attr, dst_attr):
        '''verify if 'filesize' are the same

        NOTE:
        In the perforce sample depot, 'file size' of some 'add'
        changes do not exist. It's not a problem of replicating
        script, so add an exception here.
        '''
        if src_attr == self.nonexist and dst_attr != self.nonexist:
            return

        if src_attr != dst_attr:
            raise BuildTestException(self.mismatchErr)

    def _verify_type(self, src_attr, dst_attr):
        '''verify if src/dst 'type' of 'p4 descript change' are the same

        NOTE: file types are considered the same if they are in the
        same set.
        Reference https://www.perforce.com/manuals/cmdref/Content/CmdRef/file.types.synopsis.modifiers.html
        '''
        p4types = {
            'text': [
                'text',
                'ltext',
                'ktext',
                'ctext',
                'text+Fk',
                'text+F',
                'text+k'],
            'xtext': [
                'xtext',
                'xltext',
                'text+Fx',
                'kxtext',
                'cxtext',
                'text+x'],
            'binary': [
                'binary',
                'ubinary',
            ],
            'xbinary': [
                'xbinary',
                'uxbinary',
            ],
            'resource': [
                'resource',
                'uresource',
            ],
        }

        for src_type, dst_type in zip(src_attr, dst_attr):
            if src_type == dst_type:
                continue

            for _, filetypes in list(p4types.items()):
                if set([src_type, dst_type]).issubset(set(filetypes)):
                    break
            else:
                logger.error('src/dst types: %s != %s' % (src_type, dst_type))
                raise BuildTestException(self.mismatchErr)


def verify_change_integrations(src_p4, dst_p4, src_desc, dst_desc,
                               src_depot_map, dst_depot_map):
    '''verify integrations of each file revision

    @param src_p4 [in] source p4server
    @param dst_p4 [in] destination p4server
    @param src_desc [in] output of "p4 describe src_change_id"
    @param dst_desc [in] output of "p4 describe dst_change_id"
    @param src_depot_map [in] depot to relative(to '/tmp') path mapping
    @param dst_depot_map [in] depot to relative(to '/tmp') path mapping
    '''
    depot_rev = list(zip(src_desc['depotFile'], src_desc['rev'],
                         dst_desc['depotFile'], dst_desc['rev']))

    for src_depot, src_rev, dst_depot, dst_rev in depot_rev:
        src_filelog = src_p4.run_filelog('-m1', '%s#%s' % (src_depot, src_rev))
        dst_filelog = dst_p4.run_filelog('-m1', '%s#%s' % (dst_depot, dst_rev))

        # one file, and one revision
        src_integrations = src_filelog[0].revisions[0].integrations
        dst_integrations = dst_filelog[0].revisions[0].integrations

        def srcmap(integ): return src_depot_map.translate(integ.file)
        def dstmap(integ): return dst_depot_map.translate(integ.file)

        # remove integrations not mapped in src/dst view
        src_integs = list(filter(srcmap, src_integrations))
        dst_integs = list(filter(dstmap, dst_integrations))

        # transform from Integration to tuple, because we know how
        # tuple compares equality
        P4Integ = namedtuple('P4Integ', ['how', 'file', 'srev', 'erev'])

        src_integs = [P4Integ(integ.how, srcmap(integ), integ.srev, integ.erev)
                      for integ in src_integs]
        dst_integs = [P4Integ(integ.how, dstmap(integ), integ.srev, integ.erev)
                      for integ in dst_integs]

        def integ_from(integ): return integ.how.endswith('from')
        src_integs = list(filter(integ_from, src_integs))
        dst_integs = list(filter(integ_from, dst_integs))

        # sort it for comparison easily
        src_integs.sort(key=lambda integ: integ.file)
        dst_integs.sort(key=lambda integ: integ.file)

        comb_integs = list(zip(src_integs, dst_integs))
        for src_integ, dst_integ in comb_integs:
            if src_integ == dst_integ:
                continue

            # NOTE: some 'srev' mismatches in 'branch into' or 'add into'
            # actions in sample depot
            exception_actions = ('branch into', 'add into', )
            if (src_integ.how in exception_actions and
                src_integ.how == dst_integ.how and
                src_integ.file == dst_integ.file and
                    src_integ.erev == dst_integ.erev):
                continue

            msg = 'src integ(%s) diffs dst integ(%s)' % (src_integrations,
                                                         dst_integrations)
            raise BuildTestException(msg)


def verify_change_descs(src_p4, dst_p4, src_desc, dst_desc,
                        src_change_id, dst_change_id,
                        src_depot_map, dst_depot_map):
    '''verify if description of replicated change is the same as orginal

    @param src_p4 [in] source p4server
    @param dst_p4 [in] destination p4server
    @param src_desc [in] output of "p4 describe src_change_id"
    @param dst_desc [in] output of "p4 describe dst_change_id"
    @param src_change_id [in] source change id
    @param dst_change_id [in] target change id
    @param src_depot_map [in] depot to relative(to '/tmp') path mapping
    @param dst_depot_map [in] depot to relative(to '/tmp') path mapping

    BuildTestException would be raised if certain attributes of two
    descriptions are not the same.
    '''
    # change attributes should match
    descVerify = VerifyChangeDescAttr(src_p4, dst_p4, src_desc, dst_desc,
                                      src_change_id, dst_change_id,
                                      src_depot_map, dst_depot_map)

    if src_p4.is_unicode_server() != dst_p4.is_unicode_server():
        desc_attrs = ('action', 'rev', 'time', 'user',
                      'fromFile', 'fromRev', 'desc', )
    else:
        desc_attrs = ('action', 'fileSize', 'rev', 'time', 'type',
                      'user', 'fromFile', 'fromRev', 'desc', )
    for attr in desc_attrs:
        descVerify.verify(attr)


def verify_change_files(src_root, dst_root):
    '''verify if two p4 workspaces have identical files, same hash/exec bits

    @param src_root, src p4 workspace root
    @param dst_root, dst p4 workspace root
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


def verify_changes(src_p4, dst_p4, src_changes, dst_changes,
                   do_change_desc_verification=True,
                   do_integration_verification=True):
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

    src_root = src_p4.fetch_client(src_p4.client)._root
    dst_root = dst_p4.fetch_client(dst_p4.client)._root

    for change_idx in range(change_num):
        src_change_id = src_changes[change_idx]['change']
        dst_change_id = dst_changes[change_idx]['change']
        logger.info('Verifying change(%s)->change(%s)' % (src_change_id,
                                                          dst_change_id))

        # sync to the same state in two workspaces
        src_p4.run_sync('-f', '...@%s,%s' % (src_change_id, src_change_id))
        dst_p4.run_sync('-f', '...@%s,%s' % (dst_change_id, dst_change_id))

        src_desc = src_p4.run_describe(src_change_id)[-1]
        dst_desc = dst_p4.run_describe(dst_change_id)[-1]

        if do_change_desc_verification:
            verify_change_descs(src_p4, dst_p4, src_desc, dst_desc,
                                src_change_id, dst_change_id,
                                src_depot_tmppath_map,
                                dst_depot_tmppath_map)
        else:
            logger.warning('change_desc_verification is disabled')

        if do_integration_verification:
            verify_change_integrations(src_p4, dst_p4, src_desc, dst_desc,
                                       src_depot_tmppath_map,
                                       dst_depot_tmppath_map)
        else:
            logger.warning('integration_verification is disabled')

        verify_change_files(src_root, dst_root)


def verify_replication(src_mapping, dst_mapping,
                       src_docker_cli, dst_docker_cli, **kwargs):
    '''verify if replication is done completely and correctly

    @param src_mapping [in] list of P4Server.WorkspaceMapping for src ws
    @param dst_mapping [in] list of P4Server.WorkspaceMapping for dst ws
    @param src_docker_cli [in] instance of DockerClient, container
                               should be up and running
    @param dst_docker_cli [in] target instance of DockerClient
    @param src_counter [in] optional int, last replicated change id
    @param replicate_change_num [in] optional int, number of changes to replicate
    @param source_last_changeset [in] optional int, last changeset to replicate
    '''
    p4_user = BUILD_TEST_P4D_USER
    src_ip = src_docker_cli.get_container_ip_addr()
    dst_ip = dst_docker_cli.get_container_ip_addr()
    src_p4 = P4Server('%s:1666' % src_ip, p4_user)
    dst_p4 = P4Server('%s:1666' % dst_ip, p4_user)

    source_p4_stream = None
    source_p4_stream = kwargs.get('source_p4_stream')

    src_root = tempfile.mkdtemp(prefix='buildtest_src_')
    dst_root = tempfile.mkdtemp(prefix='buildtest_dst_')
    src_p4.create_workspace(src_mapping, ws_root=src_root,
                            stream=source_p4_stream)
    dst_p4.create_workspace(dst_mapping, ws_root=dst_root)

    src_counter = kwargs.get('src_counter', 0)
    replicate_change_num = kwargs.get('replicate_change_num', 0)
    source_last_changeset = kwargs.get('source_last_changeset', None)
    do_integration_verification = kwargs.get(
        'do_integration_verification', True)
    do_change_desc_verification = kwargs.get(
        'do_change_desc_verification', True)

    if not source_last_changeset:
        source_last_changeset = '#head'
    else:
        source_last_changeset = '@%d' % source_last_changeset

    src_start_change = src_counter
    try:
        dst_start_change = 0
        src_changes = src_p4.run_changes(
            '-l', '...@%d,%s' %
            (src_start_change, source_last_changeset))
        dst_changes = dst_p4.run_changes(
            '-l', '...@%d,#head' %
            dst_start_change)

        if src_changes and str(src_start_change) == str(
                src_changes[-1]['change']):
            src_changes = src_changes[:-1]

        src_changes.reverse()
        dst_changes.reverse()

        # compare only the 'replicate_change_num' changes
        if replicate_change_num:
            src_changes = src_changes[:replicate_change_num]

        if src_changes:
            dst_changes = dst_changes[-len(src_changes):]

            verify_changes(src_p4, dst_p4, src_changes, dst_changes,
                           do_change_desc_verification,
                           do_integration_verification)
    finally:
        src_p4.delete_workspace()
        dst_p4.delete_workspace()

        shutil.rmtree(src_root)
        shutil.rmtree(dst_root)


def obliterate_depots(docker_cli, depot_mapping):
    p4_user = BUILD_TEST_P4D_USER
    ip = docker_cli.get_container_ip_addr()
    p4 = P4Server('%s:1666' % ip, p4_user)

    for depot, _ in depot_mapping:
        p4.run_obliterate('-y', depot)


def get_changelist_in_sample_depot(docker_cli, depot_dir):
    '''get change list of specified depot from p4 server hosted in docker_cli.

    @param docker_cli [in] instance of DockerClient, container hosting p4d
    @param depot_dir [in] string of source depot, e.g. '//depot/skynet/...'
    @return list of change id
    '''
    p4_user = BUILD_TEST_P4D_USER
    container_ip = docker_cli.get_container_ip_addr()
    p4 = P4Server('%s:1666' % container_ip, p4_user)

    sw_view = ((depot_dir, './...'),)
    sw_mapping = list(map(P4Server.WorkspaceMapping._make, sw_view))

    ws_root = tempfile.mkdtemp(prefix='buildtest')
    p4.create_workspace(sw_mapping, ws_root=ws_root)

    changes = p4.run_changes('-l', '...@0,#head')
    changes.reverse()

    p4.delete_workspace()
    shutil.rmtree(ws_root)

    return [change['change'] for change in changes]


def replicate_sampledir_in_groups(depot_dir,
                                  src_docker_cli,
                                  dst_whole_docker_cli,
                                  dst_group_docker_cli,
                                  num_changes_per_round,
                                  changing_repinfo_location=False):
    '''replicate from specified src_counter and number of changes
    '''
    src_depot = '/%s/...' % depot_dir
    dst_whole_depot = '//depot/buildtest_whole%s/...' % depot_dir
    dst_group_depot = '//depot/buildtest_group%s/...' % depot_dir

    src_view = ((src_depot, './...'),)
    dst_whole_view = ((dst_whole_depot, './...'),)
    dst_group_view = ((dst_group_depot, './...'),)

    src_mapping = list(map(P4Server.WorkspaceMapping._make, src_view))
    dst_whole_mapping = list(
        map(P4Server.WorkspaceMapping._make, dst_whole_view))
    dst_group_mapping = list(
        map(P4Server.WorkspaceMapping._make, dst_group_view))

    replicate_P4P4Replicate(src_mapping, dst_whole_mapping,
                            src_docker_cli, dst_whole_docker_cli)

    # replicate depot in group to dst_group_depot and verify
    src_changes = get_changelist_in_sample_depot(src_docker_cli, src_depot)
    src_changes = list(map(int, src_changes))
    src_changes.insert(0, 0)

    num_changes_to_replicate = len(src_changes)

    prefix_repinfo = False
    # while num_changes_to_replicate > 0:
    for src_counter_ver in src_changes[::num_changes_per_round]:
        ws_root = tempfile.mkdtemp(
            prefix='buildtest_group', dir=os.path.join(
                scriptRootDir, 'test/replication'))
        # -1 for definition of counter is something like 'last
        # -submitted change'
        #src_counter_ver = src_changes[-num_changes_to_replicate] - 1
        #replicate_change_num = min(num_changes_to_replicate, num_changes_per_round)
        replicate_change_num = num_changes_per_round

        if changing_repinfo_location:
            prefix_repinfo = not prefix_repinfo
        # src_counter, use 0 deliberately to make P4P4 script to detect it.
        #src_counter_rep = src_counter_ver if src_counter_ver % 2 else 0
        replicate_P4P4Replicate(src_mapping, dst_group_mapping,
                                src_docker_cli, dst_group_docker_cli,
                                src_counter=src_counter_ver,
                                replicate_change_num=replicate_change_num,
                                ws_root=ws_root,
                                prefix_repinfo=prefix_repinfo)
        verify_replication(src_mapping, dst_group_mapping,
                           src_docker_cli, dst_group_docker_cli,
                           src_counter=src_counter_ver,
                           replicate_change_num=replicate_change_num)

        #num_changes_to_replicate -= num_changes_per_round

    # verify two replicated depots, should be identical
    verify_replication(dst_group_mapping, dst_whole_mapping,
                       dst_group_docker_cli, dst_whole_docker_cli)

    obliterate_depots(dst_group_docker_cli, dst_group_mapping)
    obliterate_depots(dst_whole_docker_cli, dst_whole_mapping)


def replicate_sample_dir(depot_dir, **kwargs):
    '''test replicating directory

    create/start src/dst docker containers.
    connect to src/dst p4d
    '''
    src_depot = '/%s/...' % depot_dir
    dst_depot = '//depot/buildtest%s/...' % depot_dir

    src_view = ((src_depot, './...'),)
    dst_view = ((dst_depot, './...'),)
    replicate_sample_view(src_view, dst_view, **kwargs)


def replicate_sample_view(src_view, dst_view,
                          src_docker_cli=None,
                          dst_docker_cli=None, **kwargs):
    '''test replicating workspace view

    @param src_view [in] list of view mapping ((from, to), (from, to),)
    @param dst_view [in] list of view mapping ((from, to), (from, to),)
    '''
    src_mapping = list(map(P4Server.WorkspaceMapping._make, src_view))
    dst_mapping = list(map(P4Server.WorkspaceMapping._make, dst_view))

    do_verification = True
    if kwargs.get('skip_verification', False):
        do_verification = False

    replicate_P4P4Replicate(src_mapping, dst_mapping,
                            src_docker_cli, dst_docker_cli, **kwargs)
    if do_verification:
        verify_replication(src_mapping, dst_mapping,
                           src_docker_cli, dst_docker_cli, **kwargs)
    if kwargs.get('obliterate', True):
        obliterate_depots(dst_docker_cli, dst_mapping)


def obliterate_all_depots(docker_cli):
    '''obliterate all directories in sample depot of p4d run in docker_cli
    '''
    p4_user = BUILD_TEST_P4D_USER
    ip = docker_cli.get_container_ip_addr()
    p4 = P4Server('%s:1666' % ip, p4_user)

    depot_mapping = p4.run_depots()
    for depot in depot_mapping:
        if not depot['map'].startswith('//'):
            p4.run_obliterate('-y', '//' + depot['map'])


@contextmanager
def get_p4d_from_docker(docker_cli, depot_dir):
    '''connect to p4d in docker_cli and yield p4 so that caller can run
    cmds.
    '''
    p4_user = BUILD_TEST_P4D_USER
    ip = docker_cli.get_container_ip_addr()
    p4 = P4Server('%s:1666' % ip, p4_user)

    depot = '/%s/...' % depot_dir
    view = ((depot, './...'),)
    mapping = list(map(P4Server.WorkspaceMapping._make, view))

    p4_user = BUILD_TEST_P4D_USER
    ip = docker_cli.get_container_ip_addr()
    p4 = P4Server('%s:1666' % ip, p4_user)

    ws_root = tempfile.mkdtemp(prefix='buildtest')
    p4.create_workspace(mapping, ws_root=ws_root)
    try:
        yield p4
    finally:
        p4.delete_workspace()
        shutil.rmtree(ws_root)


def set_p4d_unicode_mode(docker_client):
    '''set p4d in unicode mode by running "/usr/local/sbin/p4d -xi" in
    container

    @param dc docker client container instance
    '''
    cmd = '/usr/local/sbin/p4d -xi'
    id_dic = docker_client.client.exec_create(docker_client.container_id, cmd,
                                              user='root')

    result = docker_client.client.exec_start(id_dic['Id'])
    logger.info(result)
