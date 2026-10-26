"""Static token-pair coverage. Does not infer DOM ancestry or certify rendered contrast."""
import json
from pathlib import Path
import re
import subprocess
from itertools import product

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONSUMERS = (ROOT / 'web/src/style.css', ROOT / 'web/src/dash.css')
DEFAULT_BASELINE = ROOT / 'tools/theme_contrast_baseline.json'
REFERENCE_PAIRS = (('ops-reference-ink', 'bg', 4.5), ('ops-reference-border', 'bg', 3.0))
KNOWN_FAIL = dict(name='legacy-ops-reference-border', pair='ops-reference-border/bg',
                  themes=('default', 'crt', 'nostromo'), value='#405c64', expires_with='t189')
BASELINE_FIELDS = ('theme', 'pair', 'foreground_value', 'background_value', 'floor')


def consumer_scope(evidence):
    """Line movement is harmless; changed selectors, files or conditions are not."""
    return sorted({(Path(item['source']).name, item['selector'], tuple(item['context']))
                   for item in evidence})


def apply_baseline(rows, baseline, completed_tasks=()):
    """Defer only design-triaged exact-value failures until their expiry task."""
    if baseline.get('version') != 1 or not re.fullmatch(r'[0-9a-f]{40}', baseline.get('source_head', '')):
        raise ValueError('Baseline requires version 1 and a measured source_head')
    entries = {}
    if not isinstance(baseline.get('entries'), list): raise ValueError('Baseline requires entries')
    for entry in baseline['entries']:
        if (any(field not in entry for field in BASELINE_FIELDS) or
                not re.fullmatch(r't[0-9]+', entry.get('expires_with', '')) or
                not isinstance(entry.get('reason'), str) or not entry['reason'].strip() or
                not isinstance(entry.get('evidence'), list) or not entry['evidence']):
            raise ValueError('Each baseline entry requires exact pair/values/floor, consumer scope, reason and expiry task')
        try: consumer_scope(entry['evidence'])
        except (KeyError, TypeError): raise ValueError('Invalid baseline consumer scope') from None
        key = tuple(entry[field] for field in BASELINE_FIELDS)
        if key in entries: raise ValueError('Duplicate baseline entry: ' + str(key))
        entries[key] = entry
    result = []
    for original in rows:
        row = dict(original)
        entry = entries.get(tuple(row.get(field) for field in BASELINE_FIELDS))
        if entry and row['status'] == 'FAIL' and not row.get('error'):
            expired = entry['expires_with'] in completed_tasks or bool((row.get('known_fail') or {}).get('expired'))
            scope_changed = consumer_scope(entry['evidence']) != consumer_scope(row.get('evidence', []))
            row['baseline'] = dict(entry, expired=expired, scope_changed=scope_changed, source_head=baseline['source_head'])
            if not expired and not scope_changed: row['status'] = 'BASELINE-FAIL'
        result.append(row)
    return result


def parse_consumers(sources):
    result = subprocess.run(['node', str(ROOT / 'web/tools/contrast-consumers.cjs')],
                            input=json.dumps(sources), text=True, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'CSS consumer parser failed')
    return json.loads(result.stdout)


def read_consumers(paths=DEFAULT_CONSUMERS):
    return parse_consumers([dict(source=str(path), css=Path(path).read_text()) for path in paths])


def roles(name):
    # Literal naming convention; names can belong to more than one group.
    return ({'text'} if 'ink' in name or 'fg' in name else set()) | (
            {'border'} if 'border' in name else set()) | (
            {'surface'} if 'surface' in name or name.startswith('bg') else set())


def references(value, tokens, seen=()):
    """Selected var() branches plus alias chains; do not use an inactive fallback."""
    names = set()
    cursor = 0
    while match := re.search(r'var\(\s*--([\w-]+)', value[cursor:]):
        start = cursor + match.start()
        name = match.group(1)
        opening = value.index('(', start)
        depth, end = 1, opening + 1
        while end < len(value) and depth:
            if value[end] == '(': depth += 1
            elif value[end] == ')': depth -= 1
            end += 1
        if depth: raise ValueError('Unclosed var() reference: ' + value)
        interior = value[opening + 1:end - 1]
        fallback = interior.split(',', 1)[1].strip() if ',' in interior else None
        if name in tokens:
            if name in seen: raise ValueError('Cyclic consumer alias: ' + ' -> '.join((*seen, name)))
            names.add(name)
            names.update(references(tokens[name], tokens, (*seen, name)))
        elif fallback is not None:
            names.update(references(fallback, tokens, seen))
        else:
            raise ValueError('Missing consumer token --' + name)
        cursor = end
    return names


def consumer_aliases(rules, theme):
    """Only root/dashboard scopes are shared; rule-local aliases stay rule-local."""
    aliases = {}
    for rule in rules:
        if rule['selector'] not in (':root', '.dash-root', f':root[data-theme="{theme}"]'):
            continue
        declarations = [d for d in rule['declarations'] if d['property'].startswith('--')]
        if declarations and rule['context']:
            raise ValueError('Conditional shared aliases require rendered analysis: ' + rule['selector'])
        for declaration in declarations:
            aliases[declaration['property'][2:]] = declaration['value']
    return aliases


def referenced_pairs(rules, tokens, theme):
    """Join declarations only for identical selectors AND conditional contexts.

    This deliberately does not guess descendant background inheritance, hover/base
    selector relationships, image pixels, or cascade winners across selectors.
    Named reference cases below cover the known inherited Operations surface.
    """
    groups = {}
    for rule in rules:
        selectors = re.findall(r'data-theme\s*=\s*[\"\']?([\w-]+)', rule['selector'])
        if selectors and theme not in selectors: continue
        key = (rule['selector'], tuple(rule['context']))
        group = groups.setdefault(key, dict(declarations={}, evidence=[]))
        group['evidence'].append(dict(source=rule['source'], line=rule['line'],
                                      selector=rule['selector'], context=rule['context']))
        for declaration in rule['declarations']:
            prop = declaration['property']
            previous = group['declarations'].get(prop)
            if not previous or declaration['important'] or not previous['important']:
                group['declarations'][prop] = declaration
    used = {}
    local_tokens = {}
    for group in groups.values():
        declarations = group['declarations']
        local = {prop[2:]: d['value'] for prop, d in declarations.items() if prop.startswith('--')}
        environment = {**tokens, **local}
        foregrounds, backgrounds = set(), set()
        for prop, declaration in declarations.items():
            category = ('background' if prop.startswith('background') else
                        'border' if prop.startswith('border') else
                        'text' if prop in ('color', 'fill', 'stroke', 'text-decoration-color') else None)
            if not category: continue
            names = references(declaration['value'], environment)
            if category == 'background':
                backgrounds.update(n for n in names if 'surface' in roles(n))
            else:
                foregrounds.update(n for n in names if category in roles(n))
        for name in foregrounds | backgrounds:
            if name in local:
                previous = local_tokens.get(name)
                if previous is not None and previous != local[name]:
                    raise ValueError('Conflicting rule-local color alias --' + name)
                if name in tokens and tokens[name] != local[name]:
                    raise ValueError('Rule-local color override requires scoped analysis --' + name)
                local_tokens[name] = local[name]
        for pair in product(foregrounds, backgrounds):
            used.setdefault(pair, []).extend(group['evidence'])
    return used, local_tokens


def measure_consumers(css, consumers, palette_rows, math, expired_known_fails=()):
    rows = list(palette_rows)
    palette_pairs = {(r['foreground'], r['pair'].split('/', 1)[1]) for r in rows}
    for theme, base in math.theme_tokens(css).items():
        tokens = {**base, **consumer_aliases(consumers['rules'], theme)}
        used, local = referenced_pairs(consumers['rules'], tokens, theme)
        tokens.update(local)
        fronts = [name for name in tokens if roles(name) & {'text', 'border'}]
        backs = [name for name in tokens if 'surface' in roles(name)]
        required = {(f, b): floor for f, b, floor in REFERENCE_PAIRS}
        for foreground, background in sorted(set(product(fronts, backs)) | set(required)):
            if (foreground, background) in palette_pairs: continue
            pair = foreground + '/' + background
            referenced = (foreground, background) in used or (foreground, background) in required
            floor = required.get((foreground, background), 4.5 if 'text' in roles(foreground) else 3.0)
            evidence = used.get((foreground, background), [])
            try:
                fv, bv = math.resolve(foreground, tokens), math.resolve(background, tokens)
                bg = math.color(bv); fg = math.foreground_color(fv, bg)
                ratio = math.contrast(fg, bg)
            except ValueError as error:
                rows.append(dict(theme=theme, pair=pair, foreground=foreground, floor=floor,
                                 status='FAIL' if referenced else 'WARN', referenced=referenced,
                                 error=str(error), evidence=evidence, ratio=None, suggestion=None))
                continue
            failed = ratio < floor
            status = ('FAIL' if referenced else 'WARN') if failed else ('MARGINAL' if ratio <= floor + .3 else 'PASS')
            known = (pair == KNOWN_FAIL['pair'] and theme in KNOWN_FAIL['themes'] and fv.lower() == KNOWN_FAIL['value'])
            exception = None
            if known and failed:
                exception = {**KNOWN_FAIL, 'expired': KNOWN_FAIL['expires_with'] in expired_known_fails}
                if not exception['expired']: status = 'KNOWN-FAIL'
            suggestion = math.passing_foreground(fg, bg, floor) if failed and referenced else None
            rows.append(dict(theme=theme, pair=pair, foreground=foreground, floor=floor, ratio=ratio,
                             status=status, referenced=referenced, evidence=evidence,
                             named_case=(foreground, background) in required,
                             foreground_value=fv, background_value=bv, known_fail=exception,
                             suggestion=suggestion, suggestion_ratio=math.contrast(math.color(suggestion), bg) if suggestion else None))
    return rows
