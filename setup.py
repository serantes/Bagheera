import os
import subprocess
import sys
from setuptools import setup
from setuptools.dist import Distribution
from setuptools.command.install import install
from setuptools.command.develop import develop
from setuptools.command.build_ext import build_ext
from setuptools.command.build_py import build_py

try:
    from setuptools.command.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:  # older setuptools
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel


def compile_wrapper():
    base_path = os.path.abspath(os.path.dirname(__file__))

    # Source path requested
    source_file = os.path.join(
        base_path, 'src', 'bagheerasearch', 'tools', 'baloo_wrapper', 'baloo_wrapper.cpp'
    )

    # Destination path requested (inside core/bagheera_search_lib/)
    output_dir = os.path.join(base_path, 'src', 'bagheerasearch', 'core', 'search_lib')
    output_lib = os.path.join(output_dir, 'libbaloo_wrapper.so')

    # Create destination directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(source_file):
        print(f"✘ Error: Source file not found at {source_file}")
        sys.exit(1)

    packages = ['KF6Baloo', 'KF6BalooEngine', 'KF6FileMetadata', 'KF6CoreAddons', 'Qt6Core']
    cflags = []
    libs = []

    for pkg in packages:
        try:
            cf = subprocess.check_output(['pkg-config', '--cflags', pkg], text=True).split()
            lb = subprocess.check_output(['pkg-config', '--libs', pkg], text=True).split()
            cflags.extend(cf)
            libs.extend(lb)
        except subprocess.CalledProcessError:
            print(f"  [!] Warning: pkg-config could not find {pkg}")

    extra_includes = [
        '-I/usr/include/KF6',
        '-I/usr/include/KF6/KFileMetaData',
        '-I/usr/include/qt6',
        '-I/usr/include/qt6/QtCore'
    ]

    # Remove duplicates while preserving order (link order can matter)
    cflags = list(dict.fromkeys(cflags + extra_includes))
    libs = list(dict.fromkeys(libs))

    compile_cmd = [
        'g++', '-shared', '-o', output_lib,
        '-fPIC', '-std=c++17',
        source_file
    ] + cflags + libs

    try:
        print(f"Executing compilation:\n{' '.join(compile_cmd)}")
        subprocess.check_call(compile_cmd)
    except subprocess.CalledProcessError:
        print("\n✘ Compilation failed.")
        sys.exit(1)


class CustomInstall(install):
    def run(self):
        compile_wrapper()
        super().run()


class CustomDevelop(develop):
    def run(self):
        compile_wrapper()
        super().run()


class CustomBuildExt(build_ext):
    def run(self):
        compile_wrapper()
        super().run()


class CustomBuildPy(build_py):
    def run(self):
        compile_wrapper()
        super().run()


class BinaryDistribution(Distribution):
    """Declare that the distribution ships a compiled binary (libbaloo_wrapper.so).

    This makes setuptools treat the package as platform-specific, so *all*
    of it (modules and metadata) goes into platlib (lib64 on openSUSE)
    instead of being split between lib and lib64.
    """

    def has_ext_modules(self):
        return True


class CustomBdistWheel(_bdist_wheel):
    """Tag the wheel as py3-none-<platform>.

    The .so is not a CPython extension, so it does not depend on the
    Python version, only on the platform.
    """

    def get_tag(self):
        _, _, plat = super().get_tag()
        return 'py3', 'none', plat


# Only cmdclass remains, the rest is read from pyproject.toml
setup(
    distclass=BinaryDistribution,
    cmdclass={
        'install': CustomInstall,
        'develop': CustomDevelop,
        'build_ext': CustomBuildExt,
        'build_py': CustomBuildPy,
        'bdist_wheel': CustomBdistWheel,
    },
    data_files=[
        ('share/applications', [
            'src/bagheeragui/assets/bagheeragui.desktop',
            'src/bagheeraview/assets/bagheeraview.desktop'
        ]),
        ('share/icons/hicolor/1024x1024/apps', [
            'src/bagheeragui/assets/bagheeragui.png',
            'src/bagheeraview/assets/bagheeraview.png'
        ]),
    ],
)
