'''some useful functions
'''

import contextlib
import os
import shutil


def generate_file_hash(filename):
    '''generate hash of contents of file

    @param filename [in] name of file to hash
    '''
    import hashlib

    hasher = hashlib.sha256()
    blocksize = 65536

    with open(filename, 'rb') as fo:
        buf = fo.read(blocksize)

        while len(buf) > 0:
            buf = buf.replace('\r\n'.encode(), '\n'.encode())
            buf = buf.replace('\r'.encode(), '\n'.encode())
            hasher.update(buf)
            buf = fo.read(blocksize)

    return hasher.hexdigest()


def generate_random_str(strlen=6):
    import random
    import string
    return ''.join(random.choice(string.ascii_lowercase)
                   for _ in range(strlen))


@contextlib.contextmanager
def working_in_dir(working_dir):
    '''change python cwd to working_dir and then change back to allow
    caller to work temporarily in working_dir
    '''
    cwd = os.getcwd()
    try:
        os.chdir(working_dir)
        yield
    finally:
        os.chdir(cwd)


def remove_dir_contents(directory, excludes=None):
    '''remove contents of directory, but don't remove directory.

    @param directory, string of path to cleanup
    @param excludes, list of strings of path to exclude
    '''
    if excludes is None:
        excludes = []

    for file_name in os.listdir(directory):
        if file_name in excludes:
            continue

        file_name = os.path.join(directory, file_name)
        if os.path.isfile(file_name) or os.path.islink(file_name):
            os.unlink(file_name)
        else:
            shutil.rmtree(file_name)


def get_list_attribute(list_of_dict, attr):
    '''Get list of attributes from a list of dictionary
    '''
    list_of_attrs = [d.get(attr) for d in list_of_dict]
    list_of_attrs = [_f for _f in list_of_attrs if _f]
    return list_of_attrs


def get_file_exec_bits(fpath):
    if os.path.isfile(fpath):
        import stat
        f_st = os.lstat(fpath)
        st_exe_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        file_exe_bits = f_st.st_mode & st_exe_bits
        return file_exe_bits

    return 0


def get_dir_file_hash(
        dir_root,
        exclude=None,
        detect_dir=True,
        excluded_files=None):
    file_comp_attr = {}

    if not exclude:
        exclude = []

    exclude = [os.path.join(dir_root, exc_dir.lstrip(
        '/')) if exc_dir.startswith('/') else exc_dir for exc_dir in exclude]

    def exclude_path(file_in_dir):
        should_be_excluded = False
        for exc_dir in exclude:
            if exc_dir.startswith('/'):
                should_be_excluded = file_in_dir.startswith(exc_dir + '/')
            else:
                should_be_excluded = exc_dir in file_in_dir

            if should_be_excluded:
                return True

        if (excluded_files and
                any([file_in_dir.endswith(ef) for ef in excluded_files])):
            return True

    len_dir_root = len(dir_root)
    for walk_root, dirs, names in os.walk(dir_root):
        if detect_dir:
            for dir_name in dirs:
                file_in_dir = os.path.join(walk_root, dir_name)
                should_be_excluded = exclude_path(file_in_dir)
                if should_be_excluded:
                    continue
                dir_name = walk_root[len_dir_root:]
                if dir_name:
                    file_comp_attr[dir_name] = 'is a directory'

        for name in names:
            file_in_dir = os.path.join(walk_root, name)

            should_be_excluded = exclude_path(file_in_dir)
            if should_be_excluded:
                continue

            # Include directories in the output dict, so that they could
            # also be compared.
            if detect_dir:
                dir_name = walk_root[len_dir_root:]
                if dir_name:
                    file_comp_attr[dir_name] = 'is a directory'

            file_exec_bit = get_file_exec_bits(file_in_dir)
            file_relative = '.' + file_in_dir[len(dir_root):]
            if os.path.isfile(file_in_dir):
                file_hash = generate_file_hash(file_in_dir)
                file_comp_attr[file_relative] = [file_hash, file_exec_bit]
            elif os.path.islink(file_in_dir):
                link_to = os.readlink(file_in_dir)
                file_comp_attr[file_relative] = [link_to, file_exec_bit]

    return file_comp_attr


def get_common_stem(list_of_paths, wc_dir):
    '''find common stem of paths

    @param list_of_paths a list of path strings
    '''
    # sort the paths, from long paths to short paths
    list_of_paths = [p[:-1] if p[-1] == '/' else p for p in list_of_paths]
    list_of_paths = list(set(list_of_paths))
    list_of_paths = sorted(list_of_paths, key=len)

    should_be_removed = []
    for idx, short_path in enumerate(list_of_paths):
        if short_path in should_be_removed:
            continue

        for longer_path in list_of_paths[idx + 1:]:
            longer_path_dir, _ = os.path.split(longer_path)

            if longer_path_dir.startswith(short_path + "/"):
                should_be_removed.append(longer_path)

    list_of_paths = list(set(list_of_paths) - set(should_be_removed))

    return list_of_paths


def print_data(name, data):
    '''try to print all the details of a data instance

    @param name, string of name of data
    @param data, any kind of object instance
    '''
    type_of_v = type(data)
    if hasattr(data, 'keys'):
        # could be a dictionary
        for k in list(data.keys()):
            v = data.get(k)
            print_data('%s.%s' % (name, k), v)
    elif type_of_v is list:
        for ve in data:
            print_data('%s[]' % name, ve)
    elif type_of_v is str:
        print('%s: %s' % (name, data))
    else:
        print('%s: %s' % (name, data))


def sleep_until_interrupted(seconds=3600):
    import time
    try:
        time.sleep(seconds)
    except BaseException:
        pass
