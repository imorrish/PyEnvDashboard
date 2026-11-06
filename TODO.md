## ship uv-dash as an Arch package

2 approaches

| Approach | Best when | Result |
| --- | --- | --- |
| **A. Source / `uv` package** | You maintain the Git repo | Builds from source with `uv` |
| **B. Binary from GitHub Release** | CI already builds Linux | Installs the `flet build linux` tarball |

B is simpler and github action is already doing most of the work

the release has uv-dash-linux.tar.gz
Use createArchPackage.sh
```
makepkg -g >> PKGBUILD
makepkg -si
```
## Publish to the AUR (optional)
Create an AUR account and add an SSH key.
Clone the empty AUR repo (name must match pkgname):

```
git clone ssh://aur@aur.archlinux.org/uv-dash.git
cd uv-dash
# put PKGBUILD (+ .SRCINFO) here
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO
git commit -m "Initial: uv-dash $pkgver"
git push
```
Users then install with
```
yay -S uv-dash
# or: paru -S uv-dash
```