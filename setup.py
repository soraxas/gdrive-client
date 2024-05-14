import re
from os import path

from setuptools import setup

# read the contents of README file
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

PKG_NAME = "gdrive_client"

# read the version file
VERSIONFILE = "gdrive_client/_version.py"
verstrline = open(VERSIONFILE, "rt").read()
mo = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", verstrline, re.M)
if not mo:
    raise RuntimeError("Unable to find version string in %s." % (VERSIONFILE,))
version_str = mo.group(1)

setup(
    name="gdrive-client",
    version=version_str,
    description="View plotted stats directly inside terminal.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Tin Lai (@soraxas)",
    author_email="oscar@tinyiu.com",
    license="MIT",
    url="https://github.com/soraxas/gdrive-client",
    keywords="tui termplot stats tensorboard csv",
    python_requires=">=3.6",
    packages=[
        f"{PKG_NAME}",
    ],
    install_requires=[
        "google-api-core==2.8.2",
        "google-api-python-client==2.51.0",
        "google-auth==2.8.0",
        "google-auth-httplib2==0.1.0",
        "google-auth-oauthlib==0.5.2",
        "googleapis-common-protos==1.56.3",
        "loguru",
    ],
    entry_points={
        "console_scripts": [
            f"gdrive-client={PKG_NAME}.main:run",
        ]
    },
    classifiers=[
        "Environment :: Console",
        "Framework :: Matplotlib",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Operating System :: POSIX",
        "Operating System :: Unix",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Desktop Environment",
        "Topic :: Terminals",
        "Topic :: Utilities",
    ],
)
