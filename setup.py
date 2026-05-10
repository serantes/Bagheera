import os
import subprocess
import sys
from setuptools import setup
from setuptools.command.install import install
from setuptools.command.develop import develop
from setuptools.command.build_ext import build_ext

def compile_wrapper():
    base_path = os.path.abspath(os.path.dirname(__file__))

    # Ruta de origen solicitada
    source_file = os.path.join(
        base_path, 'src', 'bagheerasearch', 'tools', 'baloo_wrapper', 'baloo_wrapper.cpp'
    )

    # Ruta de destino solicitada (dentro de core/bagheera_search_lib/)
    output_dir = os.path.join(base_path, 'src', 'bagheerasearch', 'core', 'search_lib')
    output_lib = os.path.join(output_dir, 'libbaloo_wrapper.so')

    # Crear el directorio de destino si no existe
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

    cflags = list(set(cflags + extra_includes))
    libs = list(set(libs))

    compile_cmd = [
        'g++', '-shared', '-o', output_lib,
        '-fPIC', '-std=c++17',
        source_file
    ] + cflags + libs

    try:
        print(f"Executing compilation:\n{' '.join(compile_cmd)}")
        subprocess.check_call(compile_cmd)
    except subprocess.CalledProcessError as e:
        print(f"\n✘ Compilation failed.")
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

# Solo dejamos cmdclass, el resto se lee de pyproject.toml
setup(
    cmdclass={
        'install': CustomInstall,
        'develop': CustomDevelop,
        'build_ext': CustomBuildExt,
    }
)
