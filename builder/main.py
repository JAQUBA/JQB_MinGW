"""
SCons build script for JQB MinGW platform.

Builds native Windows C/C++ applications using auto-installed MinGW-w64 GCC.
Drop-in replacement for PlatformIO's 'platform = native' with managed toolchain.

Features:
  - Explicit GCC/G++ toolchain configuration (no system PATH dependency)
  - Auto-adds src/ subdirectories to include path
  - Upload target = run the built executable
"""

import json as _json
import os
import subprocess
import sys
from os.path import isdir, isfile, join

from SCons.Script import (
    COMMAND_LINE_TARGETS,
    AlwaysBuild,
    Default,
    DefaultEnvironment,
)

env = DefaultEnvironment()
platform = env.PioPlatform()

# ---------------------------------------------------------------------------
# Resolve MinGW-w64 toolchain
# Auto-installed by platform.py on first build into ~/.platformio/packages/
# ---------------------------------------------------------------------------

PACKAGES_DIR = join(os.path.expanduser("~"), ".platformio", "packages")
MINGW_DIR = join(PACKAGES_DIR, "toolchain-mingw64")
MINGW_BIN = join(MINGW_DIR, "bin")

assert isdir(MINGW_DIR), (
    "MinGW-w64 toolchain not found at: %s\n"
    "Auto-install may have failed. Check network connection and retry.\n"
    "See: https://github.com/JAQUBA/JQB_MinGW"
    % MINGW_DIR
)

# Add MinGW to PATH — needed for:
#   - subprocess calls (windres in library scripts, etc.)
#   - Any tool that resolves executables via PATH
env.PrependENVPath("PATH", MINGW_BIN)
os.environ["PATH"] = MINGW_BIN + os.pathsep + os.environ.get("PATH", "")

# ---------------------------------------------------------------------------
# Configure GCC/G++ build environment
#
# All tool paths and build commands are set explicitly so the build does
# NOT depend on any system-wide compiler installation.
# ---------------------------------------------------------------------------

env.Replace(
    # --- Tool paths ---
    CC=join(MINGW_BIN, "gcc"),
    CXX=join(MINGW_BIN, "g++"),
    AS=join(MINGW_BIN, "as"),
    AR=join(MINGW_BIN, "ar"),
    RANLIB=join(MINGW_BIN, "ranlib"),
    OBJCOPY=join(MINGW_BIN, "objcopy"),
    STRIP=join(MINGW_BIN, "strip"),
    LINK=join(MINGW_BIN, "g++"),

    # --- File extensions ---
    PROGSUFFIX=".exe",
    OBJSUFFIX=".o",
    LIBSUFFIX=".a",
    LIBPREFIX="lib",

    # --- Flag prefixes/suffixes for SCons variable expansion ---
    CPPDEFPREFIX="-D",
    CPPDEFSUFFIX="",
    INCPREFIX="-I",
    INCSUFFIX="",
    LIBDIRPREFIX="-L",
    LIBDIRSUFFIX="",
    LIBLINKPREFIX="-l",
    LIBLINKSUFFIX="",

    # --- Archiver flags ---
    ARFLAGS=["rcs"],

    # --- Build command templates ---
    # These reference SCons variables ($CCFLAGS, $_CPPDEFFLAGS, etc.)
    # which contain the actual flag values from platformio.ini build_flags
    # and library scripts. Setting templates does NOT lose user flags.
    _CCCOMCOM="$CPPFLAGS $_CPPDEFFLAGS $_CPPINCFLAGS",
    CCCOM="$CC -o $TARGET -c $CFLAGS $CCFLAGS $_CCCOMCOM $SOURCES",
    CXXCOM="$CXX -o $TARGET -c $CXXFLAGS $CCFLAGS $_CCCOMCOM $SOURCES",
    ARCOM="$AR $ARFLAGS $TARGET $SOURCES",
    RANLIBCOM="$RANLIB $TARGET",
    LINKCOM="$LINK -o $TARGET $LINKFLAGS $SOURCES $_LIBDIRFLAGS $_LIBFLAGS",

    # --- No size tool for native executables ---
    SIZETOOL="",
    SIZEPRINTCMD="",
)

# ---------------------------------------------------------------------------
# Auto-add src/ subdirectories to include path
#
# Scans all subdirectories of src/ for .h files and adds them to CPPPATH.
# This allows cross-directory includes (e.g. #include "protocol.h" from
# src/shared/) without manual -I flags in platformio.ini.
# ---------------------------------------------------------------------------

_src_dir = env.subst("$PROJECT_SRC_DIR")
if isdir(_src_dir):
    for _root, _dirs, _files in os.walk(_src_dir):
        if any(f.endswith(".h") for f in _files):
            env.AppendUnique(CPPPATH=[_root])

# ---------------------------------------------------------------------------
# Auto-generate VS Code IntelliSense configuration
#
# Produces/updates .vscode/c_cpp_properties.json with a "MinGW-w64"
# configuration. Merges with existing configurations (e.g. CH55x from
# JQB_CH55XPlatform) instead of overwriting.
# ---------------------------------------------------------------------------


def _generate_ide_config(env):
    project_dir = env.subst("$PROJECT_DIR")
    vscode_dir = join(project_dir, ".vscode")

    # --- Collect include paths ---
    includes = []
    seen = set()
    for p in env.get("CPPPATH", []):
        path = os.path.abspath(str(p)).replace("\\", "/")
        if path not in seen:
            seen.add(path)
            includes.append(path)

    # Add src/ recursively
    src_dir = join(project_dir, "src").replace("\\", "/")
    includes.append(src_dir + "/**")

    # --- Collect defines ---
    defines = []

    for d in env.get("CPPDEFINES", []):
        if isinstance(d, (list, tuple)) and len(d) == 2:
            defines.append("%s=%s" % (d[0], d[1]))
        elif isinstance(d, (list, tuple)):
            for item in d:
                s = str(item)
                if s:
                    defines.append(s)
        else:
            s = str(d)
            if s:
                defines.append(s)

    for flag in env.Flatten(env.get("CCFLAGS", [])):
        fs = str(flag)
        if fs.startswith("-D"):
            d = fs[2:]
            if d and d not in defines:
                defines.append(d)

    try:
        raw = env.GetProjectOption("build_flags", "")
        parts = raw.split() if isinstance(raw, str) else env.Flatten(raw)
        for flag in parts:
            fs = str(flag).strip()
            if fs.startswith("-D"):
                d = fs[2:]
                if d and d not in defines:
                    defines.append(d)
    except Exception:
        pass

    # --- Build new configuration ---
    compiler_path = join(MINGW_BIN, "g++.exe").replace("\\", "/")

    new_config = {
        "name": "MinGW-w64",
        "includePath": includes,
        "defines": defines,
        "compilerPath": compiler_path,
        "cStandard": "c17",
        "cppStandard": "c++17",
        "intelliSenseMode": "windows-gcc-x64",
    }

    # --- Merge with existing configurations ---
    config_path = join(vscode_dir, "c_cpp_properties.json")

    try:
        with open(config_path, "r") as f:
            config = _json.load(f)
    except (IOError, OSError, ValueError):
        config = {"configurations": [], "version": 4}

    configs = config.get("configurations", [])
    found = False
    for i, c in enumerate(configs):
        if c.get("name") == "MinGW-w64":
            configs[i] = new_config
            found = True
            break
    if not found:
        configs.append(new_config)

    config["configurations"] = configs
    config["version"] = 4

    # Write only when content changed
    config_json = _json.dumps(config, indent=4)

    try:
        with open(config_path, "r") as f:
            if f.read() == config_json:
                return
    except (IOError, OSError):
        pass

    if not isdir(vscode_dir):
        os.makedirs(vscode_dir)
    with open(config_path, "w") as f:
        f.write(config_json)
    print("Generated IntelliSense config: %s" % config_path)


_generate_ide_config(env)

# ---------------------------------------------------------------------------
# Build program
# ---------------------------------------------------------------------------

target_prog = env.BuildProgram()
Default(target_prog)

# ---------------------------------------------------------------------------
# Upload = Run the built executable
#
# 'pio run -t upload' launches the .exe without waiting for it to finish
# (typical for GUI applications).
# ---------------------------------------------------------------------------

if "upload" in COMMAND_LINE_TARGETS:

    def run_program(target, source, env):
        build_dir = env.subst("$BUILD_DIR")
        exe_name = env.subst("$PROGNAME") + ".exe"
        exe_path = join(build_dir, exe_name)

        if not isfile(exe_path):
            # Try resolving from source list
            for s in source:
                p = str(s)
                if p.endswith(".exe") and isfile(p):
                    exe_path = p
                    break

        if not isfile(exe_path):
            print("Error: Executable not found: %s" % exe_path)
            return 1

        print("Running: %s" % exe_path)
        subprocess.Popen([exe_path])
        return 0  # Don't wait — GUI app stays running

    upload_actions = [env.Action(run_program, "Launching $SOURCE")]
    AlwaysBuild(env.Alias("upload", target_prog, upload_actions))
