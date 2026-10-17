#!/usr/bin/env python3
"""Audit the uploaded named binaries against another Minecraft version.

This reports class references and *directly declared*, mapped members that
cannot be found in the target version's official -> intermediary mapping. It
is a porting aid, not a bytecode transformer or a runtime compatibility test.
Inherited calls, unmapped members, constructors (not in intermediary's v1
mapping) and external libraries require separate review.

Use the complete FabricMC/intermediary mappings/<version>.tiny file as --target.
Yarn's Enigma mapping sources omit unmapped members and give false positives.
"""

from __future__ import annotations

import argparse
import collections
import io
import re
import struct
import zipfile
from pathlib import Path

from prepare_archives import ROOT, ZELITH_ZIP, prepare

TYPES = re.compile(r"L([^;]+);")
MC_TYPE = re.compile(r"L(net/minecraft/[^;<>]+);")


def translate_descriptor(descriptor: str, classes: dict[str, str]) -> str:
    return TYPES.sub(lambda match: "L" + classes.get(match.group(1), match.group(1)) + ";", descriptor)


def source_mappings(data: str):
    """Read the source archive's Tiny 2 intermediary -> named mapping."""
    lines = data.splitlines()
    if not lines or lines[0] != "tiny\t2\t0\tintermediary\tnamed":
        raise ValueError("Expected Tiny 2 intermediary -> named mappings")
    classes = {}
    for line in lines[1:]:
        if line.startswith("c\t"):
            _, intermediary, named = line.split("\t")[:3]
            classes[intermediary] = named
    members = {}
    owner = None
    for line in lines[1:]:
        if line.startswith("c\t"):
            owner = line.split("\t")[1]
        elif owner and line.startswith(("\tf\t", "\tm\t")):
            parts = line.split("\t")
            if len(parts) < 5:
                raise ValueError(f"Malformed Tiny member: {line}")
            _, tag, descriptor, intermediary, named = parts[:5]
            kind = "method" if tag == "m" else "field"
            named_owner = classes.get(owner, owner)
            named_desc = translate_descriptor(descriptor, classes)
            members[(named_owner, kind, named, named_desc)] = (owner, kind, intermediary, descriptor)
    return classes, members


def target_mappings(data: str):
    """Read the *full* Tiny v1 official -> intermediary mapping for the target."""
    lines = data.splitlines()
    if not lines or lines[0] != "v1\tofficial\tintermediary":
        raise ValueError("Expected complete Tiny v1 official -> intermediary mappings")
    classes = {}
    for line in lines[1:]:
        if line.startswith("CLASS\t"):
            _, official, intermediary = line.split("\t")
            classes[official] = intermediary
    members = set()
    descriptors = collections.defaultdict(set)
    for line in lines[1:]:
        if line.startswith(("FIELD\t", "METHOD\t")):
            tag, official_owner, official_descriptor, _name, intermediary_name = line.split("\t")
            kind = "method" if tag == "METHOD" else "field"
            owner = classes.get(official_owner, official_owner)
            descriptor = translate_descriptor(official_descriptor, classes)
            members.add((owner, kind, intermediary_name, descriptor))
            descriptors[(owner, kind, intermediary_name)].add(descriptor)
    return set(classes.values()), members, descriptors


def constant_pool(data: bytes):
    """Return UTF8 and Class/Fieldref/Methodref/InterfaceMethodref entries.

    Only the constant pool is scanned; neither the mod nor its uploaded JARs
    are executed. Java's modified UTF-8 is decoded with replacement because
    class/member names and descriptors themselves are ASCII.
    """
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        raise ValueError("Not a Java class file")
    count = struct.unpack_from(">H", data, 8)[0]
    offset = 10
    pool = {}
    index = 1
    while index < count:
        tag = data[offset]
        if tag == 1:  # Utf8
            size = struct.unpack_from(">H", data, offset + 1)[0]
            pool[index] = (tag, data[offset + 3 : offset + 3 + size].decode("utf-8", "replace"))
            offset += 3 + size
        elif tag in (7, 8, 16, 19, 20):
            pool[index] = (tag, struct.unpack_from(">H", data, offset + 1)[0])
            offset += 3
        elif tag in (9, 10, 11, 12, 17, 18):
            pool[index] = (tag, *struct.unpack_from(">HH", data, offset + 1))
            offset += 5
        elif tag in (3, 4):
            offset += 5
        elif tag in (5, 6):
            offset += 9
            index += 1  # long/double occupy two CP slots
        elif tag == 15:
            offset += 4
        else:
            raise ValueError(f"Unknown constant-pool tag {tag} at offset {offset}")
        if offset > len(data):
            raise ValueError("Truncated class file")
        index += 1
    return pool


def references(data: bytes):
    pool = constant_pool(data)
    utf8 = lambda index: pool[index][1]
    classes = set()
    members = set()
    for entry in pool.values():
        tag = entry[0]
        if tag == 7:
            name = utf8(entry[1])
            if name.startswith("net/minecraft/"):
                classes.add(name)
        elif tag == 1:
            # A class may appear only in a method/field descriptor and not have
            # a separate CONSTANT_Class entry in that particular class file.
            classes.update(MC_TYPE.findall(entry[1]))
        elif tag in (9, 10, 11):
            owner = utf8(pool[entry[1]][1])
            if owner.startswith("net/minecraft/"):
                _tag, name, descriptor = pool[entry[2]]
                members.add((owner, "field" if tag == 9 else "method", utf8(name), utf8(descriptor)))
    return classes, members


def audit(jars: list[Path], old_tiny: str, new_tiny: str):
    old_classes, old_members = source_mappings(old_tiny)
    new_classes, new_members, new_descriptors = target_mappings(new_tiny)
    named_to_intermediary = {named: intermediary for intermediary, named in old_classes.items()}
    missing_classes = collections.defaultdict(set)
    changed_members = collections.defaultdict(set)
    unknown_members = collections.defaultdict(set)
    known_members = 0
    inspected = 0
    for jar in jars:
        with zipfile.ZipFile(jar) as archive:
            for filename in archive.namelist():
                if not filename.endswith(".class"):
                    continue
                inspected += 1
                user = jar.name + ":" + filename
                class_refs, member_refs = references(archive.read(filename))
                for name in class_refs:
                    intermediary = named_to_intermediary.get(name)
                    if intermediary is None:
                        missing_classes[(name, "not in supplied source mapping")].add(user)
                    elif intermediary not in new_classes:
                        missing_classes[(name, intermediary)].add(user)
                for ref in member_refs:
                    original = old_members.get(ref)
                    if original is None:
                        # Likely an inherited method; cannot decide without a
                        # class-hierarchy lookup. Never report it as missing.
                        unknown_members[ref].add(user)
                    elif original[2].startswith(("method_", "field_", "comp_")):
                        if original in new_members:
                            known_members += 1
                        else:
                            key = (ref, original, tuple(sorted(new_descriptors.get(original[:3], ()))))
                            changed_members[key].add(user)
                    else:
                        # Constructors and identity/unmapped names (equals,
                        # get, accept, etc.) are omitted from Tiny v1 even if
                        # the target binary still has them.
                        unknown_members[ref].add(user)
    return inspected, known_members, missing_classes, changed_members, unknown_members


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True,
                        help="full intermediary mappings/<version>.tiny (official -> intermediary)")
    parser.add_argument("--limit", type=int, default=60, help="maximum entries per category")
    args = parser.parse_args()
    # Reuse the exact repaired classes used by the build, including the original
    # Async Locator binary. Preparation is deterministic and does not run JARs.
    zelith, async_jar = prepare(ROOT / "build" / "prepared")
    with zipfile.ZipFile(ZELITH_ZIP) as source:
        old_tiny = source.read("mappings-used.tiny").decode("utf-8")
    result = audit([zelith, async_jar], old_tiny, args.target.read_text(encoding="utf-8"))
    inspected, valid, absent, changed, unresolved = result
    print(f"Scanned {inspected} original classes; {valid} directly declared mapped member references still match.")
    print(f"Absent or unmapped Minecraft classes: {len(absent)}; "
          f"changed/removed declared members: {len(changed)}; "
          f"unresolved inherited/unmapped member references: {len(unresolved)}.")
    print("Constructors are omitted from the member check (not present in target Tiny v1).")
    print("Graphics libraries, Fabric API, runtime mixins and game behavior are NOT checked.\n")
    for title, findings in (("Absent or unmapped Minecraft classes", absent),
                            ("Changed/removed declared members", changed)):
        print(title + ":")
        for key, users in sorted(findings.items(), key=lambda item: (-len(item[1]), str(item[0])))[:args.limit]:
            if title.startswith("Changed"):
                (owner, kind, member, desc), (inter_owner, _, inter_member, inter_desc), possible = key
                alternative = " -> " + ", ".join(possible) if possible else " (no same-ID member mapped)"
                display = f"{owner}.{member}{desc}" if kind == "method" else f"{owner}.{member}: {desc}"
                print(f"  {display} [{kind} {inter_owner}.{inter_member}{inter_desc}]"
                      f"{alternative} : {len(users)} original classes")
            else:
                print(f"  {key[0]} [{key[1]}] : {len(users)} original classes")
        if len(findings) > args.limit:
            print(f"  ... {len(findings) - args.limit} more")
    print("\nThis is NOT a 1.21.4 build or proof of runtime compatibility.")


if __name__ == "__main__":
    main()
