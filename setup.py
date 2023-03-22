#!/usr/bin/env python

"""The setup script."""

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [ ]

test_requirements = ['pytest>=3', ]

setup(
    author="Simon Redman",
    author_email='simon@ergotech.com',
    python_requires='>=3.11',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.11',
    ],
    description="MQTT integration to control your SUTA-compatible BLE bed frame using Home Assistant",
    entry_points={
        'console_scripts': [
            'suta_mqtt_bridge=suta_mqtt_bridge.cli:main',
        ],
    },
    install_requires=requirements,
    license="MIT license",
    long_description=readme + '\n\n' + history,
    include_package_data=True,
    keywords='suta_mqtt_bridge',
    name='suta_mqtt_bridge',
    packages=find_packages(include=['suta_mqtt_bridge', 'suta_mqtt_bridge.*']),
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/sredman/suta_mqtt_bridge',
    version='0.1.0',
    zip_safe=False,
)
