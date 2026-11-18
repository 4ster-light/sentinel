# SPDX-License-Identifier: MIT
#
# COPR spec for the Sentinel process orchestrator CLI.
#
# Builds the wheel from the GitHub release tarball. Runtime and test
# dependencies come from the distribution, so no bundling and no network
# access is needed during the build itself.
#
# The SRPM is created with `make srpm` in this directory (see Makefile).

%global forgeurl https://github.com/4ster-light/sentinel
%global archive_name sentinel-%{version}

Name:           sentinel-pm
Version:        0.2.6
Release:        1%{?dist}
Summary:        Lightweight process orchestrator CLI

License:        MIT
URL:            %{forgeurl}
Source0:        %{forgeurl}/archive/v%{version}/%{archive_name}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel

%description
Sentinel starts and supervises background processes without a service
manager: per-process logs with size-based rotation, CPU and memory metrics,
process groups and clusters, port allocation, health checks, automatic
restart, and SSH-based remote management. State is kept in ~/.sentinel.

%prep
%autosetup -n %{archive_name}

%generate_buildrequires
%pyproject_buildrequires -r
echo 'python3dist(pytest)'

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files sentinel_core sentinel_cli

%check
%pyproject_check_import
# The project's pytest addopts enable coverage reporting and an 85% floor;
# the distribution build only needs the tests themselves.
PYTHONPATH=%{buildroot}%{python3_sitelib} %pytest -o addopts=

%files -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_bindir}/sentinel

%changelog
* Wed Nov 18 2026 4ster-light <me@4ster.dev> - 0.2.6-1
- Update to 0.2.6; the distribution is sentinel-pm and the command stays sentinel.
* Tue Nov 17 2026 4ster-light <me@4ster.dev> - 0.2.5-1
- Initial COPR package.
