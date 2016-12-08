#!/usr/bin/env python

'''p4 to p4 replication script
'''
import os
import sys
import tempfile
import traceback

import P4
from lib.buildlogger import getLogger, set_logging_color_format
from lib.p4server import P4Server
from lib.PerforceReplicate import P4Transfer
from lib.scmrepargs import get_arguments

logger = getLogger(__name__)


def create_p4_workspace(p4, ws_cfg, line_end='share', stream=None):
    '''create a temporary p4 workspace for replication

    @param ws_cfg [in] dict of configuration of workspace

    @return instance of p4server
    '''
    # read mapping from config file
    with open(ws_cfg['mappingcfg'], 'rt') as f:
        ws_view_cfgstr = f.readlines()
        ws_view = [mapping.split() for mapping in ws_view_cfgstr]
        ws_mapping = map(P4Server.WorkspaceMapping._make, ws_view)

    # create workspace
    unique_id = ws_cfg.get('uniqueid') if hasattr(ws_cfg, 'uniqueid') else None
    ws_name = p4.create_workspace(ws_mapping, ws_cfg['ws_root'],
                                  unique_id=unique_id, line_end=line_end,
                                  stream=stream)

    # take a look to see if client is created
    if all([ws_name != cli['client'] for cli in p4.run_clients()]):
        raise Exception('failed to create client %s' % ws_name)

    return p4


def delete_p4_workspace(p4):
    '''Delete perforce workspace

    @param p4 [in] instance of P4Server
    '''
    p4.delete_workspace()


def create_PerforceReplicate_cfg_file(srcCfg, tgtCfg):
    '''create a temporary configure file for PerforceReplicate.py
    '''
    ws_cfg_item = ['p4client', 'p4port', 'p4user', 'p4passwd', 'counter',
                   'endchange', 'empty_file']

    src_cfg_str = '\n'.join(['%s=%s' % (k, v)
                             for k, v in srcCfg.items()
                             if k in ws_cfg_item and v is not None])
    tgt_cfg_str = '\n'.join(['%s=%s' %(k, v)
                             for k, v in tgtCfg.items()
                             if k in ws_cfg_item and v is not None])
    src_content = '[source]\n' + src_cfg_str
    tgt_content = '[target]\n' + tgt_cfg_str
    gen_content = '[general]\n'

    cfg_content = '\n'.join([src_content, tgt_content, gen_content])

    cfg_fd, cfg_path = tempfile.mkstemp(suffix='.cfg', text=True)
    os.write(cfg_fd, cfg_content)
    os.close(cfg_fd)

    return cfg_path


def replicate(args):
    '''Create temporary workspace and cfg file for
    lib/PerforceReplicate.py, and call it to replicate.
    '''
    src_cfg = {'p4port': args.source_port,
               'p4user': args.source_user,
               'p4passwd': args.source_passwd,
               'counter': args.source_counter,
               'endchange': args.source_last_changeset,
               'ws_root': args.workspace_root,
               'uniqueid': args.uniqueid,
               'mappingcfg': args.source_workspace_view_cfgfile, }
    dst_cfg = {'p4port': args.target_port,
               'p4user': args.target_user,
               'p4passwd': args.target_passwd,
               'counter': 0,
               'ws_root': args.workspace_root,
               'uniqueid': args.uniqueid,
               'mappingcfg': args.target_workspace_view_cfgfile,
               'empty_file': args.target_empty_file,}

    src_p4 = P4Server(src_cfg['p4port'], src_cfg['p4user'], src_cfg['p4passwd'])
    dst_p4 = P4Server(dst_cfg['p4port'], dst_cfg['p4user'], dst_cfg['p4passwd'])

    src_stream = None
    if hasattr(args, 'source_p4_stream'):
        src_stream = args.source_p4_stream
    create_p4_workspace(src_p4, src_cfg, line_end='local',
                        stream=src_stream)
    create_p4_workspace(dst_p4, dst_cfg, line_end='local')

    src_cfg['p4client'] = src_p4.client
    dst_cfg['p4client'] = dst_p4.client

    try:
        # call P4Transfer to finish replication
        p4RepCfgFile = create_PerforceReplicate_cfg_file(src_cfg, dst_cfg)
        sys.argv = [__name__, '-c', p4RepCfgFile]
        if args.maximum:
            sys.argv.extend(['-m', str(args.maximum)])

        if args.replicate_user_and_timestamp:
            sys.argv.append('--replicate-user-and-timestamp')

        if (hasattr(args, 'prefix_description_with_replication_info') and
            args.prefix_description_with_replication_info):
            sys.argv.append('--prefix-description-with-replication-info')

        if hasattr(args, 'dry_run') and args.dry_run:
            sys.argv.append('--dry-run')

        sys.argv.extend(['--verbose', args.verbose])

        p4Rep = P4Transfer(*sys.argv[1:])
        ret = p4Rep.replicate()
    except Exception, e:
        # print exception, or we wouldn't be able to see it if
        # another exception is raised in finally section
        logger.error(e)
        logger.error(traceback.format_exc())
        raise e
    finally:
        os.unlink(p4RepCfgFile)
        delete_p4_workspace(src_p4)
        delete_p4_workspace(dst_p4)

    return ret


if __name__ == '__main__':
    args = get_arguments('P4', 'P4')
    logger.setLevel(args.verbose)

    replicate(args)
