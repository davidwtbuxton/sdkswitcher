import setuptools


setuptools.setup(
    name='sdkswitcher',
    version='dev',
    py_modules=['sdk'],
    entry_points={
        'console_scripts': ['sdkswitcher = sdk:main'],
    },
)
