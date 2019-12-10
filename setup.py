"""Setup for lti_consumer XBlock."""

from __future__ import absolute_import

import os

from setuptools import setup


def package_data(pkg, roots):
    """Generic function to find package_data.

    All of the files under each of the `roots` will be declared as package
    data for package `pkg`.

    """
    data = []
    for root in roots:
        for dirname, __, files in os.walk(os.path.join(pkg, root)):
            for fname in files:
                data.append(os.path.relpath(os.path.join(dirname, fname), pkg))

    return {pkg: data}


setup(
    name='lti_consumer-xblock',
    version='1.2.2',
    description='This XBlock implements the consumer side of the LTI specification.',
    packages=[
        'lti_consumer',
    ],
    install_requires=[
        'lxml',
        'bleach',
        'oauthlib',
        'mako',
        'XBlock',
        'xblock-utils>=v1.0.0',
    ],
    dependency_links=[
        'https://github.com/edx/xblock-utils/tarball/c39bf653e4f27fb3798662ef64cde99f57603f79#egg=xblock-utils',
    ],
    entry_points={
        'xblock.v1': [
            'lti_consumer = lti_consumer:LtiConsumerXBlock',
        ]
    },
    package_data=package_data("lti_consumer", ["static", "templates", "public", "translations"]),
)
