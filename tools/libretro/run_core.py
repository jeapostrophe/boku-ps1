#!/usr/bin/env python3
"""Boot a disc image on a libretro core with no window, no frontend and no human.

The patch must behave on Beetle PSX (`mednafen_psx`), because that is the core Mode One in
`~/Dev/retro-trainer` runs (CLAUDE.md § "Working with the disc"). This is the smallest thing
that can boot an arbitrary `.cue` on that core, press buttons on a schedule, and write out
what the core drew -- ctypes against `libretro.h`, standard library only.

    tools/libretro/run_core.py disc/image.cue --frames 2400 --shot 2300:title

`--core` names the core dylib and `--system` the directory holding `scph5500.bin`; without
them, `emulator_paths.py` finds each (`BOKU_LIBRETRO_CORE` / `BOKU_LIBRETRO_SYSTEM`, else the
retro-trainer checkout's `config/`) or says what to install. `research/tooling-setup.md`
§ "Beetle PSX, headless" says where retro-trainer keeps its build.

Frame numbering: frame N is the state after the N-th `retro_run` call, so the first frame is
1. Beetle counts a frame per `retro_run`; PCSX-Redux counts GPU vsyncs, so the two disagree on
the same boot (`research/tooling-setup.md`).

Memory card 1 is the core's SAVE_RAM: `--memcard CARD` copies a raw 128 KB card in before the
first frame and `--memcard-out` writes it back out after the last; the card file itself is
never written. `--ram-out` dumps main RAM, `--peek` samples a few words of it into `peek.tsv`
frame by frame, and `--poke` writes it (`research/save-format.md`).

Exit codes: 0 ran to the end, 2 usage (including a --memcard the core's card does not fit),
3 core did not load, 4 the core could not read the disc, 5 a save state, RAM dump or card
write-out failed, 6 an --assert-drawn frame was blank, 7 the system directory held
no BIOS so the core fell back to its own HLE one (`--allow-hle-bios` runs anyway; that boot is
not the machine Mode One runs), 8 a frame that was asked for was never reached.
"""

from __future__ import annotations

import argparse
import ctypes
import struct
import sys
import time
import zlib
from ctypes import (
    CFUNCTYPE,
    POINTER,
    c_bool,
    c_char_p,
    c_double,
    c_float,
    c_int,
    c_int16,
    c_size_t,
    c_uint,
    c_void_p,
)
from pathlib import Path

import emulator_paths  # beside this file, so on sys.path when run as a script

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CORE = 3
EXIT_GAME = 4
EXIT_STATE = 5
EXIT_ASSERT = 6
EXIT_FIRMWARE = 7
EXIT_INCOMPLETE = 8

# libretro.h's retro_get_memory_data ids. Beetle hands memory card 1 to the frontend as
# SAVE_RAM (its `use_mednafen_memcard0_method` option, default "libretro"); SYSTEM_RAM is the
# 2 MB of main RAM, so RAM address 0x80000000 + n is byte n.
MEMORY_SAVE_RAM = 0
MEMORY_SYSTEM_RAM = 2

# --- the parts of libretro.h this frontend implements -------------------------------------
# Values are from ~/Dev/retro-trainer/dist/libretro.h. Only the calls answered below are
# load-bearing; ENV_NAMES is diagnostics, and a wrong name there changes no behaviour.

ENV_EXPERIMENTAL = 0x10000

ENV_GET_CAN_DUPE = 3
ENV_SHUTDOWN = 7
ENV_SET_PERFORMANCE_LEVEL = 8
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_SET_INPUT_DESCRIPTORS = 11
ENV_SET_HW_RENDER = 14
ENV_GET_VARIABLE = 15
ENV_SET_VARIABLES = 16
ENV_GET_VARIABLE_UPDATE = 17
ENV_GET_LOG_INTERFACE = 27
ENV_GET_CONTENT_DIRECTORY = 30
ENV_GET_SAVE_DIRECTORY = 31
ENV_SET_SYSTEM_AV_INFO = 32
ENV_SET_CONTROLLER_INFO = 35
ENV_SET_MEMORY_MAPS = 36 | ENV_EXPERIMENTAL
ENV_SET_GEOMETRY = 37
ENV_SET_SUPPORT_ACHIEVEMENTS = 42 | ENV_EXPERIMENTAL
ENV_GET_CORE_OPTIONS_VERSION = 52
ENV_SET_SERIALIZATION_QUIRKS = 87

ENV_NAMES = {
    1: "SET_ROTATION",
    2: "GET_OVERSCAN",
    3: "GET_CAN_DUPE",
    6: "SET_MESSAGE",
    7: "SHUTDOWN",
    8: "SET_PERFORMANCE_LEVEL",
    9: "GET_SYSTEM_DIRECTORY",
    10: "SET_PIXEL_FORMAT",
    11: "SET_INPUT_DESCRIPTORS",
    12: "SET_KEYBOARD_CALLBACK",
    13: "SET_DISK_CONTROL_INTERFACE",
    14: "SET_HW_RENDER",
    15: "GET_VARIABLE",
    16: "SET_VARIABLES",
    17: "GET_VARIABLE_UPDATE",
    18: "SET_SUPPORT_NO_GAME",
    19: "GET_LIBRETRO_PATH",
    23: "GET_RUMBLE_INTERFACE",
    24: "GET_INPUT_DEVICE_CAPABILITIES",
    27: "GET_LOG_INTERFACE",
    28: "GET_PERF_INTERFACE",
    30: "GET_CONTENT_DIRECTORY",
    31: "GET_SAVE_DIRECTORY",
    32: "SET_SYSTEM_AV_INFO",
    33: "SET_PROC_ADDRESS_CALLBACK",
    34: "SET_SUBSYSTEM_INFO",
    35: "SET_CONTROLLER_INFO",
    36 | ENV_EXPERIMENTAL: "SET_MEMORY_MAPS",
    37: "SET_GEOMETRY",
    38: "GET_USERNAME",
    39: "GET_LANGUAGE",
    40 | ENV_EXPERIMENTAL: "GET_CURRENT_SOFTWARE_FRAMEBUFFER",
    41 | ENV_EXPERIMENTAL: "GET_HW_RENDER_INTERFACE",
    42 | ENV_EXPERIMENTAL: "SET_SUPPORT_ACHIEVEMENTS",
    44 | ENV_EXPERIMENTAL: "SET_HW_SHARED_CONTEXT",
    45 | ENV_EXPERIMENTAL: "GET_VFS_INTERFACE",
    46 | ENV_EXPERIMENTAL: "GET_LED_INTERFACE",
    47 | ENV_EXPERIMENTAL: "GET_AUDIO_VIDEO_ENABLE",
    48 | ENV_EXPERIMENTAL: "GET_MIDI_INTERFACE",
    49 | ENV_EXPERIMENTAL: "GET_FASTFORWARDING",
    50 | ENV_EXPERIMENTAL: "GET_TARGET_REFRESH_RATE",
    51 | ENV_EXPERIMENTAL: "GET_INPUT_BITMASKS",
    52: "GET_CORE_OPTIONS_VERSION",
    53: "SET_CORE_OPTIONS",
    54: "SET_CORE_OPTIONS_INTL",
    55: "SET_CORE_OPTIONS_DISPLAY",
    56: "GET_PREFERRED_HW_RENDER",
    57: "GET_DISK_CONTROL_INTERFACE_VERSION",
    58: "SET_DISK_CONTROL_EXT_INTERFACE",
    59: "GET_MESSAGE_INTERFACE_VERSION",
    60: "SET_MESSAGE_EXT",
    61: "GET_INPUT_MAX_USERS",
    62: "SET_AUDIO_BUFFER_STATUS_CALLBACK",
    63: "SET_MINIMUM_AUDIO_LATENCY",
    64: "SET_FASTFORWARDING_OVERRIDE",
    65: "SET_CONTENT_INFO_OVERRIDE",
    66: "GET_GAME_INFO_EXT",
    67: "SET_CORE_OPTIONS_V2",
    68: "SET_CORE_OPTIONS_V2_INTL",
    69: "SET_CORE_OPTIONS_UPDATE_DISPLAY_CALLBACK",
    70: "SET_VARIABLE",
    74: "GET_JIT_CAPABLE",
    87: "SET_SERIALIZATION_QUIRKS",
}

# Environment calls that only inform the frontend of something it does not use -- including
# the two geometry ones, because the size that matters arrives with every video_refresh.
# Accepting them keeps them out of the "core asked for something unimplemented" tally.
ENV_ACCEPT_AND_IGNORE = frozenset(
    {
        ENV_SET_PERFORMANCE_LEVEL,
        ENV_SET_INPUT_DESCRIPTORS,
        ENV_SET_CONTROLLER_INFO,
        ENV_SET_MEMORY_MAPS,
        ENV_SET_SUPPORT_ACHIEVEMENTS,
        ENV_SET_SERIALIZATION_QUIRKS,
        ENV_SET_SYSTEM_AV_INFO,
        ENV_SET_GEOMETRY,
    }
)

# Calls refused deliberately, which is not the same as unimplemented.
# GET_CORE_OPTIONS_VERSION is the one that does work: claiming version 0 makes the core lower
# its v2 option definitions to SET_VARIABLES, whose strings carry each option's own default --
# that is where option_defaults comes from, rather than from a list retyped into this file.
# SET_HW_RENDER is refused because there is no window and no GL context; the software-only
# build on this machine never asks (measured: it is absent from a full boot's tally), so this
# only bites on a mednafen_psx_hw build.
ENV_REFUSE = frozenset({ENV_SET_HW_RENDER, ENV_GET_CORE_OPTIONS_VERSION, ENV_GET_CONTENT_DIRECTORY})

PIXEL_0RGB1555 = 0
PIXEL_XRGB8888 = 1
PIXEL_RGB565 = 2
# name, bytes per pixel, and the struct code that reads one pixel as one word.
PIXEL_FORMATS = {
    PIXEL_0RGB1555: ("0RGB1555", 2, "H"),
    PIXEL_XRGB8888: ("XRGB8888", 4, "I"),
    PIXEL_RGB565: ("RGB565", 2, "H"),
}

# 5 bits to 8, repeating the top bits into the bottom so 31 maps to 255 rather than 248.
LUT5 = [(v << 3) | (v >> 2) for v in range(32)]
LUT6 = [(v << 2) | (v >> 4) for v in range(64)]

DEVICE_JOYPAD = 1

# RETRO_HW_FRAME_BUFFER_VALID, the (void*)-1 a hardware-rendered frame arrives as.
HW_FRAME_BUFFER_VALID = (1 << 64) - 1

# PlayStation button names to RETRO_DEVICE_ID_JOYPAD_*. libretro's ids are SNES-shaped, so
# its letters mean the opposite of a PlayStation pad's -- RETRO_DEVICE_ID_JOYPAD_X is the top
# face button, triangle, while PlayStation's X is the bottom one. Only the PlayStation names
# are accepted here: a schedule that said "X" would otherwise press triangle and pass.
BUTTONS = {
    "CROSS": 0,
    "SQUARE": 1,
    "SELECT": 2,
    "START": 3,
    "UP": 4,
    "DOWN": 5,
    "LEFT": 6,
    "RIGHT": 7,
    "CIRCLE": 8,
    "TRIANGLE": 9,
    "L1": 10,
    "R1": 11,
    "L2": 12,
    "R2": 13,
    "L3": 14,
    "R3": 15,
}

DEFAULT_HOLD = 5  # frames; what tools/redux/boot-to-dialogue.lua holds a button for

# Measured on disc/image.cue, 2026-09-20: a blank screen holds 1 distinct pixel value, the
# title screen 433, the arrival scene with its dialogue box 1518. The PS1 draws 15-bit colour
# and these screens are flat, so the gap to aim at is one-versus-hundreds, not thousands.
DEFAULT_ASSERT_COLOURS = 100


class RetroVariable(ctypes.Structure):
    _fields_ = [("key", c_char_p), ("value", c_char_p)]


class RetroSystemInfo(ctypes.Structure):
    _fields_ = [
        ("library_name", c_char_p),
        ("library_version", c_char_p),
        ("valid_extensions", c_char_p),
        ("need_fullpath", c_bool),
        ("block_extract", c_bool),
    ]


class RetroGameGeometry(ctypes.Structure):
    _fields_ = [
        ("base_width", c_uint),
        ("base_height", c_uint),
        ("max_width", c_uint),
        ("max_height", c_uint),
        ("aspect_ratio", c_float),
    ]


class RetroSystemTiming(ctypes.Structure):
    _fields_ = [("fps", c_double), ("sample_rate", c_double)]


class RetroSystemAvInfo(ctypes.Structure):
    _fields_ = [("geometry", RetroGameGeometry), ("timing", RetroSystemTiming)]


class RetroGameInfo(ctypes.Structure):
    _fields_ = [("path", c_char_p), ("data", c_void_p), ("size", c_size_t), ("meta", c_char_p)]


ENVIRONMENT_T = CFUNCTYPE(c_bool, c_uint, c_void_p)
VIDEO_REFRESH_T = CFUNCTYPE(None, c_void_p, c_uint, c_uint, c_size_t)
AUDIO_SAMPLE_T = CFUNCTYPE(None, c_int16, c_int16)
AUDIO_SAMPLE_BATCH_T = CFUNCTYPE(c_size_t, POINTER(c_int16), c_size_t)
INPUT_POLL_T = CFUNCTYPE(None)
INPUT_STATE_T = CFUNCTYPE(c_int16, c_uint, c_uint, c_uint, c_uint)
# The real prototype is variadic: void (*)(enum retro_log_level, const char *fmt, ...). The
# two NAMED arguments are in x0/x1 on arm64 whatever the variadic tail does, so declaring only
# those two is safe; the format string is printed unexpanded, %s and all.
LOG_PRINTF_T = CFUNCTYPE(None, c_int, c_char_p)


class RetroLogCallback(ctypes.Structure):
    _fields_ = [("log", LOG_PRINTF_T)]


LOG_LEVELS = ["DEBUG", "INFO", "WARN", "ERROR"]


def png(width: int, height: int, rows: list[bytes]) -> bytes:
    """8-bit RGB PNG, zlib only. tools/redux/shot2png.py holds the same eight lines for the
    Redux dumps and should: it is run directly by path, so it cannot depend on this file, and
    the PNG header has not changed since 1996 -- there is nothing here for the copies to
    disagree about."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\0" + row for row in rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def to_rgb_rows(pixels: bytes, fmt: int, width: int, height: int, pitch: int) -> list[bytes]:
    """One `bytes` of RGB triples per row, from the core's framebuffer in its chosen format."""
    rows = []
    if fmt == PIXEL_XRGB8888:
        for y in range(height):
            src = pixels[y * pitch : y * pitch + width * 4]
            row = bytearray(width * 3)
            row[0::3] = src[2::4]  # native-endian XRGB -> B,G,R,X in memory
            row[1::3] = src[1::4]
            row[2::3] = src[0::4]
            rows.append(bytes(row))
        return rows

    # (lut, shift, mask) for red, green, blue. 0RGB1555 is what a core gets if it never calls
    # SET_PIXEL_FORMAT; note this is libretro's word, red in the high bits -- the PS1's own
    # VRAM word is the other way round, which is what tools/redux/shot2png.py decodes.
    if fmt == PIXEL_RGB565:
        channels = ((LUT5, 11, 0x1F), (LUT6, 5, 0x3F), (LUT5, 0, 0x1F))
    else:
        channels = ((LUT5, 10, 0x1F), (LUT5, 5, 0x1F), (LUT5, 0, 0x1F))

    for y in range(height):
        words = struct.unpack_from(f"<{width}H", pixels, y * pitch)
        row = bytearray(width * 3)
        for c, (lut, shift, mask) in enumerate(channels):
            row[c::3] = bytes(lut[(word >> shift) & mask] for word in words)
        rows.append(bytes(row))
    return rows


class Frontend:
    """One loaded core. Every ctypes callback object is an attribute so that nothing the core
    holds a pointer to is collected while it runs -- the classic way to crash a ctypes
    frontend is to pass `CFUNCTYPE(...)(f)` as a temporary."""

    def __init__(
        self, core_path: Path, system_dir: Path, save_dir: Path, options: dict, log_level: int
    ):
        self.system_dir = str(system_dir).encode()
        self.save_dir = str(save_dir).encode()
        self.forced_options = options
        self.log_level = log_level

        self.option_defaults: dict[bytes, bytes] = {}
        self.env_counts: dict[int, int] = {}
        self.env_refused: dict[int, int] = {}
        self.env_unhandled: dict[int, int] = {}
        self.pixel_format = PIXEL_0RGB1555
        self.shutdown_requested = False
        self.firmware_missing = False
        self.buttons: frozenset[int] = frozenset()
        self.frame: bytes | None = None
        self.frame_size = (0, 0, 0)  # width, height, pitch
        self.frames_drawn = 0
        self.frames_duped = 0
        self.polls = 0

        # Buffers the core is handed pointers into; they must outlive every call.
        self._keepalive: dict[str, object] = {
            "system": ctypes.create_string_buffer(self.system_dir),
            "save": ctypes.create_string_buffer(self.save_dir),
        }
        self._var_bufs: dict[bytes, ctypes.Array] = {}

        try:
            self.lib = ctypes.CDLL(str(core_path))
        except OSError as exc:
            raise CoreError(f"cannot load core {core_path}: {exc}") from exc
        self._bind()

        self.cb_environment = ENVIRONMENT_T(self._environment)
        self.cb_video = VIDEO_REFRESH_T(self._video_refresh)
        self.cb_audio = AUDIO_SAMPLE_T(self._audio_sample)
        self.cb_audio_batch = AUDIO_SAMPLE_BATCH_T(self._audio_batch)
        self.cb_input_poll = INPUT_POLL_T(self._input_poll)
        self.cb_input_state = INPUT_STATE_T(self._input_state)
        self.cb_log = LOG_PRINTF_T(self._log)

        # retro_set_environment comes first and the core may call back into it immediately,
        # before retro_init -- by then everything it can ask about must already be set up.
        self.lib.retro_set_environment(self.cb_environment)
        self.lib.retro_set_video_refresh(self.cb_video)
        self.lib.retro_set_audio_sample(self.cb_audio)
        self.lib.retro_set_audio_sample_batch(self.cb_audio_batch)
        self.lib.retro_set_input_poll(self.cb_input_poll)
        self.lib.retro_set_input_state(self.cb_input_state)

    def _bind(self) -> None:
        lib = self.lib
        try:
            lib.retro_api_version.restype = c_uint
            lib.retro_get_system_info.argtypes = [POINTER(RetroSystemInfo)]
            lib.retro_get_system_av_info.argtypes = [POINTER(RetroSystemAvInfo)]
            lib.retro_set_environment.argtypes = [ENVIRONMENT_T]
            lib.retro_set_video_refresh.argtypes = [VIDEO_REFRESH_T]
            lib.retro_set_audio_sample.argtypes = [AUDIO_SAMPLE_T]
            lib.retro_set_audio_sample_batch.argtypes = [AUDIO_SAMPLE_BATCH_T]
            lib.retro_set_input_poll.argtypes = [INPUT_POLL_T]
            lib.retro_set_input_state.argtypes = [INPUT_STATE_T]
            lib.retro_set_controller_port_device.argtypes = [c_uint, c_uint]
            lib.retro_load_game.argtypes = [POINTER(RetroGameInfo)]
            lib.retro_load_game.restype = c_bool
            lib.retro_serialize_size.restype = c_size_t
            lib.retro_serialize.argtypes = [c_void_p, c_size_t]
            lib.retro_serialize.restype = c_bool
            lib.retro_unserialize.argtypes = [c_void_p, c_size_t]
            lib.retro_unserialize.restype = c_bool
            lib.retro_get_memory_data.argtypes = [c_uint]
            lib.retro_get_memory_data.restype = c_void_p
            lib.retro_get_memory_size.argtypes = [c_uint]
            lib.retro_get_memory_size.restype = c_size_t
        except AttributeError as exc:
            raise CoreError(f"core is missing a libretro entry point: {exc}") from exc

    # --- callbacks ------------------------------------------------------------------------

    def _log(self, level: int, fmt: bytes | None) -> None:
        if fmt is None:
            return
        # The core's own verdict is the only thing that also catches a BIOS present under the
        # wrong name or region; research/tooling-setup.md § "Beetle PSX, headless" says why
        # booting without one has to be an error rather than a warning.
        if fmt.startswith(b"Firmware is missing"):
            self.firmware_missing = True
        if level < self.log_level:
            return
        name = LOG_LEVELS[level] if 0 <= level < len(LOG_LEVELS) else str(level)
        print(f"[core {name}] {fmt.decode('utf-8', 'replace').rstrip()}", file=sys.stderr)

    def _environment(self, cmd: int, data: int | None) -> bool:
        self.env_counts[cmd] = self.env_counts.get(cmd, 0) + 1

        if cmd == ENV_GET_SYSTEM_DIRECTORY:
            return self._write_string_ptr(data, "system")
        if cmd == ENV_GET_SAVE_DIRECTORY:
            return self._write_string_ptr(data, "save")
        if cmd == ENV_GET_CAN_DUPE:
            # False on purpose. A core allowed to dupe sends NULL instead of redrawing, and
            # the frame kept for `--shot N` would then be an older frame wearing N's name --
            # a screenshot that lies about which frame it is. The NULL path below still works
            # if a core dupes anyway.
            return self._poke(data, c_bool, False)
        if cmd == ENV_SET_PIXEL_FORMAT:
            if not data:
                return False
            fmt = ctypes.cast(data, POINTER(c_int))[0]
            if fmt not in PIXEL_FORMATS:
                return False
            self.pixel_format = fmt
            return True
        if cmd == ENV_GET_LOG_INTERFACE:
            if not data:
                return False
            ctypes.cast(data, POINTER(RetroLogCallback))[0].log = self.cb_log
            return True
        if cmd == ENV_GET_VARIABLE_UPDATE:
            return self._poke(data, c_bool, False)
        if cmd == ENV_SET_VARIABLES:
            self._read_variable_defaults(data)
            return True
        if cmd == ENV_GET_VARIABLE:
            return self._answer_variable(data)
        if cmd == ENV_SHUTDOWN:
            self.shutdown_requested = True
            return True
        if cmd in ENV_ACCEPT_AND_IGNORE:
            return True
        if cmd in ENV_REFUSE:
            self.env_refused[cmd] = self.env_refused.get(cmd, 0) + 1
            return False

        self.env_unhandled[cmd] = self.env_unhandled.get(cmd, 0) + 1
        return False

    def _poke(self, data: int | None, ctype, value) -> bool:
        """Answer an environment call whose `data` is a pointer to one value."""
        if not data:
            return False
        ctypes.cast(data, POINTER(ctype))[0] = value
        return True

    def _write_string_ptr(self, data: int | None, key: str) -> bool:
        if not data:
            return False
        ctypes.cast(data, POINTER(c_void_p))[0] = ctypes.addressof(self._keepalive[key])
        return True

    def _read_variable_defaults(self, data: int | None) -> None:
        """RETRO_ENVIRONMENT_SET_VARIABLES: "Human title; first|second|third", first is the
        default. Reading them here means GET_VARIABLE can answer with the core's own defaults
        instead of a table copied into this file."""
        if not data:
            return
        array = ctypes.cast(data, POINTER(RetroVariable))
        i = 0
        while array[i].key:
            entry = array[i]
            value = entry.value or b""
            _, _, choices = value.partition(b";")
            default = choices.strip().split(b"|")[0].strip()
            if default:
                self.option_defaults[entry.key] = default
            i += 1

    def _answer_variable(self, data: int | None) -> bool:
        if not data:
            return False
        slots = ctypes.cast(data, POINTER(c_void_p))
        if not slots[0]:
            return False
        key = ctypes.string_at(slots[0])
        value = self.forced_options.get(key, self.option_defaults.get(key))
        if value is None:
            return False
        buf = self._var_bufs.get(key)
        if buf is None:
            buf = ctypes.create_string_buffer(value)
            self._var_bufs[key] = buf
        slots[1] = ctypes.addressof(buf)
        return True

    def _video_refresh(self, data: int | None, width: int, height: int, pitch: int) -> None:
        # RETRO_HW_FRAME_BUFFER_VALID is (void*)-1: "the frame is in the GL context, not here".
        # SET_HW_RENDER is refused so no core should send it, but dereferencing it would be a
        # segfault rather than an error, which is not a way to find out.
        if not data or data == HW_FRAME_BUFFER_VALID or not width or not height:
            self.frames_duped += 1  # a NULL frame means "same as last time"
            return
        # The last row is only `width` pixels wide, so reading a whole `pitch` past its start
        # can run off the core's buffer.
        _, bpp, _ = PIXEL_FORMATS[self.pixel_format]
        self.frame = ctypes.string_at(data, (height - 1) * pitch + width * bpp)
        self.frame_size = (width, height, pitch)
        self.frames_drawn += 1

    def _audio_sample(self, left: int, right: int) -> None:
        pass

    def _audio_batch(self, data, frames: int) -> int:
        return frames

    def _input_poll(self) -> None:
        self.polls += 1

    def _input_state(self, port: int, device: int, index: int, ident: int) -> int:
        if port != 0 or device != DEVICE_JOYPAD:
            return 0
        # One id per call: GET_INPUT_BITMASKS is not answered, so the core never asks for the
        # packed form (whose bit 15, R3, would not fit in the int16 this returns anyway).
        return 1 if ident in self.buttons else 0

    # --- lifecycle ------------------------------------------------------------------------

    def system_info(self) -> RetroSystemInfo:
        info = RetroSystemInfo()
        self.lib.retro_get_system_info(ctypes.byref(info))
        return info

    def av_info(self) -> RetroSystemAvInfo:
        info = RetroSystemAvInfo()
        self.lib.retro_get_system_av_info(ctypes.byref(info))
        return info

    def load_game(self, content: Path, need_fullpath: bool) -> bool:
        info = RetroGameInfo()
        info.path = str(content).encode()
        if need_fullpath:
            info.data, info.size = None, 0
        else:
            blob = content.read_bytes()
            self._keepalive["content"] = ctypes.create_string_buffer(blob, len(blob))
            info.data = ctypes.addressof(self._keepalive["content"])
            info.size = len(blob)
        self._keepalive["game_info"] = info
        return bool(self.lib.retro_load_game(ctypes.byref(info)))

    def save_state(self, path: Path) -> bool:
        size = self.lib.retro_serialize_size()
        if not size:
            return False
        buf = ctypes.create_string_buffer(size)
        if not self.lib.retro_serialize(ctypes.addressof(buf), size):
            return False
        path.write_bytes(buf.raw[:size])
        return True

    def load_state(self, path: Path) -> bool:
        blob = path.read_bytes()
        buf = ctypes.create_string_buffer(blob, len(blob))
        return bool(self.lib.retro_unserialize(ctypes.addressof(buf), len(blob)))

    def memory(self, kind: int) -> ctypes.Array | None:
        """The core's own buffer for RETRO_MEMORY_SAVE_RAM or _SYSTEM_RAM, writable in place;
        None if the core exposes none."""
        ptr, size = self.lib.retro_get_memory_data(kind), self.lib.retro_get_memory_size(kind)
        if not ptr or not size:
            return None
        return (ctypes.c_char * size).from_address(ptr)

    def distinct_colours(self) -> int:
        """How many different pixel values the last frame holds -- what a headless gate can
        assert on without eyes. DEFAULT_ASSERT_COLOURS records the measured spread."""
        if self.frame is None:
            return 0
        width, height, pitch = self.frame_size
        _, _, code = PIXEL_FORMATS[self.pixel_format]
        # The X byte of XRGB8888 is ignored by definition, so garbage there must not count as
        # colour -- that is an error that can only turn a blank screen green.
        mask = 0x00FFFFFF if code == "I" else 0xFFFF
        seen: set[int] = set()
        for y in range(height):
            seen.update(
                w & mask for w in struct.unpack_from(f"<{width}{code}", self.frame, y * pitch)
            )
        return len(seen)

    def screenshot(self, path: Path) -> tuple[int, int] | None:
        """Write the last frame as a PNG; None if the core has drawn nothing yet."""
        if self.frame is None:
            return None
        width, height, pitch = self.frame_size
        rows = to_rgb_rows(self.frame, self.pixel_format, width, height, pitch)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png(width, height, rows))
        return width, height

    def close(self) -> None:
        self.lib.retro_unload_game()
        self.lib.retro_deinit()


class CoreError(Exception):
    pass


class UsageError(Exception):
    pass


def parse_press(spec: str) -> tuple[int, int, int]:
    """FRAME:BUTTON[:HOLD] -> (first frame held, button id, last frame held)."""
    parts = spec.split(":")
    if len(parts) not in (2, 3):
        raise UsageError(f"--press wants FRAME:BUTTON[:HOLD], got {spec!r}")
    try:
        frame = int(parts[0])
        hold = int(parts[2]) if len(parts) == 3 else DEFAULT_HOLD
    except ValueError as exc:
        raise UsageError(f"--press {spec!r}: {exc}") from exc
    name = parts[1].strip().upper()
    if name not in BUTTONS:
        raise UsageError(f"--press {spec!r}: unknown button; known: {', '.join(sorted(BUTTONS))}")
    if frame < 1 or hold < 1:
        raise UsageError(f"--press {spec!r}: frame and hold start at 1")
    return frame, BUTTONS[name], frame + hold - 1


def read_press_file(path: Path) -> list[str]:
    """A schedule file: one FRAME:BUTTON[:HOLD] per line, `#` starts a comment.
    tools/libretro/boot-to-dialogue.press is the worked example."""
    lines = (raw.split("#", 1)[0].strip() for raw in path.read_text().splitlines())
    return [line for line in lines if line]


def default_shot_name(frame: int) -> str:
    return f"frame-{frame:05d}"


def parse_frame(frame_text: str, flag: str, spec: str, wants: str) -> int:
    try:
        frame = int(frame_text)
    except ValueError as exc:
        raise UsageError(f"{flag} wants {wants}, got {spec!r}") from exc
    if frame < 1:
        raise UsageError(f"{flag} {spec!r}: frames start at 1")
    return frame


def parse_at(spec: str, flag: str) -> tuple[int, str]:
    """FRAME[:NAME] -> (frame, name), defaulting the name to the frame number."""
    frame_text, _, name = spec.partition(":")
    frame = parse_frame(frame_text, flag, spec, "FRAME[:NAME]")
    return frame, name or default_shot_name(frame)


def parse_assert(spec: str) -> tuple[int, int]:
    """FRAME[:COLOURS] -> (frame, how many distinct pixel values that frame must hold)."""
    frame_text, _, colours = spec.partition(":")
    frame = parse_frame(frame_text, "--assert-drawn", spec, "FRAME[:COLOURS]")
    try:
        return frame, int(colours) if colours else DEFAULT_ASSERT_COLOURS
    except ValueError as exc:
        raise UsageError(f"--assert-drawn wants FRAME[:COLOURS], got {spec!r}") from exc


RAM_BYTES = 0x200000


def ram_offset(addr: int, n: int) -> int:
    """Byte offset into main RAM of a KUSEG, KSEG0 or KSEG1 address (0x0/0x8/0xA...)."""
    if addr >> 28 not in (0x0, 0x8, 0xA) or (addr & 0x1FFFFFFF) + n > RAM_BYTES:
        raise UsageError(f"0x{addr:08X}+{n} is not main RAM")
    return addr & 0x1FFFFFFF


def parse_peek(spec: str) -> tuple[int, int]:
    """ADDR:LEN (hex address, decimal length) -> (RAM offset, length) inside main RAM."""
    addr_text, sep, length_text = spec.partition(":")
    if not sep:
        raise UsageError(f"--peek wants ADDR:LEN, got {spec!r}")
    try:
        addr, length = int(addr_text, 16), int(length_text)
    except ValueError as exc:
        raise UsageError(f"--peek {spec!r}: {exc}") from exc
    if length < 1:
        raise UsageError(f"--peek {spec!r}: nothing to read")
    return ram_offset(addr, length), length


def parse_poke(spec: str) -> tuple[int, int, bytes]:
    """FRAME:ADDR=HEX -> (frame, RAM address, bytes), the address checked against main RAM."""
    at, sep, rest = spec.partition(":")
    addr_text, eq, hex_text = rest.partition("=")
    if not sep or not eq:
        raise UsageError(f"--poke wants FRAME:ADDR=HEX, got {spec!r}")
    frame = parse_frame(at, "--poke", spec, "FRAME:ADDR=HEX")
    try:
        addr, value = int(addr_text, 16), bytes.fromhex(hex_text)
    except ValueError as exc:
        raise UsageError(f"--poke {spec!r}: {exc}") from exc
    if not value:
        raise UsageError(f"--poke {spec!r}: no bytes to write")
    ram_offset(addr, len(value))
    return frame, addr, value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run a disc image on a libretro core headlessly and screenshot it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("content", type=Path, help="the .cue to boot (its .img must be beside it)")
    p.add_argument(
        "--core",
        type=Path,
        help="core dylib; default $BOKU_LIBRETRO_CORE, else retro-trainer's (emulator_paths.py)",
    )
    p.add_argument(
        "--system",
        type=Path,
        help="system directory holding the BIOS; default $BOKU_LIBRETRO_SYSTEM, else "
        "retro-trainer's (emulator_paths.py)",
    )
    p.add_argument(
        "--work",
        type=Path,
        default=Path("work/beetle"),
        help="where screenshots, states and memory cards go (default work/beetle)",
    )
    p.add_argument("--frames", type=int, default=600, help="how many retro_run calls to make")
    p.add_argument(
        "--press",
        action="append",
        default=[],
        metavar="FRAME:BUTTON[:HOLD]",
        help=f"hold a button from FRAME for HOLD frames (default {DEFAULT_HOLD})",
    )
    p.add_argument("--press-file", type=Path, help="a file of --press specs (text or JSON)")
    p.add_argument(
        "--shot",
        action="append",
        default=[],
        metavar="FRAME[:NAME]",
        help="write work-dir/NAME.png after that frame",
    )
    p.add_argument("--shot-every", type=int, metavar="N", help="also shoot every N frames")
    p.add_argument("--shot-from", type=int, default=1, help="first frame --shot-every considers")
    p.add_argument("--shot-to", type=int, help="last frame --shot-every considers")
    p.add_argument(
        "--state-out",
        action="append",
        default=[],
        metavar="FRAME[:NAME]",
        help="write work-dir/NAME.state after that frame",
    )
    p.add_argument("--state-in", type=Path, help="restore this state before the first frame")
    p.add_argument(
        "--memcard",
        type=Path,
        help="put this raw 128 KB card image (.mcd/.mcr) in slot 1 before the first frame; "
        "the file itself is never written",
    )
    p.add_argument(
        "--memcard-out",
        type=Path,
        help="write slot 1's card to this file after the last frame (whatever the game saved)",
    )
    p.add_argument(
        "--ram-out",
        action="append",
        default=[],
        metavar="FRAME[:NAME]",
        help="write main RAM (2 MB; byte n is RAM 0x80000000+n) to work-dir/NAME.ram after "
        "that frame",
    )
    p.add_argument(
        "--poke",
        action="append",
        default=[],
        metavar="FRAME:ADDR=HEX",
        help="write these bytes at RAM address ADDR (hex) just before FRAME runs; repeatable",
    )
    p.add_argument(
        "--peek",
        action="append",
        default=[],
        metavar="ADDR:LEN",
        help="sample LEN (decimal) bytes of RAM at ADDR (hex) into work-dir/peek.tsv, which "
        "each run rewrites: after every --peek-every'th frame from --peek-from to --peek-to "
        "(default the last frame), one line per frame -- the frame, then one hex column per "
        "--peek; repeatable",
    )
    p.add_argument("--peek-every", type=int, default=1, metavar="N")
    p.add_argument("--peek-from", type=int, default=1)
    p.add_argument("--peek-to", type=int)
    p.add_argument(
        "--assert-drawn",
        action="append",
        default=[],
        metavar="FRAME[:COLOURS]",
        help="exit 6 unless that frame holds at least COLOURS distinct pixel values "
        f"(default {DEFAULT_ASSERT_COLOURS}); a blank or BIOS-only screen holds a handful",
    )
    p.add_argument(
        "--option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="force a core option; repeatable",
    )
    p.add_argument(
        "--log-level",
        type=int,
        default=2,
        choices=range(5),
        help="lowest core log level to print (0 debug .. 3 error, 4 silent)",
    )
    p.add_argument(
        "--allow-hle-bios",
        action="store_true",
        help="run even if the core reports no BIOS in the system directory (it boots on its "
        "own HLE one, which is not the machine Mode One runs)",
    )
    p.add_argument("--quiet", action="store_true", help="only print the summary line")
    return p


def resolve_paths(args) -> tuple[Path, Path, Path]:
    try:
        core = Path(args.core).expanduser() if args.core else emulator_paths.core()
        system = Path(args.system).expanduser() if args.system else emulator_paths.system()
    except emulator_paths.NotFound as exc:
        raise UsageError(f"{exc} (or pass --core / --system)") from exc
    if not core.is_file():
        raise UsageError(f"core is not a file: {core}")
    if not system.is_dir():
        raise UsageError(f"system directory does not exist: {system}")
    content = args.content.expanduser()
    if not content.is_file():
        raise UsageError(f"content is not a file: {content}")
    return core, system, content


def schedule_presses(args) -> dict[int, frozenset[int]]:
    specs = list(args.press)
    if args.press_file:
        specs += read_press_file(args.press_file)
    held: dict[int, set[int]] = {}
    for spec in specs:
        first, button, last = parse_press(spec)
        for frame in range(first, last + 1):
            held.setdefault(frame, set()).add(button)
    return {frame: frozenset(buttons) for frame, buttons in held.items()}


def shot_frames(args) -> dict[int, str]:
    shots = {}
    for spec in args.shot:
        frame, name = parse_at(spec, "--shot")
        shots[frame] = name
    if args.shot_every:
        last = args.shot_to or args.frames
        for frame in range(args.shot_from, last + 1):
            if (frame - args.shot_from) % args.shot_every == 0:
                shots.setdefault(frame, default_shot_name(frame))
    return shots


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.memcard and args.state_in:
            # A Beetle state carries the card it was saved with (frontio.c's memcard
            # StateAction), so restoring one after --memcard would silently swap the card back.
            raise UsageError("--memcard and --state-in conflict: the state brings its own card")
        core, system, content = resolve_paths(args)
        presses = schedule_presses(args)
        shots = shot_frames(args)
        states = dict(parse_at(spec, "--state-out") for spec in args.state_out)
        rams = dict(parse_at(spec, "--ram-out") for spec in args.ram_out)
        peeks = [parse_peek(spec) for spec in args.peek]
        peek_to = args.frames if args.peek_to is None else args.peek_to
        if args.peek_every < 1:
            raise UsageError("--peek-every must be at least 1")
        if not peeks and (args.peek_to is not None or args.peek_from != 1):
            raise UsageError("--peek-from/--peek-to sample nothing without a --peek")
        if peeks and not 1 <= args.peek_from <= peek_to <= args.frames:
            raise UsageError(
                f"the --peek window {args.peek_from}..{peek_to} is not inside the run's "
                f"{args.frames} frames"
            )
        pokes: dict[int, list[tuple[int, bytes]]] = {}
        for spec in args.poke:
            at, addr, value = parse_poke(spec)
            pokes.setdefault(at, []).append((addr, value))
        card = args.memcard.expanduser().read_bytes() if args.memcard else None
        asserts = dict(parse_assert(spec) for spec in args.assert_drawn)
        # Nothing is forced by default: the software renderer is not a core option here, it is
        # what refusing SET_HW_RENDER leaves the core with.
        forced = {}
        for item in args.option:
            key, sep, value = item.partition("=")
            if not sep:
                raise UsageError(f"--option wants KEY=VALUE, got {item!r}")
            forced[key] = value
        forced_bytes = {k.encode(): v.encode() for k, v in forced.items()}
    except (UsageError, OSError) as exc:
        print(f"run_core: {exc}", file=sys.stderr)
        return EXIT_USAGE

    work = args.work.expanduser()
    # Memory cards and any other core save go here, never next to the disc image.
    saves = work / "saves"
    saves.mkdir(parents=True, exist_ok=True)

    def say(message: str) -> None:
        if not args.quiet:
            print(message, file=sys.stderr)

    try:
        fe = Frontend(core, system, saves, forced_bytes, args.log_level)
    except CoreError as exc:
        print(f"run_core: {exc}", file=sys.stderr)
        return EXIT_CORE

    info = fe.system_info()
    say(
        f"core: {info.library_name.decode()} {info.library_version.decode()} "
        f"(api {fe.lib.retro_api_version()}, need_fullpath={info.need_fullpath})"
    )
    fe.lib.retro_init()

    if not fe.load_game(content, bool(info.need_fullpath)):
        print(
            f"run_core: the core refused {content} -- it could not read the disc. Check that "
            "the .cue names its .img and that the .img is beside it. (A missing BIOS does "
            "not land here: Beetle loads the game anyway and boots HLE, which is exit 7.)",
            file=sys.stderr,
        )
        fe.lib.retro_deinit()
        return EXIT_GAME

    if fe.firmware_missing and not args.allow_hle_bios:
        print(
            f"run_core: the core found no BIOS in {system} and fell back to its own HLE one. "
            "It will boot, but not the machine Mode One runs, so the result would not be "
            "confirmation of anything. Put scph5500.bin there, or pass --allow-hle-bios.",
            file=sys.stderr,
        )
        fe.close()
        return EXIT_FIRMWARE

    fe.lib.retro_set_controller_port_device(0, DEVICE_JOYPAD)
    av = fe.av_info()
    say(
        f"game: {content} -> {av.geometry.base_width}x{av.geometry.base_height} "
        f"@ {av.timing.fps:.4f} Hz, pixel format {PIXEL_FORMATS[fe.pixel_format][0]}"
    )

    if card is not None:
        slot = fe.memory(MEMORY_SAVE_RAM)
        if slot is None or len(slot) != len(card):
            have = "no card buffer" if slot is None else f"a {len(slot)}-byte card"
            print(
                f"run_core: --memcard {args.memcard} is {len(card)} bytes but the core exposes "
                f"{have} as SAVE_RAM (is beetle_psx_use_mednafen_memcard0_method forced to "
                "'mednafen'?)",
                file=sys.stderr,
            )
            fe.close()
            return EXIT_USAGE
        slot[:] = card
        say(f"memcard: slot 1 <- {args.memcard}")

    ram = fe.memory(MEMORY_SYSTEM_RAM) if pokes or rams or peeks else None
    if (pokes or rams or peeks) and ram is None:
        print(
            "run_core: the core exposes no SYSTEM_RAM for --poke/--ram-out/--peek", file=sys.stderr
        )
        fe.close()
        return EXIT_STATE

    status = EXIT_OK
    if args.state_in:
        if not fe.load_state(args.state_in):
            print(f"run_core: the core refused the state {args.state_in}", file=sys.stderr)
            fe.close()
            return EXIT_STATE
        say(f"state: restored {args.state_in}")

    peek_out = None
    if peeks:
        work.mkdir(parents=True, exist_ok=True)
        peek_out = (work / "peek.tsv").open("w", encoding="ascii")

    started = time.monotonic()
    frame = 0
    for frame in range(1, args.frames + 1):
        fe.buttons = presses.get(frame, frozenset())
        for addr, value in pokes.get(frame, ()):
            at = ram_offset(addr, len(value))
            ram[at : at + len(value)] = value
            say(f"poke: frame {frame} 0x{addr:08X} <- {value.hex()}")
        fe.lib.retro_run()
        if frame in shots:
            out = work / f"{shots[frame]}.png"
            size = fe.screenshot(out)
            if size is None:
                print(
                    f"run_core: nothing to shoot at frame {frame}: the core has drawn no frame yet",
                    file=sys.stderr,
                )
                status = EXIT_ASSERT
                break
            say(f"shot: frame {frame} -> {out} ({size[0]}x{size[1]})")
        if frame in asserts:
            seen, want = fe.distinct_colours(), asserts[frame]
            if seen < want:
                print(
                    f"run_core: frame {frame} holds {seen} distinct pixel values, wanted at "
                    f"least {want} -- the core ran but drew nothing recognisable",
                    file=sys.stderr,
                )
                status = EXIT_ASSERT
                break
            say(f"assert: frame {frame} holds {seen} distinct pixel values (wanted {want})")
        if frame in states:
            out = work / f"{states[frame]}.state"
            out.parent.mkdir(parents=True, exist_ok=True)
            if not fe.save_state(out):
                print(f"run_core: retro_serialize failed at frame {frame}", file=sys.stderr)
                status = EXIT_STATE
                break
            say(f"state: frame {frame} -> {out} ({out.stat().st_size} bytes)")
        if (
            peek_out
            and args.peek_from <= frame <= peek_to
            and (frame - args.peek_from) % args.peek_every == 0
        ):
            cols = [ram[at : at + n].hex() for at, n in peeks]
            peek_out.write("\t".join([str(frame), *cols]) + "\n")
        if frame in rams:
            out = work / f"{rams[frame]}.ram"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(ram.raw)
            say(f"ram: frame {frame} -> {out}")
        if fe.shutdown_requested:
            say(f"core asked to shut down at frame {frame}")
            break
    elapsed = time.monotonic() - started
    if peek_out:
        peek_out.close()

    # A frame that was asked for and never happened is a failure, not a note: the core can ask
    # to shut down early, and a gate whose --assert-drawn frame never arrived would otherwise
    # report success for a run that never tested anything.
    wanted = set(shots) | set(states) | set(asserts) | set(rams) | set(pokes)
    if peeks:
        wanted.add(peek_to)
    missed = sorted(f for f in wanted if f > frame)
    if missed:
        print(
            f"run_core: never reached frame(s) {missed} -- stopped at {frame} of {args.frames}",
            file=sys.stderr,
        )
        status = status or EXIT_INCOMPLETE

    if args.memcard_out:
        slot = fe.memory(MEMORY_SAVE_RAM)
        if slot is None:
            print("run_core: the core exposes no SAVE_RAM to write out", file=sys.stderr)
            status = status or EXIT_STATE
        else:
            args.memcard_out.parent.mkdir(parents=True, exist_ok=True)
            args.memcard_out.write_bytes(slot.raw)
            say(f"memcard: slot 1 -> {args.memcard_out}")

    def env_name(cmd: int) -> str:
        return ENV_NAMES.get(cmd, f"env{cmd}")

    say(f"env asked: { ({env_name(c): n for c, n in sorted(fe.env_counts.items())}) }")
    say(f"env refused on purpose: {sorted(map(env_name, fe.env_refused))}")
    say(f"env unimplemented: {sorted(map(env_name, fe.env_unhandled))}")
    print(
        f"ran {frame} frames in {elapsed:.1f}s = {frame / max(elapsed, 1e-6):.1f} fps "
        f"({fe.frames_drawn} drawn, {fe.frames_duped} duped, {fe.polls} polls)",
        file=sys.stderr,
    )

    fe.close()
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
