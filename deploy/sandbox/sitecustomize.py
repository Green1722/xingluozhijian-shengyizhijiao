"""Sandbox compatibility layer for running the verifiers locally.

``tempfile.mkdtemp`` creates scratch directories with POSIX mode ``0o700``.
Some restricted Windows sandboxes translate that mode into an ACL that denies
the same process further writes, so ``TemporaryDirectory`` scratch files cannot
be created and the verifiers fail with ``PermissionError: WinError 5``.

This module is never imported unless ``deploy/sandbox`` is placed on
``PYTHONPATH``.  It keeps the random naming of ``mkdtemp`` but creates the
directory with the default mode, which stays writable inside the sandbox.
Outside such a sandbox it is unnecessary; the plain verifiers work as shipped.
"""
import os
import tempfile

_candidate_names = tempfile._get_candidate_names()


def mkdtemp(suffix=None, prefix=None, dir=None):
    prefix = tempfile.gettempprefix() if prefix is None else prefix
    suffix = "" if suffix is None else suffix
    directory = tempfile.gettempdir() if dir is None else dir
    for _ in range(tempfile.TMP_MAX):
        name = os.path.join(directory, prefix + next(_candidate_names) + suffix)
        try:
            os.mkdir(name)
            return name
        except FileExistsError:
            continue
    raise FileExistsError(f"no usable temporary directory name in {directory}")


tempfile.mkdtemp = mkdtemp
