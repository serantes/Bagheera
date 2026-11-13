#
# spec file for package Bagheera Suite
#
# Copyright (c) 2026 Ignacio Serantes
# License: GPL-3.0-or-later
#

# Build only for the default Python flavor (avoid duplicate installs per Python version)
%define pythons python3
# The only compiled artifact is a helper .so; no usable debuginfo is generated
%global debug_package %{nil}

Name:           bagheera
Version:        1.0.0
Release:        1
Summary:        Bagheera: Search Tool and Image Viewer for KDE/Baloo
License:        GPL-3.0-or-later
URL:            https://github.com/serantes/Bagheera
Source0:        %{name}-%{version}.tar.gz

# --- C++ / KF6 / Qt6 BUILD DEPENDENCIES (from setup.py) ---
BuildRequires:  gcc-c++
BuildRequires:  pkgconfig
BuildRequires:  kf6-baloo-devel
BuildRequires:  kf6-kfilemetadata-devel
BuildRequires:  kf6-kcoreaddons-devel
BuildRequires:  qt6-base-devel
# BuildRequires:  pkgconfig(Qt6Core)
# BuildRequires:  pkgconfig(KF6Baloo)
# BuildRequires:  pkgconfig(KF6FileMetadata)
# BuildRequires:  pkgconfig(KF6CoreAddons)

# --- PYTHON BUILD DEPENDENCIES (from pyproject.toml) ---
BuildRequires:  python-rpm-macros
BuildRequires:  python313-base
BuildRequires:  python313-pip
BuildRequires:  python313-wheel
BuildRequires:  python313-setuptools

# --- BASE RUNTIME DEPENDENCIES (from pyproject.toml) ---
Requires:       python313-exiv2
Requires:       python313-faiss
Requires:       python313-geopy
Requires:       python313-lmdb
Requires:       python313-numpy
Requires:       python313-pillow
Requires:       python313-psutil
Requires:       python313-pyparsing
Requires:       python313-pyside6
Requires:       python313-watchdog

# -- NOT AVAILABLE PACKAGES ---
#Requires:       python313-face-recognition
#Requires:       python313-faiss-gpu
#Requires:       python313-imagehash
#Requires:       python313-mediapipe

# System and desktop integration utilities
BuildRequires:  fdupes
BuildRequires:  update-desktop-files

%description
Bagheera Suite is an advanced collection of tools including a search tool
and an image viewer optimized for KDE and Baloo.

%prep
%autosetup -p1
# Stale local build artifact (duplicate libbaloo_wrapper.so); enable if the app does not load it
# rm -rf src/bagheerasearch/tools/baloo_wrapper/build

%build
# Build Python wheel (triggers CustomBuildPy/CustomBuildExt in setup.py, compiling libbaloo_wrapper.so via g++)
%pyproject_wheel

%install
%pyproject_install

# Remove duplicated files using hardlinks
%fdupes %{buildroot}%{python3_sitearch}

# Register and integrate .desktop launchers in KDE/GNOME
%suse_update_desktop_file -r bagheeraview Qt KDE Graphics Photography Viewer
%suse_update_desktop_file -r bagheeragui Utility System

%files
%doc README.MD
%license LICENSE
%{_bindir}/bagheerasearch
%{_bindir}/bagheeragui
%{_bindir}/bagheeraview
%{python3_sitearch}/bagheerasearch*
%{python3_sitearch}/bagheeraview*
%{python3_sitearch}/bagheeragui*
%{python3_sitearch}/bagheera_suite-%{version}*-info/
%{_datadir}/applications/bagheeraview.desktop
%{_datadir}/applications/bagheeraview_x11.desktop
%{_datadir}/applications/bagheeragui.desktop
%{_datadir}/icons/hicolor/*/apps/bagheeraview.*
%{_datadir}/icons/hicolor/*/apps/bagheeraview_x11.*
%{_datadir}/icons/hicolor/*/apps/bagheeragui.*

%changelog
* Wed Nov 1 2026 Ignacio Serantes <kde@aynoa.es> - 1.0.0
- Initial release.
