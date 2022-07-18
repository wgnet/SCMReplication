#!/usr/bin/python3

from datetime import datetime, tzinfo, timedelta
import re


class ReplicationException(Exception):
    '''exception raised by replication scripts

    '''
    pass


default_description_rep_info_pattern = {
    'formatter': (
        'Imported from {srcserver}\n'
        'r{revision}|{submitter}|{submittime}'), 'extracter': (
            'Imported from (?P<srcserver>.+)\n'
            'r(?P<revision>[0-9]+)\|(?P<submitter>.+)\|(?P<submittime>.+)')}


def get_revision_from_desc(desc, pattern=default_description_rep_info_pattern):
    description_lines = desc.strip().split('\n')
    description_lines = [l.strip() for l in description_lines]
    description_lines = [_f for _f in description_lines if _f]

    desc_pattern = pattern['extracter']

    # get the lines of replication info from target change description
    num_lines_rep_info = len(desc_pattern.split('\n'))

    # if it's prefixed, we get the rep info lines from the beginning
    rep_info_line_idx_front = (0, num_lines_rep_info)

    # otherwise, we get the rep info lines from the end
    num_desc_lines = len(description_lines)
    rep_info_line_idx_end = (num_desc_lines - num_lines_rep_info,
                             num_desc_lines)

    rep_info_line_idx = [rep_info_line_idx_front, rep_info_line_idx_end]
    for start_line_idx, end_line_idx in rep_info_line_idx:
        rep_info_lines = description_lines[start_line_idx:end_line_idx]
        rep_info = '\n'.join(rep_info_lines)

        # extract revision from description
        match = re.match(desc_pattern, rep_info)
        if match:
            break

    if not match:
        return 0

    last_replicated_changelist = match.group('revision')

    return int(last_replicated_changelist)


class ReplicationSCM(object):
    '''base class of svn and p4 replication classes
    '''

    def __init__(self, section, cfg_parser):
        #[(str_option_name, boolean_optional), ]
        if not self.option_properties:
            raise ReplicationException('option_properties not initialized')

        self.config_scm_from_cfg_file(cfg_parser, section)

        # default replication info to be added in description of new changes
        self.description_rep_info_pattern = default_description_rep_info_pattern

        self.cli_arguments = None

    def set_desc_rep_info_pattern(self, str_formatter, re_extracter):
        self.description_rep_info_pattern['formatter'] = str_formatter
        self.description_rep_info_pattern['extracter'] = re_extracter

    def config_scm_from_cfg_file(self, cfg_parser, section):
        if not cfg_parser.has_section(section):
            err_msg = 'Config file has no section: %s' % section
            raise ReplicationException(err_msg)

        for option, optional in self.option_properties:
            self._read_property_option(cfg_parser, section, option, optional)

    def _read_property_option(self, cfg_parser, section, option, optional):
        '''Read options from cfg file and set instance property accordingly

        @param cfg_parser ConfigParser instance
        @param section string of cfg section, could be "source" or "target"
        @param option string of name of property
        @param optional is this property optional or required

        '''
        if cfg_parser.has_option(section, option):
            self.__dict__[option] = cfg_parser.get(section, option)
            return

        if optional:
            self.__dict__[option] = None
            return

        err_msg = 'Required option %s not found in "%s"' % (option, section)
        raise ReplicationException(err_msg)

    def update_to_revision(self, revision):
        raise NotImplementedError()

    def get_commit_message_of_rev(self):
        raise NotImplementedError()

    def get_replicated_rev(self, rev=None):
        '''get last replicated revision from info in change description

        If source counter is not given from cmd line arguments, we could
        try to get it from description of changes replicated last time.

        When replicating changes, we prefix or suffix the description
        of original change with a string of certain format. The prefix
        is usually like
        'Automated import from perforce change {revision} from {srcserver}'
        where {revision} is the revision of changelist from which this new
        change was replicated. So {revision} from the description of
        the last replicated change is the one we should start from
        this time.

        @return string of last source changelist which was replicated last
        time. -1 if depot doesn't exist.
        '''
        last_descs = self.get_commit_message_of_rev(num_of_rev=64)
        if not last_descs:
            return []

        repped_revs = [
            get_revision_from_desc(
                desc,
                pattern=self.description_rep_info_pattern) for desc in last_descs]

        return repped_revs

    def get_last_replicated_rev(self):
        return self.get_replicated_rev()

    def format_replication_info(self, src_rev, src_srv,
                                orig_submitter=None,
                                orig_submit_time=None):
        '''generate replication info with given info

        For now, we need to support two kinds of rep_info_patterns:
          'Automated import from perforce change {changelist} from {srcserver}'
          'Imported from {srcserver}\nr{revision}|{submitter}|{submittime}'

        @param src_rev source revision being replicated
        @param src_srv name of source server
        @param orig_submitter original submitter of the change being replicated
        @param orig_submit_time submitting time of the change being replicated
        @return string of replication information
        '''
        rep_info_pattern = self.description_rep_info_pattern['formatter']
        self.logger.debug('rep_info_pattern: %s' % rep_info_pattern)

        # date in change is in epoch time, we need it in canonical form
        class UTC(tzinfo):
            """UTC"""

            def utcoffset(self, dt):
                return timedelta(0)

            def tzname(self, dt):
                return "UTC +1"

            def dst(self, dt):
                return timedelta(0)

        utc = UTC()
        if orig_submit_time:
            orig_submit_time_dt = datetime.fromtimestamp(
                float(orig_submit_time), utc)
            orig_submit_time_isofmt = orig_submit_time_dt.isoformat()
        else:
            orig_submit_time_isofmt = ''

        rep_info = rep_info_pattern.format(srcserver=src_srv,
                                           revision=src_rev,
                                           submitter=orig_submitter,
                                           submittime=orig_submit_time_isofmt)

        return rep_info

    def sanitise_commit_message(self, desc):
        desc = desc.replace('\r', '')
        return desc

    def format_replicate_desc(self, desc, src_rev, src_srv,
                              orig_submitter, orig_submit_time):
        '''use description prefix pattern to format p4 commit message

        @param desc string of change description
        @param src_rev, source revision number that we are replicating
        @param src_srv, source server
        @param orig_submitter, submitter of original change
        @param orig_submit_time, submit time of original change
        @return string of new description with replication message
        '''
        rep_info = self.format_replication_info(src_rev, src_srv,
                                                orig_submitter,
                                                orig_submit_time)

        if self.cli_arguments.prefix_description_with_replication_info:
            # prefix
            desc = rep_info + '\n\n' + desc.lstrip()
        else:
            # suffix
            desc = desc.rstrip() + '\n\n' + rep_info

        desc = self.sanitise_commit_message(desc)

        return desc
