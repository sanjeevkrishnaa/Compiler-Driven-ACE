# Launcher failure: virtual-environment symlink dereference

The first manifest launch failed before importing the simulator. The launcher had
resolved the explicitly supplied `.venv/bin/python` symlink to the framework's
system Python executable, which removed the virtual environment's site-packages
and caused `ModuleNotFoundError: sequence`.

The preserved `failed.json`, `stdout.log`, and `stderr.log` are the original
failure evidence. Commit `4708ae3` changed the launcher to make the interpreter
path absolute without dereferencing it and added a regression test. The exact same
manifest job then completed and passed the resume validator.
