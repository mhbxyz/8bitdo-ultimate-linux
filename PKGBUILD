pkgname=ultim8do
pkgver=0.1.0
pkgrel=1
pkgdesc="Linux CLI tooling for inspecting 8BitDo Ultimate controllers"
arch=('any')
url="https://github.com/mhbxyz/8bitdo-ultimate-linux"
license=('Apache')
depends=('python' 'python-evdev' 'python-pyudev' 'python-rich' 'python-typer')
makedepends=('python-build' 'python-hatchling' 'python-installer')
source=("${pkgname}-${pkgver}.tar.gz")
sha256sums=('SKIP')

build() {
  cd "${srcdir}/${pkgname}-${pkgver}"
  python -m build --wheel --no-isolation
}

package() {
  cd "${srcdir}/${pkgname}-${pkgver}"
  python -m installer --destdir="${pkgdir}" dist/*.whl

  install -Dm644 udev/99-8bitdo-ultimate.rules \
    "${pkgdir}/usr/lib/udev/rules.d/99-8bitdo-ultimate.rules"
  install -Dm644 systemd/ultim8do.service \
    "${pkgdir}/usr/lib/systemd/user/ultim8do.service"
  install -Dm644 mappings/sdl2/gamecontrollerdb.txt \
    "${pkgdir}/usr/share/ultim8do/mappings/sdl2/gamecontrollerdb.txt"
  install -Dm644 mappings/steam/README.md \
    "${pkgdir}/usr/share/ultim8do/mappings/steam/README.md"
  install -Dm755 scripts/install-udev-rules.sh \
    "${pkgdir}/usr/share/ultim8do/install-udev-rules.sh"
}
