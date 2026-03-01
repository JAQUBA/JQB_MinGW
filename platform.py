"""
JQB MinGW Platform — PlatformIO platform class.

Auto-downloads MinGW-w64 GCC toolchain for native Windows C/C++ builds.
No manual setup required — toolchain is installed automatically on first build.

Packages are downloaded to ~/.platformio/packages/toolchain-mingw64/
"""

import json
import os
import shutil
import sys
import zipfile
from os.path import isdir, isfile, join

from platformio.public import PlatformBase

# ---------------------------------------------------------------------------
# MinGW-w64 package configuration
#
# Source: winlibs.com (brechtsanders/winlibs_mingw on GitHub)
# Variant: GCC 14.2.0, x86_64, POSIX threads, SEH exceptions, UCRT runtime
# ---------------------------------------------------------------------------

_MINGW_PACKAGE = {
    "name": "toolchain-mingw64",
    "version": "14.2.0",
    "description": "MinGW-w64 GCC 14.2.0 (x86_64, UCRT, POSIX threads, SEH)",
    "strip_root": "mingw64",
    "url": (
        "https://github.com/brechtsanders/winlibs_mingw/releases/download/"
        "14.2.0posix-19.1.7-12.0.0-ucrt-r3/"
        "winlibs-x86_64-posix-seh-gcc-14.2.0-mingw-w64ucrt-12.0.0-r3.zip"
    ),
}


def _get_packages_dir():
    """Return PlatformIO packages directory."""
    pio_home = os.environ.get(
        "PLATFORMIO_HOME_DIR",
        join(os.path.expanduser("~"), ".platformio"),
    )
    return join(pio_home, "packages")


def _download(url, dest_path):
    """Download a file from URL with progress indication."""
    from urllib.request import urlretrieve

    def _progress(count, block_size, total_size):
        if total_size > 0:
            pct = min(100, count * block_size * 100 // total_size)
            mb_done = (count * block_size) / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            sys.stdout.write(
                "\r  Downloading: %d%% (%.0f / %.0f MB)" % (pct, mb_done, mb_total)
            )
            sys.stdout.flush()

    urlretrieve(url, dest_path, _progress)
    sys.stdout.write("\r  Downloading: done                              \n")
    sys.stdout.flush()


def _install_mingw(packages_dir):
    """Download, extract and install MinGW-w64 toolchain."""
    pkg = _MINGW_PACKAGE
    pkg_dir = join(packages_dir, pkg["name"])

    # Already installed — skip
    if isdir(pkg_dir) and isfile(join(pkg_dir, "package.json")):
        return

    if sys.platform != "win32":
        raise RuntimeError(
            "JQB_MinGW platform is designed for Windows only. "
            "Current platform: %s" % sys.platform
        )

    print("[MinGW] Installing %s v%s ..." % (pkg["name"], pkg["version"]))
    print("[MinGW] This is a one-time download (~450 MB). Please wait...")

    tmp_dir = join(packages_dir, "_mingw_tmp")
    try:
        if isdir(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir)

        # Download
        archive_path = join(tmp_dir, "mingw.zip")
        _download(pkg["url"], archive_path)

        # Extract
        print("  Extracting (this may take a minute)...")
        extract_dir = join(tmp_dir, "extract")
        os.makedirs(extract_dir)
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(extract_dir)

        # Remove archive immediately to free disk space
        try:
            os.remove(archive_path)
        except OSError:
            pass

        # Determine source directory (with optional root stripping)
        if pkg["strip_root"]:
            source_dir = join(extract_dir, pkg["strip_root"])
        else:
            source_dir = extract_dir

        if not isdir(source_dir):
            raise RuntimeError(
                "Expected directory '%s' not found after extraction" % source_dir
            )

        # Verify gcc.exe exists
        gcc_path = join(source_dir, "bin", "gcc.exe")
        if not isfile(gcc_path):
            raise RuntimeError(
                "gcc.exe not found at '%s' — archive structure may have changed"
                % gcc_path
            )

        # Move to final location
        if isdir(pkg_dir):
            shutil.rmtree(pkg_dir)
        shutil.move(source_dir, pkg_dir)

        # Create package.json for PlatformIO
        with open(join(pkg_dir, "package.json"), "w") as f:
            json.dump(
                {
                    "name": pkg["name"],
                    "version": pkg["version"],
                    "description": pkg["description"],
                },
                f,
                indent=2,
            )

        print("[MinGW] %s installed successfully" % pkg["name"])

    except Exception as e:
        print("[MinGW] ERROR installing %s: %s" % (pkg["name"], e))
        raise
    finally:
        if isdir(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
            except OSError:
                pass


class JqbMingwPlatform(PlatformBase):

    def configure_default_packages(self, variables, targets):
        # Auto-install MinGW-w64 if not present
        packages_dir = _get_packages_dir()
        if not isdir(packages_dir):
            os.makedirs(packages_dir)

        _install_mingw(packages_dir)

        # Declare package for PlatformIO
        if "toolchain-mingw64" not in self.packages:
            self.packages["toolchain-mingw64"] = {
                "type": "toolchain",
                "optional": True,
            }

        return super().configure_default_packages(variables, targets)
