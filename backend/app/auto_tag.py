"""Filename-based tags, following frontend/src/utils/autoTag.js."""

import re


POLARITY = {"pos", "neg", "positive", "negative"}


def sanitize_tag(value):
    value = re.sub(r"\s+", "_", value.strip())
    return re.sub(r"[^A-Za-z0-9_+.-]", "", value)


def compress_runs(tag):
    parts = tag.split("_")
    result = []
    i = 0
    while i < len(parts):
        match = re.fullmatch(r"([A-Za-z]+)([0-9]+)", parts[i])
        j = i
        if match:
            while j + 1 < len(parts):
                current = re.fullmatch(r"([A-Za-z]+)([0-9]+)", parts[j])
                following = re.fullmatch(r"([A-Za-z]+)([0-9]+)", parts[j + 1])
                if (following and following[1] == match[1]
                        and int(following[2]) == int(current[2]) + 1):
                    j += 1
                else:
                    break
        if j > i:
            last = re.fullmatch(r"([A-Za-z]+)([0-9]+)", parts[j])
            result.append(f"{parts[i]}-{last[2]}")
        else:
            result.append(parts[i])
        i = j + 1
    return "_".join(result)


def suggest_tags(file_names):
    stems = [re.sub(r"\.mzml$", "", name, flags=re.IGNORECASE) for name in file_names]
    parts = [[part for part in re.split(r"[_\-. ]+", stem) if part] for stem in stems]
    common = set()
    if len(parts) > 1:
        common = set(part.lower() for part in parts[0])
        for tokens in parts[1:]:
            common.intersection_update(part.lower() for part in tokens)

    tags = []
    used = set()
    for stem, tokens in zip(stems, parts):
        kept = [part for part in tokens
                if part.lower() not in common or part.lower() in POLARITY]
        base = sanitize_tag(compress_runs("_".join(kept))) or sanitize_tag(stem)
        tag = base
        suffix = 2
        while tag in used:
            tag = f"{base}_{suffix}"
            suffix += 1
        used.add(tag)
        tags.append(tag)
    return tags
