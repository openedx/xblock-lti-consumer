"""Setup for lti_consumer XBlock."""

import os

from setuptools import setup, find_packages


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


def load_requirements(*requirements_paths):
    """
    Load all requirements from the specified requirements files.
    Returns a list of requirement strings.
    """
    requirements = set()
    for path in requirements_paths:
        with open(path) as reqs:
            requirements.update(
                line.split('#')[0].strip() for line in reqs
                if is_requirement(line.strip())
            )
    return list(requirements)


def is_requirement(line):
    """
    Return True if the requirement line is a package requirement;
    that is, it is not blank, a comment, a URL, or an included file.
    """
    return line and not line.startswith(('-r', '#', '-e', 'git+', '-c'))


with open('README.rst') as _f:
    long_description = _f.read()

setup(
    name='lti-consumer-xblock',
    version='2.3.2',
    description='This XBlock implements the consumer side of the LTI specification.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=find_packages(),
    install_requires=load_requirements('requirements/base.in'),
    dependency_links=[
        'https://github.com/edx/xblock-utils/tarball/c39bf653e4f27fb3798662ef64cde99f57603f79#egg=xblock-utils',
    ],
    entry_points={
        'xblock.v1': [
            'lti_consumer = lti_consumer.lti_xblock:LtiConsumerXBlock',
        ],
        'lms.djangoapp': [
            "lti_consumer = lti_consumer.apps:LTIConsumerApp",
        ],
        'cms.djangoapp': [
            "lti_consumer = lti_consumer.apps:LTIConsumerApp",
        ]
    },
    package_data=package_data("lti_consumer", ["static", "templates", "public", "translations"]),
    keywords='lti consumer xblock',
    url='https://github.com/edx/xblock-lti-consumer',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Framework :: Django',
        'Framework :: Django :: 2.2',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Natural Language :: English',
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.8",
    ]
)
