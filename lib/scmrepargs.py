import argparse
import os

def get_arguments(src_scm, dst_scm):
    '''Get cli arguments.

    @param src_scm "P4" or "SVN"
    @param dst_scm "P4" or "SVN"
    @return args
    '''
    
    if any([s not in ['P4', 'SVN', 'p4', 'svn'] for s in [src_scm, dst_scm]]):
        raise Exception('Unsupported rep: %s => %s' % (src_scm, dst_scm)) 

    src_scm = src_scm.upper()
    dst_scm = dst_scm.upper()
    script_description = '''Script to replicate from %s to %s.

    This script reads configuration of src/target workspaces form cli
    arguments, creates two temporary workspaces and replicate from src
    to target.''' % (src_scm, dst_scm)

    def get_scm_port_example(scm):
        if scm == 'P4':
            return 'Perforce:1666'
        else:
            return 'svn://10.17.0.1:3690/repos'
    src_example = get_scm_port_example(src_scm)
    dst_example = get_scm_port_example(dst_scm)

    argparser = argparse.ArgumentParser(description=script_description)

    # configuration of src and target workspaces
    srcGroup = argparser.add_argument_group('source', 'source workspace sepc')
    tgtGroup = argparser.add_argument_group('target', 'target workspace sepc')

    srcGroup.add_argument('--source-port', required=True,
                           help='server:portnum, e.g. %s' % src_example)
    srcGroup.add_argument('--source-user',
                          default=os.environ.get('SCMREP_SOURCE_USER'),
                          help='source user, or config by env variable '
                          'SCMREP_SOURCE_USER')
    srcGroup.add_argument('--source-passwd',
                          default=os.environ.get('SCMREP_SOURCE_PASS'),
                          help='source user password, or config by env variable '
                          'SCMREP_SOURCE_PASS')
    # keep backward compatibility
    srcGroup.add_argument('--source-replicate-dir-cfgfile',
                            help='cfg file name for source workspace mapping')
    srcGroup.add_argument('--source-workspace-view-cfgfile',
                           help='cfg file name for source workspace mapping')
    srcGroup.add_argument('--source-counter', default='0',
                           help='last replicated change number, '
                                'default 0, i.e. all changes')
    srcGroup.add_argument('--source-last-changeset', default=None,
                           help='last changeset to replicat, default #head')
    srcGroup.add_argument('--svn-ignore-externals', action='store_true',
                           help='for svn-p4 rep, ignore externals when updating')
    srcGroup.add_argument('--source-p4-stream', default=None,
                           help='source p4 stream, if any')

    tgtGroup.add_argument('--target-port', required=True,
                           help='server:portnum, e.g. %s' % dst_example)
    tgtGroup.add_argument('--target-user',
                          default=os.environ.get('SCMREP_TARGET_USER'),
                          help='target user, or config by env variable '
                          'SCMREP_TARGET_USER')
    tgtGroup.add_argument('--target-passwd',
                          default=os.environ.get('SCMREP_TARGET_PASS'),
                          help='target user password, or config by env variable '
                          'SCMREP_TARGET_PASS')
    tgtGroup.add_argument('--target-workspace-view-cfgfile', required=True,
                          help='cfg file name for target workspace mapping')
    tgtGroup.add_argument('--target-empty-file',
                           help='target empty file for ignoring integration' \
                           ' from outside of workspace.')

    # extra config of workspace
    argparser.add_argument('-r', '--workspace_root',
                           help='workspace root directory, by default $PWD')
    argparser.add_argument('-i', '--uniqueid',
                           help='unique string to put in workspace name')
    argparser.add_argument('-m', '--maximum',
                           help='maximum number of change to replicate')
    argparser.add_argument('--suffix-description-with-replication-info',
                           action='store_true',
                           help=('obselete, no longer used. if set, add'
                                 ' replication info after original'
                                 ' description. Otherwise, before it'))
    argparser.add_argument('--prefix-description-with-replication-info',
                           action='store_true',
                           help=('if set, add replication info before original'
                                 ' description. by default, after it'))
    argparser.add_argument('--replicate-user-and-timestamp', action='store_true',
                           help='Enable replication of user and timestamp '\
                           'of source changelist. NOTE! needs "admin" ' \
                           'access for this operation.')

    # general config
    argparser.add_argument('-v', '--verbose', default='INFO',
                           choices=('DEBUG', 'INFO', 'WARNING',
                                    'ERROR', 'CRITICAL'),
                           help="Set level of logging")
    argparser.add_argument('--dry-run', action='store_true',
                           help="printing actions to be taken")

    return argparser.parse_args()
