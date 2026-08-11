r"""
search_signs.py

Searches every region file (.mca) in a Minecraft world's "region" folder for
sign block entities, and prints their text and coordinates.

Works across the format changes between versions:
- Pre-1.18 worlds (CV3, CV4, CV5, CV6, Blipville - all 1.16.5):
    chunk root -> "Level" -> "TileEntities", sign text in Text1-Text4
- 1.18+ worlds (CV7 - 1.20.4):
    chunk root -> "block_entities" directly, sign text in
    front_text/back_text -> "messages"

Usage:
    python search_signs.py "C:\path\to\cv4"
    python search_signs.py "C:\path\to\cv4" --find "keyword"

If --find is given, only signs containing that text (case-insensitive) are shown.
Otherwise, every sign found in the world is printed.

No third-party packages required, just a normal Python install.
"""

import io
import json
import struct
import zlib
import gzip
import argparse
from pathlib import Path
from multiprocessing import Pool, cpu_count


# ---------------------------------------------------------------------------
# Minimal, selective NBT reader.
#
# A full-featured NBT library (like nbtlib) decodes every part of a chunk,
# including all the terrain data (block states, biomes, heightmaps), which
# is the vast majority of a chunk's bytes and something this script never
# needs. Instead, this only fully decodes the parts we actually care about
# (tile entities / block entities) and skips everything else by seeking
# past it without ever building Python objects for it. That skipping is
# what makes large worlds like CV7 scan several times faster.
# ---------------------------------------------------------------------------

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

_FIXED_SIZE = {TAG_BYTE: 1, TAG_SHORT: 2, TAG_INT: 4, TAG_LONG: 8, TAG_FLOAT: 4, TAG_DOUBLE: 8}
_STRUCT_FMT = {TAG_BYTE: ">b", TAG_SHORT: ">h", TAG_INT: ">i", TAG_LONG: ">q", TAG_FLOAT: ">f", TAG_DOUBLE: ">d"}


def _read_ubyte(f):
    return f.read(1)[0]


def _read_ushort(f):
    return struct.unpack(">H", f.read(2))[0]


def _read_int(f):
    return struct.unpack(">i", f.read(4))[0]


def _read_string(f):
    n = _read_ushort(f)
    return f.read(n).decode("utf-8", errors="replace")


def _skip_string(f):
    n = _read_ushort(f)
    f.seek(n, 1)


def _skip_payload(f, tag_type):
    """Discard a tag's payload without materializing it into Python objects."""
    if tag_type in _FIXED_SIZE:
        f.seek(_FIXED_SIZE[tag_type], 1)
    elif tag_type == TAG_BYTE_ARRAY:
        n = _read_int(f)
        f.seek(n, 1)
    elif tag_type == TAG_STRING:
        _skip_string(f)
    elif tag_type == TAG_LIST:
        elem_type = _read_ubyte(f)
        n = _read_int(f)
        if elem_type != TAG_END:
            for _ in range(n):
                _skip_payload(f, elem_type)
    elif tag_type == TAG_COMPOUND:
        while True:
            t = _read_ubyte(f)
            if t == TAG_END:
                break
            _skip_string(f)
            _skip_payload(f, t)
    elif tag_type == TAG_INT_ARRAY:
        n = _read_int(f)
        f.seek(n * 4, 1)
    elif tag_type == TAG_LONG_ARRAY:
        n = _read_int(f)
        f.seek(n * 8, 1)
    else:
        raise ValueError(f"Unknown NBT tag type: {tag_type}")


def _read_value(f, tag_type, selector=None):
    """
    Fully decode a tag's payload into a plain Python value (dict / list /
    str / number). `selector` only matters when tag_type is TAG_COMPOUND:
    a dict means "only decode these keys, skip the rest"; None means
    "decode everything at and below this point" (used once we're already
    inside a subtree we know is small, like a single tile entity).
    """
    if tag_type == TAG_COMPOUND:
        return _read_compound(f, selector if isinstance(selector, dict) else None)
    if tag_type == TAG_LIST:
        elem_type = _read_ubyte(f)
        n = _read_int(f)
        items = []
        if elem_type != TAG_END:
            for _ in range(n):
                items.append(_read_value(f, elem_type, None))
        return items
    if tag_type == TAG_STRING:
        return _read_string(f)
    if tag_type in _STRUCT_FMT:
        fmt = _STRUCT_FMT[tag_type]
        return struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]
    if tag_type == TAG_BYTE_ARRAY:
        n = _read_int(f)
        f.seek(n, 1)
        return None
    if tag_type == TAG_INT_ARRAY:
        n = _read_int(f)
        f.seek(n * 4, 1)
        return None
    if tag_type == TAG_LONG_ARRAY:
        n = _read_int(f)
        f.seek(n * 8, 1)
        return None
    raise ValueError(f"Unknown NBT tag type: {tag_type}")


def _read_compound(f, selector=None):
    """
    Read a compound's tags until TAG_End.
    selector=None  -> fully decode every key.
    selector={...} -> only decode keys present in the dict, skip the rest.
                      Values are the nested selector to use if that key is
                      itself a compound (None = fully decode from there).
    """
    result = {}
    while True:
        t = _read_ubyte(f)
        if t == TAG_END:
            break
        name = _read_string(f)
        if selector is None:
            result[name] = _read_value(f, t, None)
        elif name in selector:
            result[name] = _read_value(f, t, selector[name])
        else:
            _skip_payload(f, t)
    return result


# Only descend into "Level" (pre-1.18) or "block_entities" (1.18+) at the
# chunk root, and only "TileEntities" within "Level". Everything else at
# the root (Sections/block states, Biomes, Heightmaps, Entities, Structures,
# ...) is skipped without ever being decoded - that's the bulk of a chunk.
_ROOT_SELECTOR = {
    "Level": {"TileEntities": None},
    "block_entities": None,
}


def parse_chunk_root(raw_bytes):
    """Selectively parse a decompressed chunk's NBT bytes, returning a
    plain dict containing only the tile-entity-relevant data."""
    f = io.BytesIO(raw_bytes)
    root_type = _read_ubyte(f)
    if root_type != TAG_COMPOUND:
        return {}
    _read_string(f)  # root tag name (usually empty), discard
    return _read_compound(f, _ROOT_SELECTOR)


# ---------------------------------------------------------------------------
# Region file (.mca) handling
# ---------------------------------------------------------------------------

def iter_region_chunk_data(mca_path):
    """
    Manually parse a .mca region file's header and yield each present
    chunk's selectively-parsed data (see parse_chunk_root above).
    """
    with open(mca_path, "rb") as f:
        header = f.read(4096)
        if len(header) < 4096:
            return  # empty/incomplete region file

        for i in range(1024):
            offset_bytes = header[i * 4: i * 4 + 3]
            sector_count = header[i * 4 + 3]
            offset = int.from_bytes(offset_bytes, "big")
            if offset == 0 or sector_count == 0:
                continue  # chunk not present

            f.seek(offset * 4096)
            length_bytes = f.read(4)
            if len(length_bytes) < 4:
                continue
            length = int.from_bytes(length_bytes, "big")
            compression_type = f.read(1)[0]
            payload = f.read(length - 1)

            try:
                if compression_type == 1:
                    raw = gzip.decompress(payload)
                elif compression_type == 2:
                    raw = zlib.decompress(payload)
                elif compression_type == 3:
                    raw = payload  # uncompressed
                else:
                    continue
                yield parse_chunk_root(raw)
            except Exception:
                continue


def extract_text(tag_value):
    """
    Sign text lines are stored as a string containing JSON, e.g. '"Hello"'
    or '{"text":"Hello"}'. This pulls out the readable text regardless of
    which version's flavor of the text component it is.
    """
    if tag_value is None:
        return ""
    raw = str(tag_value)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw  # fallback: just show the raw string

    def flatten(obj):
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            parts = [obj.get("text", "")]
            for extra in obj.get("extra", []):
                parts.append(flatten(extra))
            return "".join(parts)
        if isinstance(obj, list):
            return "".join(flatten(o) for o in obj)
        return ""

    return flatten(parsed)


def get_tile_entities(chunk_data):
    """
    Returns the list of tile/block entities for a chunk, regardless of
    whether it's a pre-1.18 chunk (Level -> TileEntities) or a 1.18+
    chunk (block_entities at the root).
    """
    if "Level" in chunk_data:
        level = chunk_data["Level"]
        return level.get("TileEntities", [])
    return chunk_data.get("block_entities", [])


def get_sign_lines(te):
    """
    Returns the list of text lines for a sign tile entity, regardless of
    whether it uses the old Text1-Text4 format or the new (1.20+)
    front_text/back_text format. For double-sided signs, front text is
    listed first, then back text.
    """
    lines = []

    # Pre-1.20 format
    for i in range(1, 5):
        key = f"Text{i}"
        if key in te:
            lines.append(extract_text(te.get(key)))

    # 1.20+ format
    for side_key in ("front_text", "back_text"):
        side = te.get(side_key)
        if side is not None:
            for message in side.get("messages", []):
                lines.append(extract_text(message))

    return lines


def scan_region_file(mca_path):
    """
    Scans a single region file for signs. Runs in a worker process.
    Returns (list_of_signs, None) on success or ([], (filename, error)) on failure.
    """
    found = []
    try:
        for chunk_data in iter_region_chunk_data(mca_path):
            for te in get_tile_entities(chunk_data):
                te_id = str(te.get("id", ""))
                if "sign" not in te_id.lower():
                    continue
                x = int(te.get("x"))
                y = int(te.get("y"))
                z = int(te.get("z"))
                lines = get_sign_lines(te)
                found.append({
                    "x": x, "y": y, "z": z,
                    "lines": lines,
                    "file": mca_path.name,
                })
        return found, None
    except Exception as e:
        return [], (mca_path.name, str(e))


def find_signs(world_path):
    region_dir = Path(world_path) / "region"
    if not region_dir.exists():
        print(f"No 'region' folder found at {region_dir}")
        return []

    signs = []
    mca_files = sorted(region_dir.glob("*.mca"))
    print(f"Scanning {len(mca_files)} region files in {region_dir} ...")

    # Bigger/newer worlds (like CV7) have far more explored region files than
    # older ones, so this scans multiple files at once across CPU cores
    # instead of one at a time, which is significantly faster on large worlds.
    worker_count = max(cpu_count() - 1, 1)
    with Pool(processes=worker_count) as pool:
        for file_signs, error in pool.imap_unordered(scan_region_file, mca_files):
            if error:
                print(f"  (skipped {error[0]}: {error[1]})")
            else:
                signs.extend(file_signs)

    return signs


def main():
    parser = argparse.ArgumentParser(description="Search sign text in a Minecraft world (1.13-1.20.x).")
    parser.add_argument("world_path", help="Path to the world save folder (e.g. the 'cv4' folder)")
    parser.add_argument("--find", help="Only show signs containing this text (case-insensitive)", default=None)
    args = parser.parse_args()

    signs = find_signs(args.world_path)

    if args.find:
        needle = args.find.lower()
        signs = [s for s in signs if any(needle in line.lower() for line in s["lines"])]

    print(f"\nFound {len(signs)} matching sign(s):\n")
    for s in signs:
        text = " | ".join(line for line in s["lines"] if line.strip())
        print(f"({s['x']}, {s['y']}, {s['z']})  ->  {text}")


if __name__ == "__main__":
    main()
