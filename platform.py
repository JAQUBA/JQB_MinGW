"""
JQB MinGW Platform — PlatformIO platform class.

Auto-downloads MinGW-w64 GCC toolchain for native Windows C/C++ builds.
No manual setup required — toolchain is installed automatically on first build.

On first 'pio run', this platform:
  1. Queries GitHub API for latest winlibs GCC release
  2. Downloads the x86_64 POSIX/SEH/UCRT .zip (~250 MB)
  3. Extracts to ~/.platformio/packages/toolchain-mingw64/
  4. Subsequent builds use the cached toolchain (no re-download)
"""

import json
import os
import re
import shutil
import sys
import zipfile
from os.path import isdir, isfile, join

from platformio.public import PlatformBase

# ---------------------------------------------------------------------------
# MinGW-w64 package configuration
#
# Source: winlibs.com (brechtsanders/winlibs_mingw on GitHub)
# Variant: x86_64, POSIX threads, SEH exceptions, UCRT runtime
#
# The platform auto-detects the latest release via GitHub API.
# Fallback URL is used if the API is unreachable.
# ---------------------------------------------------------------------------

_GITHUB_REPO = "brechtsanders/winlibs_mingw"
_GITHUB_API_URL = "https://api.github.com/repos/%s/releases/latest" % _GITHUB_REPO

# Pattern to match x86_64 POSIX SEH UCRT .zip asset
_ASSET_PATTERN = re.compile(
    r"winlibs-x86_64-posix-seh-gcc-[\d.]+-mingw-w64ucrt-[\d.]+-r\d+\.zip$"
)

_FALLBACK_URL = (
    "https://github.com/brechtsanders/winlibs_mingw/releases/download/"
    "15.2.0posix-13.0.0-ucrt-r6/"
    "winlibs-x86_64-posix-seh-gcc-15.2.0-mingw-w64ucrt-13.0.0-r6.zip"
)
_FALLBACK_VERSION = "15.2.0"

_PACKAGE_NAME = "toolchain-mingw64"
_STRIP_ROOT = "mingw64"


def _get_packages_dir():
    """Return PlatformIO packages directory."""
    pio_home = os.environ.get(
        "PLATFORMIO_HOME_DIR",
        join(os.path.expanduser("~"), ".platformio"),
    )
    return join(pio_home, "packages")


def _fetch_latest_release():
    """Query GitHub API for latest winlibs release.
    Returns (download_url, version_string) or None on failure.
    """
    try:
        from urllib.request import urlopen, Request

        req = Request(_GITHUB_API_URL)
        req.add_header("Accept", "application/vnd.github.v3+json")
        req.add_header("User-Agent", "JQB_MinGW-PlatformIO")

        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        tag = data.get("tag_name", "")
        assets = data.get("assets", [])

        # Find the x86_64 posix seh ucrt .zip
        for asset in assets:
            name = asset.get("name", "")
            if _ASSET_PATTERN.match(name):
                url = asset.get("browser_download_url", "")
                # Extract GCC version from filename
                m = re.search(r"gcc-([\d.]+)", name)
                version = m.group(1) if m else tag
                return url, version

    except Exception as e:
        print("[MinGW] GitHub API unavailable (%s), using fallback URL" % e)

    return None


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
    pkg_dir = join(packages_dir, _PACKAGE_NAME)

    # Already installed — skip
    if isdir(pkg_dir) and isfile(join(pkg_dir, "package.json")):
        return

    if sys.platform != "win32":
        raise RuntimeError(
            "JQB_MinGW platform is designed for Windows only. "
            "Current platform: %s" % sys.platform
        )

    # Try to get latest release from GitHub API
    result = _fetch_latest_release()
    if result:
        download_url, version = result
        print("[MinGW] Latest release: GCC %s" % version)
    else:
        download_url = _FALLBACK_URL
        version = _FALLBACK_VERSION
        print("[MinGW] Using fallback: GCC %s" % version)

    print("[MinGW] Installing toolchain-mingw64 v%s ..." % version)
    print("[MinGW] This is a one-time download (~250 MB). Please wait...")

    tmp_dir = join(packages_dir, "_mingw_tmp")
    try:
        if isdir(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir)

        # Download
        archive_path = join(tmp_dir, "mingw.zip")
        _download(download_url, archive_path)

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

        # Determine source directory (strip root)
        source_dir = join(extract_dir, _STRIP_ROOT)

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
                    "name": _PACKAGE_NAME,
                    "version": version,
                    "description": "MinGW-w64 GCC %s (x86_64, UCRT, POSIX threads, SEH)" % version,
                },
                f,
                indent=2,
            )

        print("[MinGW] toolchain-mingw64 v%s installed successfully" % version)

    except Exception as e:
        print("[MinGW] ERROR: %s" % e)
        raise
    finally:
        if isdir(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
            except OSError:
                pass


class Jqb_mingwPlatform(PlatformBase):

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

    def configure_debug_options(self, initial_debug_options, ide_data):
        import copy

        debug_options = copy.deepcopy(initial_debug_options)

        packages_dir = _get_packages_dir()
        mingw_dir = join(packages_dir, _PACKAGE_NAME)
        gdb_path = join(mingw_dir, "bin", "gdb.exe").replace("\\", "/")

        debug_options["gdb_path"] = gdb_path

        # No debug server for native apps — GDB launches the program directly
        if "server" not in debug_options:
            debug_options["server"] = {}

        if "init_cmds" not in debug_options:
            # Build program path for GDB 'file' command
            prog_path = ide_data.get("prog_path", "").replace("\\", "/")
            debug_options["init_cmds"] = [
                "define pio_reset_halt_target",
                "end",
                "define pio_reset_run_target",
                "end",
                "set confirm off",
                "set breakpoint pending on",
                "set print pretty on",
            ]
            # Load executable symbols so breakpoints resolve before 'run'
            if prog_path:
                debug_options["init_cmds"].append(
                    'file "%s"' % prog_path
                )

        if "init_break" not in debug_options:
            debug_options["init_break"] = "tbreak main"

        if "load_cmds" not in debug_options:
            # No firmware to flash — just start the program;
            # breakpoints (including init_break) are set before this.
            debug_options["load_cmds"] = ["run"]

        return debug_options
