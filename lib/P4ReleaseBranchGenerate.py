#!/usr/bin/python3

import json
import traceback
import tempfile
import shutil

from datetime import datetime, timedelta
import re

from .buildcommon import generate_random_str
from .buildlogger import getLogger
from P4 import P4Exception, P4
from .p4server import P4Server
from pprint import pprint, pformat


logger = getLogger(__name__)
p4_srv_utc_offset = None


class P4RBGError(Exception):
    pass


def create_branch_view(p4, source_depot_dir, target_depot_dir):
    '''create a branch view from source_depot_dir to target_depot_dir

    @param p4, P4Server instance
    @param source_depot_dir, string e.g. //depot/source/branch/...
    @param target_depot_dir, string e.g. //depot/target/branch/...
    @return string, name of branch view
    '''
    branch_name = 'RBG_branch_view' + generate_random_str()
    branch_mapping = '%s %s' % (source_depot_dir, target_depot_dir)
    branch_spec = {'Branch': branch_name,
                   'Description': 'branch for release branch generation',
                   'Owner': p4.user,
                   'Options': 'unlocked',
                   'View': branch_mapping}

    branch_spec = '\n'.join('%s: %s' % (k, v)
                            for k, v in list(branch_spec.items()))

    p4.input = branch_spec
    p4.run_branch('-i')

    return branch_name


def delete_branch_view(p4, branch_view):
    '''delete branch view

    @param p4, P4Server instance
    @param branch_view, string of name of branch view
    '''
    p4.delete_branch(branch_view)
    return None


def delete_p4_workspace(p4):
    '''Delete perforce workspace

    @param p4, instance of P4Server
    '''
    p4.delete_workspace()

    # verify that client is deleted
    clients = p4.run_clients()
    if any(p4.client == cli['client'] for cli in clients):
        err_msg = '%s deleted clients: %s' % (p4.client, clients)
        raise P4RBGError(err_msg)


def create_p4_workspace(p4_port, p4_user, p4_passwd, depot_dir, verbose):
    '''create a temporary directory and p4 workspace

    @param p4_port, string, p4 port, e.g. 192.168.1.2:1666
    @param p4_user, string, p4 user
    @param p4_passwd, string
    @param depot_dir, string, depot directory, e.g. //depot/proj1/main/...
    @param verbose, string, verbosity of logger

    @return instance of p4server and string of workspace root directory
    '''
    ws_root = tempfile.mkdtemp(prefix='ReleaseBranchGenerate_')

    p4 = P4Server(p4_port, p4_user, p4_passwd)

    # read mapping from config file
    ws_mapping = list(
        map(P4Server.WorkspaceMapping._make, [(depot_dir, './...')]))

    # create workspace
    ws_name = p4.create_workspace(ws_mapping, ws_root)

    p4.exception_level = P4.RAISE_ERROR
    p4.logger.setLevel(verbose)

    return p4, ws_root


def submit_opened_files(
        p4,
        from_branch,
        src_rev,
        replicate_user_and_timestamp):
    '''run submit if any file opened

    description would be modified to indicate replication.
    @param p4, instance of P4Server
    @param from_branch, string, src branch depot dir
    @param src_rev source revision replicated

    @return new revision number if there are opened files, otherwise None.
    '''
    opened = p4.run_opened()
    if not opened:
        logger.warning('No opened file')
        return None

    # get description of original revision
    changes = p4.run_changes('-l',
                             '%s@%s,%s' % (from_branch, src_rev, src_rev))
    p4_change = changes[0]
    desc = p4_change.get('desc')
    author = p4_change.get('user')

    # remove #review from commit message
    # They trigger Swarm behaviour, and if it's #review-XXXX it
    # actually updates an existing review.
    desc = desc.replace('#review', '# review')

    # append 'copy from'
    desc = '%s\nCopied from revision @%s by %s' % (desc, src_rev, author)

    # submit change and return new revision number
    output_lines = p4.run_submit('-d', desc)
    new_change = None
    for line in output_lines:
        if 'submittedChange' in line:
            new_change = line['submittedChange']
            break

    if not new_change:
        raise P4RBGError('No submittedChange found')

    if replicate_user_and_timestamp:
        orig_timestamp = p4_change.get('time')
        update_user_and_timestamp(p4, new_change, author, orig_timestamp)

    return new_change


def get_p4_srv_timezone_delta(p4):
    '''get utc offset of p4 server timezone

    @param p4 perforce instance
    @return timedelta of timezone offset
    '''
    global p4_srv_utc_offset

    if p4_srv_utc_offset is not None:
        if not isinstance(p4_srv_utc_offset, timedelta):
            raise P4RBGError('p4_srv_utc_offset is not timedelta')

        return p4_srv_utc_offset

    p4_info = p4.run_info()[0]
    srv_time = p4_info['serverDate']
    srv_utc_offset = srv_time.split()[-2]

    re_pat_timezone = r'[+-]\d{4}'
    if (len(srv_utc_offset) != 5 or
            not re.search(re_pat_timezone, srv_utc_offset)):
        raise P4RBGError('incorrect srv_utc_offset(%s)' % srv_utc_offset)

    east = srv_utc_offset.startswith('+')
    offset_hours = int(srv_utc_offset[1:3])
    offset_minutes = int(srv_utc_offset[3:])

    if not east:
        offset_hours = -offset_hours
        offset_minutes = -offset_minutes

    p4_srv_utc_offset = timedelta(hours=offset_hours, minutes=offset_minutes)
    return p4_srv_utc_offset


def update_user_and_timestamp(p4, changelist, orig_user, orig_date):
    '''update change with original user and date

    @param new_changelist new changelist num
    @param orig_user, string of user of original change
    @param orig_date, string of date of original change
    '''
    utc_offset = get_p4_srv_timezone_delta(p4)

    # need to update the user and time stamp
    new_change = p4.fetch_change(changelist)

    new_change._user = orig_user
    orig_change_date = int(orig_date)

    # date in change is in epoch time, we need it in p4 server's timezone
    orig_utc_datetime = datetime.utcfromtimestamp(orig_change_date)
    p4_srv_datetime = orig_utc_datetime + utc_offset
    new_change._date = p4_srv_datetime.strftime("%Y/%m/%d %H:%M:%S")

    logger.debug('%s %s' % (new_change._user, new_change._date))
    try:
        p4.save_change(new_change, '-f')
    except P4Exception as e:
        err_msg = 'failed to update @%s, "admin" perm needed ' \
                  'for "p4 change -f"' % changelist
        logger.error(err_msg)
        raise


def generate_RBG_key(target_depot_dir, target_rev):
    '''generate key for ReleaseBranchGeneration

    @param target_depot_dir, string e.g. //depot/target/branch/...

    @return string of p4 key for this target depot
    '''
    dst_dir = target_depot_dir.replace('/', '_')
    dst_dir = dst_dir.replace('.', '')
    key = 'release_branch_generate-'
    key += '%s_%s' % (dst_dir, target_rev)

    return key


def get_value_of_RBG_key(p4, target_depot_dir, target_rev):
    key = generate_RBG_key(target_depot_dir, target_rev)
    k_v = p4.run_key(key)
    return k_v[0]['value']


def set_value_of_RBG_key(p4, target_depot_dir, target_revision, value):
    key = generate_RBG_key(target_depot_dir, target_revision)
    p4.run_key(key, json.dumps(value))


def get_release_branch_copy_records(p4, target_depot_dir):
    '''get record of release branch copy from p4 keys

    @param p4 instance of P4Server
    @param target_depot_dir, string e.g. //depot/target/branch/...

    @return list of dict of copy records
    '''
    key = generate_RBG_key(target_depot_dir, '*')
    copied_changes = p4.run_keys('-e', key)

    if copied_changes == []:
        return []

    copied_changes = [json.loads(cp['value']) for cp in copied_changes]
    return copied_changes


def add_release_branch_copy_record(p4, source_depot_dir,
                                   target_depot_dir, src_rev,
                                   dst_rev):
    '''add record of release branch copy in p4 keys

    @param p4 instance of P4Server
    @param source_depot_dir, string e.g. //depot/source/branch/...
    @param target_depot_dir, string e.g. //depot/target/branch/...
    @param src_rev, string of source revision
    @param dst_rev, string of target revision
    '''
    new_copy_record = {'dst_revision': dst_rev,
                       'src_revision': src_rev,
                       'src_depot': source_depot_dir}

    set_value_of_RBG_key(p4, target_depot_dir, dst_rev,
                         new_copy_record)
    return 0


def find_most_recent_common_ancestor(prev_rev_branches, curr_rev_branches):
    '''find most recent revision of two revision lists

    @param prev_rev_branches, list of rev, branch_depot pairs
    @param curr_rev_branches, list of rev, branch_depot pairs
    @return latest common revision
    '''
    logger.debug('prev_rev_branches: %s' % prev_rev_branches)
    logger.debug('curr_rev_branches: %s' % curr_rev_branches)

    if not prev_rev_branches:
        return None

    prev_revs_set = set([int(r) for r, b in prev_rev_branches])
    curr_revs_set = set([int(r) for r, b in curr_rev_branches])

    common_revs = prev_revs_set.intersection(curr_revs_set)
    if not common_revs:
        return '0'

    max_common_rev = max(common_revs)
    return str(max_common_rev)


def get_revisions_earliest_first(p4, depot, with_integrations=False):
    if with_integrations:
        changes = p4.run_changes('-i', depot)
    else:
        changes = p4.run_changes(depot)

    if not changes:
        return []

    # earliest first
    changes.reverse()

    # get revisions
    revisions = [c['change'] for c in changes]

    return revisions


def find_parent_branches(p4, depot, parent_branches):
    '''recursively find parent branches of a depot directory

    @param p4 instance of P4Server
    @param depot, depot directory, e.g. //depot/Jam/...
    @param parent_branches [out] list of depot directories
    '''
    change_revs = get_revisions_earliest_first(p4, depot)
    if not change_revs:
        return

    first_rev_of_depot = change_revs[0]
    change_desc = p4.run_describe(first_rev_of_depot)[-1]
    depotfile_rev = list(zip(change_desc['depotFile'], change_desc['rev']))
    integration_from = None
    for depot_file_path, depot_file_rev in depotfile_rev:
        depot_file_filelog = p4.run_filelog('-m1', '%s#%s' % (depot_file_path,
                                                              depot_file_rev))
        filelog = depot_file_filelog[0]
        revision = filelog.revisions[0]
        for integ in reversed(revision.integrations):
            branch_from_actions = ('copy from', 'branch from')
            if integ.how in branch_from_actions:
                integration_from = integ.file
                break
        if integration_from:
            break

    if not integration_from:
        return

    depot_branch_dir = depot[:-3]
    depot_file_path_subdir = depot_file_path[len(depot_branch_dir):]
    branch_from_dir = integration_from[:-len(depot_file_path_subdir)]
    branch_from_dir += '...'

    parent_branches.append(branch_from_dir)

    find_parent_branches(p4, branch_from_dir, parent_branches)


def get_branch_rev_hist(p4, depot_dir, src_branches):
    '''get revisions submitted to src_branches that are related to source_depot

    "p4 changes -i //depot/dir/..." gets all revisions related to //depot/dir
    "p4 changes //depot/dir/..." gets revisions submitted to //depot/dir

    @param p4 instance of P4Server
    @param depot_dir, string e.g. //depot/branch/...
    @param src_branches, parent branches of src_depot_dir(included)
    '''
    # get all revisions related to depot_dir
    # The -i flag also includes any revisions integrated into the
    # specified files
    change_revs_with_integs = get_revisions_earliest_first(
        p4, depot_dir, with_integrations=True)

    revisions = []
    branches = []
    b_revs_latest_first = []

    # from leaf branch to root branch
    for b_depot in src_branches:
        # get revisions submitted to branch
        b_revs_latest_first = get_revisions_earliest_first(p4, b_depot)
        b_revs_latest_first.reverse()
        for b_rev in b_revs_latest_first:
            if (b_rev in change_revs_with_integs and b_rev not in revisions):
                # it's possible that b_rev could appear in two branches, e.g.
                # "p4 move" could produce in src/dst depots
                revisions.append(b_rev)
                branches.append(b_depot)

    # This is quite unlikely to happen but it's possible that two
    # release branches(branched from same trunk) have no common
    # ancestor revision. E.g. two branches have totally different set
    # of files.  We append the rest revisions of trunk to the end, so
    # that such release branches could still find common ancestor.
    trunk_revs = b_revs_latest_first
    if revisions:
        last_rev = revisions[-1]
        last_branch = branches[-1]
        idx_of_last_rev = trunk_revs.index(last_rev)
        unrelated_revs_before_last = trunk_revs[idx_of_last_rev + 1:]
        revisions.extend(unrelated_revs_before_last)
        branches.extend([last_branch] * len(unrelated_revs_before_last))

    rev_branch_latest_first = list(zip(revisions, branches))

    rev_branch_latest_first.reverse()
    rev_branch_earliest_first = rev_branch_latest_first

    logger.debug('%s revision: %s' % (depot_dir,
                                      pformat(rev_branch_earliest_first)))
    return rev_branch_earliest_first


def map_src_rev_to_target_rev(src_rev_branches, copied_records, target_depot):
    '''map src revs to target revs

    These src revisions to be reverted must have been "p4
    copy"ed to target depot dir. we should reverted copied
    revisions
    '''
    copied_records_latest_first = copied_records
    copied_records_latest_first.reverse

    target_rev_branches = []
    for rev, _ in src_rev_branches:
        for rep_record in copied_records_latest_first:
            if rev == rep_record['src_revision']:
                logger.debug('%s copied as %s' % (rev,
                                                  rep_record['dst_revision']))
                target_rev_branches.append((rep_record['dst_revision'],
                                            target_depot))
                break

    return target_rev_branches


def get_revisions_to_copy(p4,
                          source_depot_dir, target_depot_dir,
                          maximum, source_last_revision):
    '''Get revision to copy, or reverse
    '''
    copied_records = get_release_branch_copy_records(p4, target_depot_dir)

    if copied_records:
        prev_source_depot = copied_records[-1]['src_depot']
    else:
        prev_source_depot = source_depot_dir
    curr_source_depot = source_depot_dir

    revs_to_reverse = []
    revs_to_copy = []
    if prev_source_depot != source_depot_dir:
        # find branch tree of src depots directories
        prev_src_branches = [prev_source_depot, ]
        curr_src_branches = [curr_source_depot, ]
        find_parent_branches(p4, prev_source_depot, prev_src_branches)
        find_parent_branches(p4, curr_source_depot, curr_src_branches)

        # get revisions of branchs that are related to src depots
        prev_src_revs = get_branch_rev_hist(p4, prev_source_depot,
                                            prev_src_branches)
        curr_src_revs = get_branch_rev_hist(p4, curr_source_depot,
                                            curr_src_branches)

        common_ancestor = find_most_recent_common_ancestor(prev_src_revs,
                                                           curr_src_revs)

        src_revs_to_reverse = [(rev, b) for rev, b in prev_src_revs
                               if int(rev) >= int(common_ancestor)]

        target_revs_to_reverse = map_src_rev_to_target_rev(src_revs_to_reverse,
                                                           copied_records,
                                                           target_depot_dir)

        # don't reverse the last revision, copying the latest one
        # makes no change to the depot
        revs_to_reverse = target_revs_to_reverse[:-1]

        revs_to_copy = [(rev, b) for rev, b in curr_src_revs
                        if int(rev) > int(common_ancestor)]
    else:
        # src (revisions, branch_depot)
        curr_changes = p4.run_changes(curr_source_depot)
        curr_changes.reverse()
        curr_rev_branches = [(c['change'], curr_source_depot)
                             for c in curr_changes]

        # copied revisions
        copied_revs = [(rec['src_revision'], curr_source_depot)
                       for rec in copied_records
                       if rec['src_depot'] == curr_source_depot]

        if not copied_revs:
            # if no copied revision found in p4 keys, it's probably
            # the 1st time this script is run. We need to find our
            # revision history of target depot, and find from which
            # revision of source depot we can resume copying.
            dst_branches = [target_depot_dir]
            find_parent_branches(p4, target_depot_dir, dst_branches)
            curr_dst_revs = get_branch_rev_hist(p4, target_depot_dir,
                                                dst_branches)
            copied_revs = curr_dst_revs

        common_ancestor = find_most_recent_common_ancestor(copied_revs,
                                                           curr_rev_branches)

        if common_ancestor:
            for idx, rev_branch in enumerate(curr_rev_branches):
                rev, b = rev_branch
                if rev == common_ancestor:
                    revs_to_copy = curr_rev_branches[idx + 1:]
        else:
            revs_to_copy = curr_rev_branches[:]

    logger.debug('*' * 80)
    logger.debug('common_ancestor = ')
    logger.debug(pformat(common_ancestor))
    logger.debug('revs_to_reverse = ')
    logger.debug(pformat(revs_to_reverse))
    logger.debug('revs_to_copy = ')
    logger.debug(pformat(revs_to_copy))

    changes = revs_to_reverse[:]
    changes.reverse()

    if maximum:
        revs_to_copy = revs_to_copy[:maximum]

    changes += revs_to_copy

    if source_last_revision:
        source_last_revision = str(source_last_revision)

        revisions = [rev for rev, branch in changes]
        if source_last_revision not in revisions:
            raise P4RBGError('%s not in %s' % (source_last_revision,
                                               revisions))
        idx_of_last_revision = revisions.index(source_last_revision)
        return changes[:idx_of_last_revision + 1]

    return changes


def get_branch_view(p4, existing_branches, from_branch, target_depot_dir):
    '''get branch view from from_branch to target_depot_dir, create if not exist
    '''
    branch_view = existing_branches.get(from_branch)
    if not branch_view:
        branch_view = create_branch_view(p4, from_branch,
                                         target_depot_dir)
        existing_branches[from_branch] = branch_view
    return branch_view


def repopulate_change_submitter_time(p4, target_depot_dir, dry_run):
    '''update copied changes with src change submitter and time

    @param p4, p4 client instance
    @param target_depot_dir, target depot , e.g. //depot/Jam-test/...
    @param dry_run, print what to do but don't do it
    '''
    copied_records = get_release_branch_copy_records(p4, target_depot_dir)

    for rec in copied_records:
        dst_rev = rec['dst_revision']
        src_rev = rec['src_revision']

        src_change_desc = p4.run_describe(src_rev)[-1]
        src_user = src_change_desc['user']
        src_time = src_change_desc['time']

        dst_change_desc = p4.run_describe(dst_rev)[-1]
        dst_user = dst_change_desc['user']
        dst_time = dst_change_desc['time']

        if (src_user != dst_user or src_time != dst_time):
            src_time_utc = datetime.utcfromtimestamp(int(src_time))
            msg = 'Updating property of change #%s, %s %s' % (dst_rev,
                                                              src_user,
                                                              src_time_utc)
            logger.info(msg)

            if dry_run:
                continue

            update_user_and_timestamp(p4, dst_rev, src_user, src_time)


def release_branch_generate(p4_port, p4_user, p4_passwd,
                            source_depot_dir, target_depot_dir,
                            replicate_user_and_timestamp=False,
                            repopulate_change_properties=False,
                            maximum=0, source_last_revision=0,
                            dry_run=False, verbose='INFO'):
    '''Release branch generation

    @param p4_port, string p4 server port
    @param p4_user, string, p4 user
    @param p4_passwd, string, password
    @param source_depot_dir, string, p4 depot to copy revisions from
    @param target_depot_dir, string, p4 depot dir of release branch
    @param maximum, integer, number of revisions to copy
    @param source_last_revision, last source revision to copy, inclusive
    @param verbose, verbosity of loggers
    '''
    logger.setLevel(verbose)

    p4, ws_root = create_p4_workspace(p4_port, p4_user, p4_passwd,
                                      target_depot_dir, verbose)
    if repopulate_change_properties:
        repopulate_change_submitter_time(p4, target_depot_dir, dry_run)

    changes = get_revisions_to_copy(p4, source_depot_dir,
                                    target_depot_dir, maximum,
                                    source_last_revision)
    copy_branch_views = {}
    try:
        for src_rev, from_branch in changes:
            logger.info('copying %s%s' % (from_branch, src_rev))
            if dry_run:
                continue

            branch_view = get_branch_view(p4, copy_branch_views,
                                          from_branch, target_depot_dir)

            p4.run_copy('-v', '-f', '-b', branch_view, '...@%s' % src_rev)
            dst_rev = submit_opened_files(p4, from_branch, src_rev,
                                          replicate_user_and_timestamp)

            if not dst_rev:
                continue

            add_release_branch_copy_record(p4, from_branch,
                                           target_depot_dir, src_rev,
                                           dst_rev)
            logger.info('new p4 change: %s' % dst_rev)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        raise
    finally:
        p4.run_revert('...')
        delete_p4_workspace(p4)
        for copy_branch in list(copy_branch_views.values()):
            delete_branch_view(p4, copy_branch)
        p4.disconnect()
        shutil.rmtree(ws_root)
