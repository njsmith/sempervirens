# This file is part of sempervirens
# Copyright (C) 2015 Nathaniel Smith <njs@pobox.com>
# See file LICENSE.txt for license information.

import os
import os.path
import socket
import json
import threading
from collections import defaultdict

# import appdirs
import requests

DIRECTORY_NAME = "sempervirens"

DISABLE_ENVVAR = "SV_DISABLE"

# Cross-platform directory nonsense:
# One version (has all-versions wheel on pypi):
#    https://github.com/ActiveState/appdirs/blob/master/appdirs.py
# Critiques:
#    - Supposedly the correct way to get the OS X directory is
#         -[NSFileManager URLsForDirectory: NSApplicationSupportDirectory inDomains: NSUserDomainMask]
#      whereas the above hardcodes ~/Library/Application Support/
#    - The unixy code doesn't take any care to be robust against missing HOME
#      (Or no, wait: os.expanduser falls back on getpwduid, so I guess that's
#      correct.)
#    - The unixy code ignores the rule that if an XDG_*_HOME variable is empty
#      or contains a non-absolute path, then you should ignore it. See
#      http://standards.freedesktop.org/basedir-spec/latest/ar01s02.html
#
# Annoyingly, it's not clear to me that Windows or OS X even *have* an
# equivalent of /etc for per-machine config. I guess OS X does from this link?
#   https://apple.stackexchange.com/questions/76611/cant-access-etc-folder-in-os-x-mountain-lion
# Yeah, must be:
#   https://apple.stackexchange.com/search?q=%2Fetc
#
# Maybe we can live with an envvar for global disablement at least for now.

# DATA_DIR is something like
#   ~/.local/share/sempervirens/
#
# It contains:
#   /consent
#     {"consent-given": True,
#      "consent-type": {"program": "IPython", "version": "..."},
#      "consent-date": "2015-12-01"}
#   /install-id
#     16 bytes
#     this should permissions 0600
#   /sempervirens-python/   -- ours to play with

class OTP(object):
    def __init__(self):
        self.enabled = False
        # The main SV directory, e.g. ~/.local/share/sempervirens
        self.sempervirens_path = None
        # The directory we use for storing things, e.g.
        #    ~/.local/share/sempervirens/sempervirens-python/$HOSTNAME/
        self.data_path = None

        # {project_id:
        #   {key:
        #     {value: counter}
        self.stats = defaultdict(lambda:
                                 defaultdict(lambda:
                                             defaultdict(float)))

        if DISABLE_ENVVAR in os.environ:
            return

        user_data_path = appdirs.user_data_dir()
        if not os.path.isdir(user_data_path):
            return

        self.otp_path = os.path.join(user_data_path, DIRECTORY_NAME)
        # If the otp_path doesn't even exist, then the user has definitely not
        # consented.
        if not os.path.isdir(self.otp_path):
            return

        # if we do not own directory, then bail out
        XX

        self.otp_python_dir = os.path.join(self.sempervirens_dir,
                                           "sempervirens-python",
                                           socket.gethostname())



    def increment(self, project_id, key, value, count=1):
        self.stats[project_id][key][value] += count

    def register_poll_callback(self, project_id, fn):
        # project_id is so we can measure how slow fn() is and complain to the
        # right people if it's bad.
        XX

    def record_consent(self, version, consented):
        pass


    def _ensure_directory(self):
        if self.data_dir is None:
            return

        if not os.path.exists(self.data_dir):
            pass

def has_accepted():
    return 

def short_text():
    return "Aren't you sure you don't want not to accept data collection ?"


# Snapshotting is tricky -- what if someone comes along and uploads a partial
# snapshot? I guess we can't prevent that, and we're going to be rolling up
# sessions anyway, so eh. Just reset our internal stats (including "number of
# sessions") to 0 whenever we snapshot.


# acquire a lock to create the daily rollup
#   on temporary failure, move the rollup back into the regular directory like
#     it's a single session
#   if there are >1 week old daily rollups, (attempt to) retrieve their
#     contents and put them back into circulation
#
# locking:
#   probably the only reliable method on NFS:
#     - create a unique file
#     - link(unique file, common lock file name)
#     - stat(unique file)
#     - if unique file's link count is 2, then we own the lock
#   of course, SMB is another matter...
# BETTER IDEA: give each host its own unique data directory
#   open-telemetry-project/otp-py/branna/pending/...
#                                       /rollup-<day>
# of course, this breaks whenever a computer changes its hostname:
#   https://stackoverflow.com/questions/4271740/how-can-i-use-python-to-get-the-system-hostname#comment16118145_4271755
# Sources of unique ids:
#  - on linux with systemd (and others?): /etc/machine-id
#  - on windows there's
#       HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography\MachineGuid
#    (which is supposed to be unique, but can fail to be if someone uses a
#    non-standard method of cloning new machines, "not running sysprep")
#    Of course we could also just store our own id under HKEY_LOCAL_MACHINE
#  - On OS X there's gethostuuid()
# maybe we should just use the hostname, plus fcntl.lockf / msvcrt.locking.
# ...does fcntl locking work between processes on the same machine on nfs?
#
# -- lock /tmp/otp-<username>? dangerous if someone else grabs it first though
#   (and named mutexes are basically equivalent to this on windows)
#
# if each ping has an id attached, and we create this id by something like
#   hash(secret, date, hostname, installid), then this should reliably let us
#   see when two processes both tried to read the same day
#   and double-counting within a single user isn't *that* big a deal anyway
#   - better: give install-id, sub-install-id, reporting-period, and the
#     sub-install id is just an arbitrary nonce which should make that triple
#     unique under ordinary circumstances.
#
# docs say:
#   - on FreeBSD: mount_nfs(8) says: you can have either local locking (with
#     "nolockd" / -L), or server-side locking
#   - on Linux: nfs(5) says: "lock" -> use NLM, "nolock" -> local locking
#   - on OSX: mount_nfs(8) says: you can choose real locks, local locks, or to
#     have all lock operations return ENOTSUP
#     OSX tends to assume file locking works though I think, and who mounts
#     their OSX home directory over NFS anyway?
#
# after writing: check to see if there are previous day/week/whatever records
# if so spawn the cleaner, which will try to grab the machine-dir lock
#
# we also need some sort of permanent failure mode I guess, to prevent growing
#   unboundedly? maybe discard any single log file that is larger than a fixed
#   size (and increment a counter saying that we've done so)?
#   or just throw away anything that's more than a month out?


# stuff in ping:
#   - install-id
#   - beginning of earliest session covered
#   - end of latest session covered
#

# Things we should just go ahead and log ourselves:
#   platform type (sys.platform?)
#   python version
#   python distributor if we can figure it out?
#   32- versus 64-bit
#   other CPUID stuff? maybe better leave that to numpy; very difficult to do
#     without compiled code.
#   our own version number!
#   versions for some particular known packages
#      - numpy, scipy, matplotlib, pandas, IPython
#      eh, or maybe not. we don't even see them unless we get imported (I
#      guess that will happen via IPython, but...), and gives a skewed idea of
#      things...
#
#   our overhead: delay added to shutdown, anything else we can log cheaply?
#   ...delay added to shutdown is hard given that by the time we've measured
#      it, it's too late to record it...
#   time spent calling poll() functions would make sense to count, though


if __name__ == "__main__":
    # Have "opt-in" and "opt-out" commands
    # and "status" -- opted in/out + directory size
    # and where the directory is so people can browse around if they want
    pass
