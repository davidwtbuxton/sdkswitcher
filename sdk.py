#!/usr/bin/env python
import argparse
import distutils.version
import errno
import io
import logging
import os
import re
import shutil
import sys
import tempfile
import urllib2
import zipfile

try:
    import configparser
except ImportError:
    import ConfigParser as configparser


SDK_DOWNLOAD_URL = 'https://storage.googleapis.com/appengine-sdks/featured/google_appengine_%s.zip'
SDK_OLD_DOWNLOAD_URL = 'https://storage.googleapis.com/appengine-sdks/deprecated/%s/google_appengine_%s.zip'
CONFIG_FILENAME = 'sdkswitcher.ini'
SDK_VERSION_LATEST = 'latest'
SDK_VERSION_PATTERN = re.compile(r'^\d+\.\d+\.\d+$') # Like '1.9.57'
SDK_VERSION_CHECK_URL = 'https://appengine.google.com/api/updatecheck'
UTF8 = 'utf-8'


logger = logging.getLogger(__name__)


class BadVersionString(ValueError):
    """The version was not valid."""


def make_parser(env):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    ac_parser = subparsers.add_parser('activate')
    ac_parser.add_argument('version')
    ac_parser.set_defaults(command=env.activate)
    # Py2.7 argparse doesn't understand the `aliases` keyword.
    subparsers._name_parser_map['ac'] = ac_parser

    check_parser = subparsers.add_parser('check')
    check_parser.set_defaults(command=env.check)

    dl_parser = subparsers.add_parser('download')
    dl_parser.add_argument('version')
    dl_parser.set_defaults(command=env.download)
    subparsers._name_parser_map['dl'] = dl_parser

    in_parser = subparsers.add_parser('install')
    in_parser.add_argument('version')
    in_parser.set_defaults(command=env.install)

    ln_parser = subparsers.add_parser('link')
    ln_parser.add_argument('dest')
    ln_parser.set_defaults(command=env.link)
    subparsers._name_parser_map['ln'] = ln_parser

    rm_parser = subparsers.add_parser('remove')
    rm_parser.add_argument('version')
    rm_parser.set_defaults(command=env.remove)
    subparsers._name_parser_map['rm'] = rm_parser

    summary_parser = subparsers.add_parser('summary')
    summary_parser.set_defaults(command=env.summary)


    return parser


class Env(object):
    """Reads preferences, handles the cached SDKs."""
    config_defaults = {
        # By default create the SDK symlink in the user home directory.
        'link': '~/',
        'cache_dir': '',
    }

    def __init__(self, config=None):
        if config is None:
            config = self.default_config()

        self.config = config

    @classmethod
    def load(cls):
        """Returns an Env instance. If the env doesn't exist, a new env is
        returned.
        """
        filename = cls.config_filename()
        config = cls.default_config()
        config.read(filename)
        obj = cls(config=config)

        return obj

    @classmethod
    def config_dir(cls):
        """The directory to save preferences (and SDKs by default)."""
        if sys.platform.startswith('darwin'):
            path = '~/Library/Application Support/'
        elif sys.platform.startswith('win'):
            path = '~\\Application Settings\\'
        else:
            path = '~/.'

        path += 'sdkswitcher'

        return path

    @classmethod
    def config_filename(cls):
        """The path to the sdkswitcher.ini configuration file."""
        filename = os.path.join(cls.config_dir(), CONFIG_FILENAME)
        filename = os.path.expanduser(filename)
        filename = os.path.abspath(filename)

        return filename

    @classmethod
    def default_config(cls):
        return configparser.ConfigParser(defaults=cls.config_defaults)

    def cache_dir(self):
        """The full directory to store cached SDKs."""
        cache_dir = self.config.defaults()['cache_dir']

        if not cache_dir:
            cache_dir = self.config_dir()

        cache_dir = os.path.expanduser(cache_dir)
        cache_dir = os.path.abspath(cache_dir)

        return cache_dir

    def sdk_link(self):
        """The currently configured location for the full SDK symlink."""
        link = self.config.defaults()['link']

        if link:
            link = os.path.expanduser(link)
            # Whatever the user chooses, the link itself is called 'google_appengine'.
            link = os.path.join(link, 'google_appengine')
            link = os.path.abspath(link)

        return link

    def save_config(self):
        filename = self.config_filename()

        with open(filename, 'w') as fh:
            self.config.write(fh)

        return filename

    def activate(self, version):
        self._activate(version)
        version = self.active_version()
        sys.stdout.write('SDK version %s is now active.\n' % version)

    def _activate(self, version):
        version = self._resolve_version(version)
        link = self.sdk_link()
        cache_dir = self.cache_dir()
        target = os.path.join(cache_dir, version, 'google_appengine')
        try:
            os.symlink(target, link)
        except OSError as err:
            if err.errno == errno.EEXIST:
                # (17, 'File exists'):
                os.unlink(link)
                os.symlink(target, link)
            else:
                raise

        return target

    def active_version(self):
        """Find the currently active SDK (if any)."""
        sdk_link = self.sdk_link()

        try:
            target = os.readlink(sdk_link)
        except OSError as err:
            if err.errno == errno.ENOENT:
                # (2, 'No such file or directory') No symlink. Version is None.
                return
            else:
                raise

        dname, fname = os.path.split(target)

        assert fname == 'google_appengine'

        version = os.path.basename(dname)

        return version

    def check(self):
        version = self._check()
        sys.stdout.write('Latest version: %s\n' % version)

        return version

    def _check(self):
        pattern = re.compile(r'\brelease: "([^"]+)"')
        response = urllib2.urlopen(SDK_VERSION_CHECK_URL)

        for line in response:
            match = pattern.search(line)

            if match:
                return match.group(1)

    def download(self, version):
        version = self._resolve_version(version)
        sys.stdout.write('Downloading SDK version %s\n' % version)

        filename = self._download(version)
        sys.stdout.write('Saved as %s\n' % filename)

        return filename

    def _download(self, version):
        url = self._sdk_url(version)
        try:
            response = urllib2.urlopen(url)
        except urllib2.HTTPError:
            # Didn't work, maybe it's an old deprecated SDK?
            url = self._sdk_url_deprecated(version)
            response = urllib2.urlopen(url)

        suffix = safe_filename(url)
        _, filename = tempfile.mkstemp(suffix=suffix)

        with open(filename, 'wb') as fh:
            fh.write(response.read())

        return filename

    @classmethod
    def _sdk_url(cls, version):
        return SDK_DOWNLOAD_URL % (version,)

    @classmethod
    def _sdk_url_deprecated(cls, version):
        version_no_dots = version.replace('.', '')

        return SDK_OLD_DOWNLOAD_URL % (version_no_dots, version)

    def install(self, version):
        """Install an SDK version.

        This will check for the latest version, download it, extract it and
        activate it if necessary. Else will activate a previously installed
        version.
        """
        version = self._resolve_version(version)
        installed_versions = self._get_installed_versions()

        sys.stdout.write('Installing SDK version %s\n' % version)

        if version not in installed_versions:
            sys.stdout.write('Downloading...\n')
            filename = self._download(version)
            self._extract(filename, version)

            sys.stdout.write('Extracted SDK version %s\n' % version)

        self.activate(version)

    def _extract(self, filename, version):
        target = self.cache_dir()
        target = os.path.join(target, version)

        with zipfile.ZipFile(filename, 'r') as archive:
            archive.extractall(target)

        # Now set the SDK scripts as executable.
        target_sdk = os.path.join(target, 'google_appengine')

        for root, dirs, files in os.walk(target_sdk):
            for f in files:
                if f.endswith('.py'):
                    f = os.path.join(root, f)
                    mode = os.stat(f).st_mode
                    # Add execute bit for owner, group, others.
                    mode = mode | 0o111
                    os.chmod(f, mode)

            # Only top-level scripts.
            break

        return target

    def link(self, dest):
        """Set the SDK symlink in preferences.

        If there is an active SDK, the symlink is recreated.
        """
        old_link = self.sdk_link()
        version = self.active_version()

        # Let's create the new link first, in case it fails for some reason.
        # Then we can clean up the old one.

        self.config.set(configparser.DEFAULTSECT, 'link', dest)

        new_link = self.sdk_link()

        if version and (old_link != new_link):

            self.activate(version)

            # Now delete the previous symlink.
            if old_link:
                os.unlink(old_link)

        self.save_config()

    def remove(self, version):
        """Delete installed SDK versions."""
        version = self._resolve_version(version)
        sys.stdout.write('Removing SDK version %s\n' % version)

        filename = self._remove(version)
        sys.stdout.write('Removed %s\n' % filename)

    def _remove(self, version):
        cache_dir = self.cache_dir()
        target = os.path.join(cache_dir, version)

        shutil.rmtree(target)

        return target

    def summary(self):
        """List the installed SDK versions and indicate which is active."""
        value = self._summary()
        value = value.encode(UTF8)
        sys.stdout.write(value)
        sys.stdout.write('\n')

        return value

    def _summary(self):
        """Returns summary as a string."""
        installed_versions = self._get_installed_versions()
        config_filename = self.config_filename()
        cache_dir = self.cache_dir()
        active = self.active_version()
        link = self.sdk_link()

        out = io.StringIO()

        out.write(u'Reading preferences from {}\n'.format(config_filename))
        out.write(u'{} SDKs in {}\n'.format(len(installed_versions), cache_dir))
        out.write(u'SDK symlink is {}\n'.format(link))
        out.write(u'\n')

        for version in installed_versions:
            flag = u' *' if version == active else u''

            out.write(u'{:>10}{}\n'.format(version, flag))

        value = out.getvalue()

        return value

    def _get_installed_versions(self):
        """Returns a list of SDK version strings.

        The versions are sorted so that 1.9.5 is before 1.9.40.
        """
        cache_dir = self.cache_dir()

        versions = []

        for root, dirs, files in os.walk(cache_dir):
            for d in dirs:
                sdk_path = os.path.join(root, d, 'google_appengine')

                if os.path.exists(sdk_path):
                    versions.append(d)

            break

        versions.sort(key=distutils.version.LooseVersion)

        return versions

    def _resolve_version(self, version):
        """Returns an SDK version after resolving ambiguous values.

        For 'latest', this will hit the network to check the latest published
        SDK version.

        For a short version like '57', this will check if there is an installed
        SDK version that matches.

        Raises BadVersionString if the value isn't a valid version string, or if
        it matches more than 1 installed SDK.
        """
        if version == SDK_VERSION_LATEST:
            return self._check()

        # It's something like '1.9.57'.
        if SDK_VERSION_PATTERN.match(version):
            return version

        # It's incomplete, like '57'. See if it matches a cached version.
        installed_versions = self._get_installed_versions()
        pattern = re.escape(version)
        matches = [re.search(pattern, v) for v in installed_versions]
        matches = [m for m in matches if m]

        if len(matches) == 1:
            return matches[0].string

        raise BadVersionString


def safe_filename(url):
    """Returns a string to use as a filename.

    Raises ValueError if there is no suitable filename.

    >>> safe_filename('https://example.com/google_appengine_1.9.57.zip')
    'google_appengine_1.9.57.zip'
    """
    url = url.strip('/')
    _, _, filename = url.rpartition('/')
    filename = re.sub(r'[^-_.a-zA-Z0-9]+', '.', filename)
    filename = re.sub(r'\.+', '.', filename)
    filename = filename.strip('.')

    # If we've stripped everything out, fail.
    if not filename:
        raise ValueError

    return filename


def main():
    env = Env.load()
    parser = make_parser(env)

    # Special case no arguments to show summary as well as help.
    if len(sys.argv) == 1:
        env.summary()
        parser.print_help()
        return 0

    args = parser.parse_args()

    # Call the command with any command-line arguments as keywords.
    kwargs = vars(args)
    command = kwargs.pop('command')
    command(**kwargs)

    return 0


if __name__ == '__main__':
    main()
