SDK Switcher
============

A Python command-line tool for switching between different versions of the Google App Engine SDK.


Installation
------------

You can install from the GitHub repository using pip:

    $ pip install https://github.com/davidwtbuxton/sdkswitcher/archive/master.zip

This will install a command-line tool, `sdkswitcher`. The `sdkswitcher` tool allows one to download multiple versions of the Google App Engine Python SDK and easily create a symlink to the "active" version.

You want to add the path to the symlink to your shell's `$PATH` environment variable.


Usage
-----

Show a summary of installed SDK versions and which is active.

    $ sdkswitcher summary
    $ sdkswitcher


Download, install and activate an SDK:

    $ sdkswitcher install 1.9.57


Download, install and activate the latest SDK:

    $ sdkswitcher install latest


Activate an installed SDK:

    $ sdkswitcher activate 1.9.57
    $ sdkswitcher ac 57

When using activate, you can refer to an SDK by just part of the version number. If there is only 1 installed version that matches, it is activated. Otherwise you get an error.


Check for a new SDK:

    $ sdkswitcher check

This prints out the latest SDK version.


Delete an installed SDK:

    $ sdkswitcher remove 1.9.57
    $ sdkswitcher rm 57


Set the symlink directory for the SDK:

    $ sdkswitcher link ~/Documents/Development
    $ sdkswitcher ln ~/Documents/Development


Download an SDK without installing it or activating it:

    $ sdkswitcher download 1.9.57
    $ sdkswitcher dl 1.9.57
