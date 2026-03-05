# JQB MinGW Platform — Copilot Instructions

## Project Overview
PlatformIO custom platform that provides auto-installed MinGW-w64 GCC toolchain for native Windows C/C++ applications. No manual compiler setup required — toolchain is downloaded from [winlibs](https://github.com/brechtsanders/winlibs_mingw) on first build.

## Architecture

- `platform.json` — PlatformIO platform manifest (metadata, packages, debug tools).
- `platform.py` — Platform class (`Jqb_mingwPlatform`). Handles toolchain auto-download from GitHub on first build, and configures debug options (GDB).
- `builder/main.py` — SCons build script. Configures GCC/G++ environment, auto-generates VS Code IDE configs (`c_cpp_properties.json`, `launch.json`), handles build/upload/debug targets.

## Key Conventions

- Python 2/3 compatible syntax (PlatformIO may run on either).
- Use `os.path.join` for all file paths; use forward slashes (`/`) in generated JSON configs.
- All tool paths are absolute — no reliance on system PATH.
- Generated IDE configs (`.vscode/`) merge with existing configurations — never overwrite other tools' configs (e.g. CH55x from JQB_CH55XPlatform).
- Toolchain lives in `~/.platformio/packages/toolchain-mingw64/`.

## Build Targets

- `pio run` — Build the project (release: `-O2 -DNDEBUG`).
- `pio run -t upload` — Build and run the `.exe`.
- `pio debug` — Build with debug symbols (`-Og -g3 -ggdb3`) and launch GDB.

## Debug

- GDB comes from the auto-installed MinGW-w64 toolchain (`toolchain-mingw64/bin/gdb.exe`).
- Debug build uses `-Og -g3 -ggdb3` flags.
- Release build uses `-O2 -DNDEBUG`.
- `launch.json` is auto-generated with a `"Debug (MinGW-w64 GDB)"` configuration.
- PlatformIO debug tool is registered as `mingw-gdb` in `platform.json`.
