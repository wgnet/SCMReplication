'''wrapper of P4 class

We add this wrapper so that we can have some flexibility in the
future.

'''

import os
import argparse
from socket import gethostname
from collections import namedtuple

import P4
from buildlogger import getLogger
from buildcommon import generate_random_str

srv_account_passwd = dict()
class P4Server(P4.P4):
    '''P4 wrapper with methods to create/delete temporary workspace.
    '''

    WorkspaceMapping = namedtuple('WorkspaceMapping',
                                  ['depot_dir', 'rel_dir'])

    def __init__(self, port, user=None, password=None, login=True,
                 log_level='WARNING', **kwargs):
        user = user if user else generate_random_str()
        password = password if password else generate_random_str()

        port_user = '%s_%s' % (port, user)
        srv_account_passwd[port_user] = password[:]
        super(P4Server, self).__init__(port=port, user=user,
                                       password=password, **kwargs)

        # not sure if we need this
        self.disable_tmp_cleanup()

        # set logger
        logger = getLogger('p4server-' + port)
        self.logger = logger
        self.logger.setLevel(log_level)

        if login:
            self.connect()
            self.try_login()

        self.logger.debug('P4Server created successfully')

    def __del__(self):
        if self.connected():
            self.disconnect()

        super(P4Server, self).__del__()

    def try_login(self):
        from localestring import locale_encoding
        locale_to_p4charset = {'cp1251':'cp1251',
                               'utf-8':'utf8',}
        try:
            self.run_login()
        except Exception, e:
            if 'Unicode server permits only unicode enabled clients' in str(e):
                self.charset = locale_to_p4charset[locale_encoding.lower()]
                self.run_login()
            else:
                raise

    def create_workspace(self, ws_mapping, ws_root=None, unique_id=None,
                         line_end='share', stream=None):
        '''create new p4 workspace

        Workspace specification is composed with information from P4 and
        other arguments and assigned to p4.input. Then new workspace is
        created by calling "p4 client -i" which reads workspace spec from
        stdin.

        @param ws_mapping [in] list of instance(s) of WorkspaceMapping
        @param ws_root [in] string of absolute dir used as root of workspace
        @param unique_id [in] string to be appended at the end of workspace name
        @param stream [in] stream to be used
        '''
        if not ws_root:
            ws_root = os.getcwd()

        if not unique_id:
            unique_id = generate_random_str(10)

        # ws_mapping should be list of instance of WorkspaceMapping
        is_ws_map = lambda inst: isinstance(inst, P4Server.WorkspaceMapping)
        if not all(map(is_ws_map, ws_mapping)):
            raise Exception('Invalid workspace mapping format %s' % ws_mapping)

        # right-hand side of tuple should be path relative to ws_root
        is_rel_path = lambda inst: inst.rel_dir.startswith('./')
        if not all(map(is_rel_path, ws_mapping)):
            raise Exception('right-hand map should be relative path to ws root')

        ws_name = '%s_%s_replication-script_%s' % (self.user,
                                                   gethostname(),
                                                   unique_id)

        ws_view = ''.join(['\t%s   //%s%s\n' % (depot, ws_name, rel_dir[1:])
                           for depot, rel_dir in ws_mapping])

        if line_end not in ['local', 'share', 'unix', 'win']:
            raise Exception('probably not correct line end %s' % line_end)

        ws_spec = {'Client': ws_name,
                   'Description': 'Temp workspace created for replication',
                   'Owner': self.user,
                   'LineEnd': line_end,
                   'Root': ws_root,
                   'Options': ('noallwrite noclobber nocompress '
                               'unlocked nomodtime normdir'),
                   'View': ws_view}
        if stream:
            ws_spec['Stream'] = stream
            del ws_spec['View']

        ws_spec = '\n'.join('%s: %s' % (k, v) for k, v in ws_spec.items())

        self.input = ws_spec
        self.run_client('-i')
        self.logger.info('Created new workspace: %s' % ws_spec)

        self.cwd = ws_root
        self.client = ws_name

        if stream:
            try:
                self.run_switch(stream)
            except:
                pass

        return ws_name

    def is_unicode_server(self):
        '''by default, p4.charset is none unless we set it explicitely for
        communication with p4 server that run in unicode mode.
        '''
        return self.charset != 'none'

    def delete_workspace(self):
        '''delete p4 workspace
        '''
        ws_name = self.client
        try:
            self.delete_client(ws_name)
        except P4.P4Exception, e:
            exc_msg = str(e)

            if 'Connection reset by peer' in exc_msg:
                self.logger.info('Try again to delete the client %s' % ws_name)
                if self.connected():
                    self.disconnect()

                port_user = '%s_%s' % (self.port, self.user)
                passwd = srv_account_passwd[port_user]
                self.password = passwd
                self.connect()
                self.run_login()
                self.delete_client(self.client)
            else:
                msg = 'Failed to delete client %s, %s' % (ws_name, exc_msg)
                self.logger.error(msg)
                raise

    def get_depot_path_map(self, root=None):
        '''get depot -> abs path mapping of current client in p4
    
        @return instance of P4.Map, from depot to abs path
        '''
        ws_spec = self.fetch_client(self.client)
        depot_to_root = P4.Map(ws_spec._view)
        root = root if root else ws_spec._root

        root_to_path = P4.Map('//%s/...   %s/...' % (self.client, root))
        depot_to_path = P4.Map.join(depot_to_root, root_to_path)

        return depot_to_path
