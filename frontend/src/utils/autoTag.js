/**
 * Automatic tag suggestions for mzML files.
 *
 * Rule: keep what makes each file different from the others in this project,
 * drop what they all share. It does not need to know what the parts mean.
 *
 *   1. split each name (without .mzML) into parts at "_", "-", "." and spaces
 *   2. drop parts that every file has (case-insensitive)
 *   3. always keep the ionisation mode (pos/neg/positive/negative)
 *   4. shorten numbered runs: SC07_SC08_SC09 -> SC07-09
 *   5. keep the original order and spelling
 *   6. make tags unique with _2, _3 ...
 *   fallback: if nothing would be left, keep the full name
 *
 * Examples
 *   SC07_SC08_SC09_Inlet_ACN_DCM_neg + SC10_SC11_SC12_Outlet_ACN_DCM_pos
 *     -> SC07-09_Inlet_neg, SC10-12_Outlet_pos
 *   ISB401_AA_KO_NEG_DLD3_1 + ISB401_AA_WT_POS_FY4_1
 *     -> KO_NEG_DLD3, WT_POS_FY4
 */

const POLARITY = new Set(['pos', 'neg', 'positive', 'negative']);

/** Characters allowed in a tag (tags are used in output file names). */
export function sanitizeTag(value) {
  return String(value ?? '')
    .trim()
    .replace(/\s+/g, '_')
    .replace(/[^A-Za-z0-9_+\-.]/g, '');
}

function stem(fileName) {
  return String(fileName).replace(/\.mzml$/i, '');
}

function parts(fileName) {
  return stem(fileName).split(/[_\-. ]+/).filter(Boolean);
}

/** SC07_SC08_SC09 -> SC07-09 (consecutive numbers with the same prefix). */
export function compressRuns(tag) {
  const p = tag.split('_');
  const out = [];
  let i = 0;
  while (i < p.length) {
    const m = /^([A-Za-z]+)(\d+)$/.exec(p[i]);
    let j = i;
    if (m) {
      while (j + 1 < p.length) {
        const cur = /^([A-Za-z]+)(\d+)$/.exec(p[j]);
        const next = /^([A-Za-z]+)(\d+)$/.exec(p[j + 1]);
        if (next && next[1] === m[1] && Number(next[2]) === Number(cur[2]) + 1) j += 1;
        else break;
      }
    }
    if (j > i) out.push(`${p[i]}-${/^[A-Za-z]+(\d+)$/.exec(p[j])[1]}`);
    else out.push(p[i]);
    i = j + 1;
  }
  return out.join('_');
}

/** Make tags unique, without changing any tag listed in `reserved`. */
export function makeUnique(tags, reserved = []) {
  const used = new Set(reserved);
  return tags.map((t) => {
    let tag = t;
    let n = 2;
    while (used.has(tag)) tag = `${t}_${n++}`;
    used.add(tag);
    return tag;
  });
}

/**
 * Suggested tags for a list of file names (same order).
 * `reserved`: tags already in use that must not be repeated.
 */
export function suggestTags(fileNames, reserved = []) {
  return makeUnique(rawSuggestions(fileNames), reserved);
}

/**
 * Suggestions only for `newNames`, comparing against all files of the project
 * (`allNames`), so the common parts are found across the whole project.
 * Tags in `reserved` (files that already have a tag) are never repeated.
 */
export function suggestTagsForNew(allNames, newNames, reserved = []) {
  const raw = rawSuggestions(allNames);
  const byName = Object.fromEntries(allNames.map((n, i) => [n, raw[i]]));
  return makeUnique(newNames.map((n) => byName[n] || sanitizeTag(stem(n))), reserved);
}

function rawSuggestions(fileNames) {
  const split = fileNames.map(parts);
  let common = new Set();
  if (split.length > 1) {
    common = new Set(split[0].map((x) => x.toLowerCase()));
    for (const p of split.slice(1)) {
      const lower = new Set(p.map((x) => x.toLowerCase()));
      common = new Set([...common].filter((x) => lower.has(x)));
    }
  }
  const raw = split.map((p, i) => {
    const keep = p.filter((x) => !common.has(x.toLowerCase()) || POLARITY.has(x.toLowerCase()));
    const tag = sanitizeTag(compressRuns(keep.join('_')));
    return tag || sanitizeTag(stem(fileNames[i]));
  });
  return raw;
}
