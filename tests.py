import ConfigParser as configparser
import errno
import io
import os
import shutil
import tempfile
import unittest
import urllib2

import mock

import sdk


class SdkArgumentParsingTestCase(unittest.TestCase):
    def test_parse_summary_command(self):
        argv = ['summary']
        env = sdk.Env()
        parser = sdk.make_parser(env)
        args = parser.parse_args(argv)

        self.assertEqual(
            vars(args),
            {'command': env.summary},
        )

    def test_parse_install_command_missing_version_argument(self):
        argv = ['install']
        env = sdk.Env()
        parser = sdk.make_parser(env)

        with self.assertRaises(SystemExit) as err_context:
            parser.parse_args(argv)

        self.assertEqual(err_context.exception.code, 2)

    def test_parse_install_command(self):
        argv = ['install', '1.9.57']
        env = sdk.Env()
        parser = sdk.make_parser(env)

        args = parser.parse_args(argv)

        self.assertEqual(
            vars(args),
            {
                'command': env.install,
                'version': '1.9.57',
            },
        )

    def test_parse_check_command(self):
        argv = ['check']
        env = sdk.Env()
        parser = sdk.make_parser(env)

        args = parser.parse_args(argv)

        self.assertEqual(
            vars(args),
            {
                'command': env.check,
            },
        )

    def test_parse_remove_command(self):
        argv = ['remove', '1.9.57']
        env = sdk.Env()
        parser = sdk.make_parser(env)

        args = parser.parse_args(argv)

        self.assertEqual(
            vars(args),
            {
                'command': env.remove,
                'version': '1.9.57',
            },
        )

    def test_parse_remove_command_missing_argument(self):
        argv = ['remove']
        env = sdk.Env()
        parser = sdk.make_parser(env)

        with self.assertRaises(SystemExit) as err_context:
            parser.parse_args(argv)

        self.assertEqual(err_context.exception.code, 2)

    def test_parse_link_command(self):
        argv = ['link', '~/gae']
        env = sdk.Env()
        parser = sdk.make_parser(env)

        args = parser.parse_args(argv)

        self.assertEqual(
            vars(args),
            {
                'command': env.link,
                'dest': '~/gae',
            },
        )

    def test_parse_link_command_missing_argument(self):
        argv = ['link']
        env = sdk.Env()
        parser = sdk.make_parser(env)

        with self.assertRaises(SystemExit) as err_context:
            parser.parse_args(argv)

        self.assertEqual(err_context.exception.code, 2)


class EnvTestCase(unittest.TestCase):
    @mock.patch('sys.platform', 'darwin')
    def test_darwin_config_dir(self):
        result = sdk.Env.config_dir()

        self.assertEqual(result, '~/Library/Application Support/sdkswitcher')

    @mock.patch('sys.platform', 'win')
    def test_windows_config_dir(self):
        result = sdk.Env.config_dir()

        self.assertEqual(result, '~\Application Settings\\sdkswitcher')

    @mock.patch('sys.platform', 'linux')
    def test_linux_config_dir(self):
        result = sdk.Env.config_dir()

        self.assertEqual(result, '~/.sdkswitcher')

    @mock.patch('sys.platform', 'linux')
    @mock.patch.dict('os.environ', {'HOME': '/home/foo'})
    def test_darwin_config_filename(self):
        result = sdk.Env.config_filename()

        self.assertEqual(result, '/home/foo/.sdkswitcher/sdkswitcher.ini')

    @mock.patch('sys.platform', 'linux')
    @mock.patch.dict('os.environ', {'HOME': '/home/foo'})
    def test_cache_dir_default(self):
        # The cache dir can be configured by an INI file.
        env = sdk.Env()
        result = env.cache_dir()

        self.assertEqual(result, '/home/foo/.sdkswitcher')

    @mock.patch.dict('os.environ', {'HOME': '/home/foo'})
    def test_sdk_link(self):
        env = sdk.Env()
        result = env.sdk_link()

        self.assertEqual(result, '/home/foo/google_appengine')

    @mock.patch('sys.platform', 'linux')
    def test_load_env_reads_preferences_from_home_dir(self):
        # We'll use a new temporary directory as the current user's $HOME.
        temp_dir = tempfile.mkdtemp()
        temp_ini = os.path.join(temp_dir, '.sdkswitcher', sdk.CONFIG_FILENAME)
        os.makedirs(os.path.dirname(temp_ini))

        with open(temp_ini, 'wb') as fh:
            fh.write('[DEFAULT]\nlink = /bar/baz\n')

        try:
            with mock.patch.dict('os.environ', {'HOME': temp_dir}):
                env = sdk.Env.load()
                link = env.sdk_link()

        finally:
            shutil.rmtree(temp_dir)

        # The link path depends on our custom prefs file.
        self.assertEqual(link, '/bar/baz/google_appengine')

    @mock.patch('sys.platform', 'linux')
    def test_save_config(self):
        temp_dir = tempfile.mkdtemp()
        temp_ini = os.path.join(temp_dir, '.sdkswitcher', sdk.CONFIG_FILENAME)
        os.makedirs(os.path.dirname(temp_ini))

        env = sdk.Env()

        try:
            with mock.patch.dict('os.environ', {'HOME': temp_dir}):
                env.save_config()

            with open(temp_ini) as fh:
                ini_contents = fh.read()

        finally:
            shutil.rmtree(temp_dir)

        self.assertEqual(ini_contents, '[DEFAULT]\nlink = ~/\ncache_dir = \n\n')

    def test_active_version_returns_none_if_link_is_missing(self):
        config = configparser.ConfigParser(defaults={'link': '/home/foo'})
        env = sdk.Env(config=config)

        no_such_file = OSError(errno.ENOENT, 'No such file or directory')

        with mock.patch('os.readlink', side_effect=no_such_file):
            result = env.active_version()

        self.assertIsNone(result)

    def test_acive_version_raises_error_for_other_os_readlink_errors(self):
        # Env.active_version() does os.readlink(). For errors other than
        # ENOENT it should raise an exception.

        config = configparser.ConfigParser(defaults={'link': '/home/foo'})
        env = sdk.Env(config=config)

        not_permitted = OSError(errno.EPERM, 'Operation not permitted')

        with mock.patch('os.readlink', side_effect=not_permitted):
            with self.assertRaisesRegexp(OSError, '\[Errno 1\]'):
                env.active_version()


class SummaryCommandTestCase(unittest.TestCase):
    @mock.patch('sys.platform', 'linux')
    @mock.patch.dict('os.environ', {'HOME': '/home/foo'})
    def test_summary_output(self):
        env = sdk.Env()

        with mock.patch('sys.stdout', new=io.BytesIO()) as m:
            env.summary()

        self.assertEqual(
            m.getvalue(),
            (
                'Reading preferences from /home/foo/.sdkswitcher/sdkswitcher.ini\n'
                '0 SDKs in /home/foo/.sdkswitcher\n'
                'SDK symlink is /home/foo/google_appengine\n\n\n'
            ),
        )

    @mock.patch('sys.platform', 'linux')
    @mock.patch.dict('os.environ', {'HOME': '/home/foo'})
    def test_versions_are_sorted_in_summary_output(self):
        env = sdk.Env()

        # Setup the installed SDK versions.
        versions = [
            '9.0.0',
            '100.0.0',
            '1.0.0',
        ]
        path_walk = [('/foo', versions, [])]

        with mock.patch('sys.stdout', new=io.BytesIO()) as m:
            with mock.patch('os.walk', return_value=path_walk):
                with mock.patch('os.path.exists', return_value=True):
                    env.summary()

        self.assertEqual(
            m.getvalue(),
            (
                'Reading preferences from /home/foo/.sdkswitcher/sdkswitcher.ini\n'
                '3 SDKs in /home/foo/.sdkswitcher\n'
                'SDK symlink is /home/foo/google_appengine\n\n'
                '     1.0.0\n'
                '     9.0.0\n'
                '   100.0.0\n\n'
            ),
        )


class CheckCommandTestCase(unittest.TestCase):
    def test_can_parse_api_response(self):
        env = sdk.Env()
        response = io.BytesIO(
            "release: \"1.9.57\"\n"
            "timestamp: 1516312066\n"
            "api_versions: ['1']\n"
            "supported_api_versions:\n"
            "  python:\n"
            "    api_versions: ['1']\n"
            "  python27:\n"
            "    api_versions: ['1']\n"
            "  go:\n"
            "    api_versions: ['go1', 'go1.6', 'go1.8']\n"
            "  java7:\n"
            "    api_versions: ['1.0']\n"
        )

        with mock.patch('urllib2.urlopen', return_value=response):
            result = env.check()

        self.assertEqual(result, '1.9.57')


class ActivateCommandTestCase(unittest.TestCase):
    def test_can_activate_installed_sdk_version(self):
        # This is quite complicated.
        temp_dir = tempfile.mkdtemp()
        env = sdk.Env()

        try:
            with mock.patch.dict('os.environ', {'HOME': temp_dir}):
                with mock.patch('sys.platform', 'linux'):
                    env.activate(version='1.9.57')

            link_filename = os.path.join(temp_dir, 'google_appengine')
            self.assertTrue(os.path.islink(link_filename))

            link_target = os.readlink(link_filename)
            expected = os.path.join(temp_dir, '.sdkswitcher', '1.9.57', 'google_appengine')
            self.assertEqual(link_target, expected)

        finally:
            shutil.rmtree(temp_dir)


class DownloadCommandTestCase(unittest.TestCase):
    def test_downloads_sdk_to_disk(self):
        env = sdk.Env()
        response = io.BytesIO('foo')

        with mock.patch('urllib2.urlopen', return_value=response):
            filename = env.download(version='1.9.57')
            # Clean up this temp file.
            os.unlink(filename)

        basename = os.path.basename(filename)

        self.assertTrue(basename.endswith('google_appengine_1.9.57.zip'), filename)

    def test_downloads_deprecated_sdk_to_disk(self):
        env = sdk.Env()
        response = io.BytesIO('foo')

        # First request gets a 404, which should cause a second request to the
        # deprecated SDKs bucket.
        side_effects = [
            urllib2.HTTPError('https://example.com/', 404, 'no', {}, None),
            response,
        ]

        with mock.patch('urllib2.urlopen', side_effect=side_effects):
            filename = env.download(version='1.8.0')
            # Clean up this temp file.
            os.unlink(filename)

        basename = os.path.basename(filename)

        self.assertTrue(basename.endswith('google_appengine_1.8.0.zip'), filename)


class RemoveCommandTestCase(unittest.TestCase):
    @mock.patch('sys.platform', 'linux')
    @mock.patch.dict('os.environ', {'HOME': '/home/foo'})
    def test_remove_deletes_installed_sdk(self):
        env = sdk.Env()

        with mock.patch('shutil.rmtree') as mock_rmtree:
            env.remove(version='1.9.57')

        self.assertEqual(
            mock_rmtree.call_args_list,
            [mock.call('/home/foo/.sdkswitcher/1.9.57')],
        )


class SafeFilenameTestCase(unittest.TestCase):
    def test_safe_1(self):
        value = 'https://storage.googleapis.com/appengine-sdks/featured/google_appengine_1.9.57.zip'
        result = sdk.safe_filename(value)

        self.assertEqual(result, 'google_appengine_1.9.57.zip')

    def test_safe_2(self):
        value = 'foo/../../..bar..zip..'
        result = sdk.safe_filename(value)

        self.assertEqual(result, 'bar.zip')

    def test_safe_3(self):
        value = '..'

        with self.assertRaises(ValueError):
            sdk.safe_filename(value)


if __name__ == '__main__':
    unittest.main()
