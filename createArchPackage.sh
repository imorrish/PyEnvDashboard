# Maintainer: Ian Morrish <you@example.com>
pkgname=uv-dash-bin
pkgver=0.1.0
pkgrel=1
pkgdesc="Dashboard for discovering and managing uv Python projects (prebuilt)"
arch=('x86_64')
url="https://github.com/imorrish/uv-dash"
license=('MIT')
depends=()  # Flet bundle is mostly self-contained; add gtk3 if runtime needs it
provides=('uv-dash')
conflicts=('uv-dash')
source=("$pkgname-$pkgver.tar.gz::$url/releases/download/v$pkgver/uv-dash-linux.tar.gz")
sha256sums=('SKIP')

package() {
  # adjust paths to match what flet put in the tarball
  install -d "$pkgdir/opt/uv-dash"
  cp -a "$srcdir"/* "$pkgdir/opt/uv-dash/" 2>/dev/null || true
  # if the archive extracts to a single folder:
  # cp -a "$srcdir"/uv-dash-linux/* "$pkgdir/opt/uv-dash/"

  install -d "$pkgdir/usr/bin"
  # binary name from flet is often the product name
  ln -s /opt/uv-dash/uv-dash "$pkgdir/usr/bin/uv-dash" 2>/dev/null \
    || ln -s /opt/uv-dash/uv_dash "$pkgdir/usr/bin/uv-dash"

  install -Dm644 /dev/stdin "$pkgdir/usr/share/applications/uv-dash.desktop" << 'EOF'
[Desktop Entry]
Name=uv-dash
Comment=Discover and manage uv Python projects
Exec=uv-dash
Terminal=false
Type=Application
Categories=Development;Utility;
EOF
}