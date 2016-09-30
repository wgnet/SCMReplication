#!/usr/bin/env python

'''svn to p4 replication config file related variables and functions

Kind of outdated.
'''

from collections import OrderedDict

CONFIG = 'migrate.cfg'
TEMPLATE = 'template_migrate.cfg'
DOCUMENT_SECTION = 'document'
GENERAL_SECTION = 'general'
SOURCE_SECTION = 'source'
TARGET_SECTION = 'target'
USED_BY_PID = 'USED_BY_PID'
RUN_ID = 'RUN_ID'

# This is for writing to sample config file - OrderedDict used to preserve order of lines.
DEFAULT_CONFIG = OrderedDict({
    DOCUMENT_SECTION: OrderedDict([
        ("# This file is a historical record of the migration process. Do not delete.", None),
        ("# P4PASSWD: if password is not specified, your current ticket is used.", None),
        ("# SVN_USER: if username is not specified, your current ticket is used.", None),
        ("# SVN_PASSWD: if password is not specified, your current ticket is used.", None),
        ("# SVN_CLIENT_ROOT: The full file path to the root working copy folder.", None),
        ("#    It should match the root folder defined in the target P4CLIENT.", None),
        ("# P4CLIENT: is a workspace that maps all the files that should be considered during transfer.", None),
        ("#    This includes all the files that can be considered integration sources on the source or target.", None),
        ("# EMPTY_FILE: is a file that will be used for ignored integrations", None),
        ("#    from files outside the P4CLIENT workspace.  This file should", None),
        ("#    be empty and otherwise unused in the depot.", None),
        ("# CL_COUNTER: represents the last transferred P4 change number.", None),
        ("#    Should be initialized to 0. (Historical)", None),
        ("# REV_COUNTER: represents the last transferred Svn revision number.", None),
        ("#    Should be initialized to 0. (Historical)", None),
        ("# USED_BY_PID: represents the process identification number of the active process using this file.", None),
        ("#    Should be initialized to None. (Historical)", None),
        ("# SVN_REPO_LABEL: short friendly label for the SVN repository.", None),
        ("#    Used as part of the auto-generated change description tail.", None),
    ]),
    GENERAL_SECTION: OrderedDict([
        (USED_BY_PID, "None"),
    ]),
    SOURCE_SECTION: OrderedDict([
        ("#SVN_CLIENT_ROOT", ""),
        ("#SVN_REPO_LABEL", "MySvnRepo"),
        ("#SVN_REPO_URL", ""),
        ("#SVN_USER", ""),
        ("#SVN_PASSWD", ""),
        ("REV_COUNTER", "0"),
    ]),
    TARGET_SECTION: OrderedDict([
        ("#P4CLIENT", ""),
        ("#P4PORT", ""),
        ("#P4USER", ""),
        ("#P4PASSWD", ""),
        ("EMPTY_FILE", "ignored.txt"),
        ("CL_COUNTER", "0"),
    ]),
})

def writeTemplateConfig():
    from ConfigParser import ConfigParser

    # Do not over-write another file with the same name
    if os.path.exists(TEMPLATE):
        print("")
        print("# The template configuration file, {}, already exists".format(TEMPLATE))
        print("")
        return

    # Print defaults from above dictionary for saving as a base file
    config = ConfigParser(allow_no_value=True)
    config.optionxform = str
    ordered_secs =[SOURCE_SECTION,TARGET_SECTION,GENERAL_SECTION,DOCUMENT_SECTION]
    for sec in ordered_secs:
        config.add_section(sec)
        for k in DEFAULT_CONFIG[sec].keys():
            config.set(sec, k, DEFAULT_CONFIG[sec][k])
    print("\n# Creating a template for the required configuration file: %s\n" % TEMPLATE)
    with open(TEMPLATE, "wt") as fh:
        config.write(fh)

