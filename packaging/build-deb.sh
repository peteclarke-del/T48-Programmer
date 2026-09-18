#!/usr/bin/env bash
#
# Build the Debian package: the application, the minipro release it was tested
# with compiled from source, minipro's chip database, and its udev rules.
#
#   packaging/build-deb.sh [OUTPUT_DIR]
#
# Needs build-essential, pkg-config, libusb-1.0-0-dev, zlib1g-dev, curl and
# python3-pip.

set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${1:-${project_dir}/dist}"
python_command="${PYTHON:-python3}"

package_version="$(cd "${project_dir}/src" && "${python_command}" -c \
    'import t48_programmer; print(t48_programmer.__version__)')"
minipro_version="$(tr -d '[:space:]' < "${project_dir}/packaging/minipro-version.txt")"
minipro_sha256="$(tr -d '[:space:]' < "${project_dir}/packaging/minipro-source.sha256")"
architecture="$(dpkg --print-architecture)"
install_prefix=/usr/lib/t48-programmer

if [[ "${package_version}" == *-* ]]; then
    echo "The project version must not contain a Debian revision separator: ${package_version}" >&2
    exit 1
fi

build_dir="$(mktemp -d)"
trap 'rm -rf -- "${build_dir}"' EXIT
minipro_archive="${build_dir}/minipro-${minipro_version}.tar.gz"
minipro_source="${build_dir}/minipro-${minipro_version}"
package_root="${build_dir}/t48-programmer_${package_version}_${architecture}"
application_lib="${package_root}${install_prefix}"
doc_dir="${package_root}/usr/share/doc/t48-programmer"

curl --fail --location --silent --show-error \
    --output "${minipro_archive}" \
    "https://gitlab.com/DavidGriffith/minipro/-/archive/${minipro_version}/minipro-${minipro_version}.tar.gz"
echo "${minipro_sha256}  ${minipro_archive}" | sha256sum --check --status
tar -xzf "${minipro_archive}" -C "${build_dir}"

# minipro compiles the location of its chip database into the binary from
# PREFIX. It must be built with the prefix it will run from, and DESTDIR must
# stay unset, because the Makefile folds DESTDIR into that compiled-in path.
make -C "${minipro_source}" --jobs="$(nproc)" PREFIX="${install_prefix}" minipro

install -d \
    "${application_lib}/share/minipro" \
    "${package_root}/usr/bin" \
    "${package_root}/usr/share/applications" \
    "${package_root}/usr/share/metainfo" \
    "${package_root}/usr/share/icons/hicolor/scalable/apps" \
    "${package_root}/usr/lib/udev/rules.d" \
    "${doc_dir}" \
    "${package_root}/DEBIAN" \
    "${output_dir}"

"${python_command}" -m pip install \
    --disable-pip-version-check \
    --no-compile \
    --no-deps \
    --target "${application_lib}" \
    "${project_dir}"

# Wheels may preserve a cooperative build umask. Installed application files
# must never remain group writable under /usr.
chmod -R go-w "${application_lib}"
# pip writes the console script here. The package has its own launcher.
rm -rf -- "${application_lib}/bin"
install -d "${application_lib}/bin"

install -m 0755 "${minipro_source}/minipro" "${application_lib}/bin/minipro"
install -m 0644 "${minipro_source}/infoic.xml" "${minipro_source}/logicic.xml" \
    "${application_lib}/share/minipro/"
install -m 0755 "${project_dir}/packaging/t48-programmer" \
    "${package_root}/usr/bin/t48-programmer"
install -m 0644 "${project_dir}/data/com.github.pclarke.T48Programmer.desktop" \
    "${package_root}/usr/share/applications/com.github.pclarke.T48Programmer.desktop"
install -m 0644 \
    "${project_dir}/src/t48_programmer/data/icons/hicolor/scalable/apps/com.github.pclarke.T48Programmer.svg" \
    "${package_root}/usr/share/icons/hicolor/scalable/apps/"
install -m 0644 "${project_dir}/data/com.github.pclarke.T48Programmer.metainfo.xml" \
    "${package_root}/usr/share/metainfo/com.github.pclarke.T48Programmer.metainfo.xml"
# Named for this package. A distribution's minipro package ships its own rules
# as 60-minipro.rules, and dpkg will not let two packages own one file. Having
# both installed is harmless, since they grant the same access.
install -m 0644 "${project_dir}/packaging/60-t48-programmer.rules" \
    "${package_root}/usr/lib/udev/rules.d/60-t48-programmer.rules"
install -m 0644 "${project_dir}/README.md" "${project_dir}/SECURITY.md" "${doc_dir}/"
install -m 0644 "${project_dir}/LICENSE" "${doc_dir}/copyright"
install -m 0644 "${minipro_source}/LICENSE" "${doc_dir}/COPYING.minipro"
install -m 0755 "${project_dir}/packaging/postinst" "${package_root}/DEBIAN/postinst"
install -m 0755 "${project_dir}/packaging/postrm" "${package_root}/DEBIAN/postrm"

installed_size="$(du -sk "${package_root}/usr" | cut -f1)"
cat > "${package_root}/DEBIAN/control" <<CONTROL
Package: t48-programmer
Version: ${package_version}
Section: electronics
Priority: optional
Architecture: ${architecture}
Installed-Size: ${installed_size}
Maintainer: Pete Clarke <peteclarke-del@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, libusb-1.0-0, zlib1g
Homepage: https://github.com/peteclarke-del/T48-Programmer
Description: Native Linux interface for the XGecu T48 chip programmer
 T48 Programmer reads, writes, verifies and erases EPROMs, EEPROMs, flash and
 microcontrollers, and prepares Amiga, Atari ST and Acorn ROM sets. The package
 includes minipro ${minipro_version}, its chip database, and the Linux
 device-access rules.
CONTROL

artifact="${output_dir}/t48-programmer_${package_version}_${architecture}.deb"
dpkg-deb --root-owner-group --build "${package_root}" "${artifact}"
echo "Created ${artifact}"
