#!/usr/bin/env python3

from curl_cffi import requests as cffi_requests
import requests as stdlib_requests
import re, urllib.parse, hashlib, random, traceback, uuid, json, time, base64, math, io, struct
from collections import deque
from Crypto.Cipher import AES
from Crypto.Util import Counter
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import numpy as np

__version__ = "1.1.0"
CHROME_VERSIONS = [120, 123, 124, 131, 136, 142]
IMPERSONATE_MAP = {
    120: "chrome120", 123: "chrome123", 124: "chrome124",
    131: "chrome131", 136: "chrome136", 142: "chrome142",
}
SCREEN_RESOLUTIONS = [
    "1920x1080", "1366x768", "1536x864", "1440x900", "1280x720",
    "1600x900", "2560x1440", "1920x1200",
]
PLATFORMS = {
    "Windows": {
        "ua":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
        "nav": "Win32",
        "sec": '"Windows"',
    },
    "Linux": {
        "ua":  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
        "nav": "Linux x86_64",
        "sec": '"Linux"',
    },
    "macOS": {
        "ua":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36",
        "nav": "MacIntel",
        "sec": '"macOS"',
    },
}
LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.8",
    "en-US,en;q=0.9,es;q=0.7",
]

# ── GIF DECODER ──────────────────────────────────────────────────────────────

def lzw_decode(data, min_size, pixel_count):
    clear_code = 1 << min_size
    eoi = clear_code + 1
    code_size = min_size + 1
    code_mask = (1 << code_size) - 1
    dict_table = [[i] for i in range(clear_code)] + [[clear_code], [eoi]]
    next_code = eoi + 1
    output = []
    bits = 0
    bit_buf = 0
    data_pos = 0
    prev = None
    while len(output) < pixel_count:
        while bits < code_size and data_pos < len(data):
            bit_buf |= data[data_pos] << bits
            bits += 8
            data_pos += 1
        code = bit_buf & code_mask
        bit_buf >>= code_size
        bits -= code_size
        if code == clear_code:
            dict_table = [[i] for i in range(clear_code)] + [[clear_code], [eoi]]
            next_code = eoi + 1
            code_size = min_size + 1
            code_mask = (1 << code_size) - 1
            prev = None
        elif code == eoi:
            break
        else:
            if code < len(dict_table):
                entry = dict_table[code]
            elif code == next_code and prev:
                entry = prev + [prev[0]]
            else:
                break
            output.extend(entry)
            if prev and next_code < 4096:
                dict_table.append(prev + [entry[0]])
                next_code += 1
                if next_code > code_mask and code_size < 12:
                    code_size += 1
                    code_mask = (1 << code_size) - 1
            prev = entry
    return output[:pixel_count]


def parse_gif(data):
    pos = 6
    cw = data[pos] | (data[pos+1] << 8)
    ch = data[pos+2] | (data[pos+3] << 8)
    packed = data[pos+4]
    has_gct = (packed >> 7) & 1
    gct_size = 3 * (2 ** ((packed & 0x7) + 1))
    pos += 7
    gct = data[pos:pos+gct_size] if has_gct else None
    if has_gct:
        pos += gct_size
    frames = []
    delay = 0
    transparent_index = -1
    while pos < len(data):
        block = data[pos]
        pos += 1
        if block == 0x3B:
            break
        elif block == 0x21:
            label = data[pos]
            pos += 1
            if label == 0xF9:
                pos += 1
                flags = data[pos]
                delay = (data[pos+1] | (data[pos+2] << 8)) * 10
                pos += 2
                transparent_index = data[pos] if (flags & 1) else -1
                pos += 2
            else:
                while True:
                    sz = data[pos]
                    pos += 1
                    if not sz:
                        break
                    pos += sz
        elif block == 0x2C:
            fx = data[pos] | (data[pos+1] << 8)
            fy = data[pos+2] | (data[pos+3] << 8)
            fw = data[pos+4] | (data[pos+5] << 8)
            fh = data[pos+6] | (data[pos+7] << 8)
            ipacked = data[pos+8]
            pos += 9
            has_lct = (ipacked >> 7) & 1
            lct_size = 3 * (2 ** ((ipacked & 0x7) + 1)) if has_lct else 0
            ct = data[pos:pos+lct_size] if has_lct else gct
            if has_lct:
                pos += lct_size
            min_code = data[pos]
            pos += 1
            lzw_data = []
            while True:
                sz = data[pos]
                pos += 1
                if not sz:
                    break
                lzw_data.extend(data[pos:pos+sz])
                pos += sz
            pixels = lzw_decode(lzw_data, min_code, fw * fh)
            patch = np.zeros((fh, fw, 4), dtype=np.uint8)
            for i, ci in enumerate(pixels):
                ci3 = ci * 3
                if ci3 + 2 < len(ct):
                    patch[i // fw, i % fw] = [ct[ci3], ct[ci3+1], ct[ci3+2], 0 if ci == transparent_index else 255]
            frames.append({'x': fx, 'y': fy, 'w': fw, 'h': fh, 'delay': delay, 'patch': patch})
    return {'w': cw, 'h': ch, 'frames': frames}


def composite_frames(gif):
    w, h = gif['w'], gif['h']
    canvas = np.zeros((h, w, 4), dtype=np.uint8)
    composed = []
    for frame in gif['frames']:
        next_canvas = canvas.copy()
        for fy in range(frame['h']):
            for fx in range(frame['w']):
                if frame['patch'][fy, fx, 3] == 0:
                    continue
                cy, cx = frame['y'] + fy, frame['x'] + fx
                if 0 <= cy < h and 0 <= cx < w:
                    next_canvas[cy, cx] = frame['patch'][fy, fx]
        composed.append(next_canvas)
        canvas = next_canvas
    return composed

# ── IMAGE ANALYSIS ───────────────────────────────────────────────────────────

def detect_bg(rgba, w, h):
    C = 12
    samples = []
    for y in range(min(C, h)):
        for x in range(min(C, w)):
            for px, py in [(x, y), (w-1-x, y), (x, h-1-y), (w-1-x, h-1-y)]:
                if 0 <= px < w and 0 <= py < h:
                    samples.append(rgba[py, px, :3])
    samples = np.array(samples)
    return {
        'bgR': int(np.median(samples[:, 0])),
        'bgG': int(np.median(samples[:, 1])),
        'bgB': int(np.median(samples[:, 2])),
    }


def saturation(r, g, b):
    rn, gn, bn = r/255, g/255, b/255
    max_c = max(rn, gn, bn)
    min_c = min(rn, gn, bn)
    l = (max_c + min_c) / 2
    if max_c == min_c:
        return 0
    d = max_c - min_c
    return d / (2 - max_c - min_c if l > 0.5 else max_c + min_c)


def find_blobs(rgba, w, h, bgR, bgG, bgB, thresh=22, min_size=12, min_sat=0):
    visited = np.zeros((h, w), dtype=bool)
    blobs = []
    for y in range(h):
        for x in range(w):
            if visited[y, x]:
                continue
            r, g, b = int(rgba[y, x, 0]), int(rgba[y, x, 1]), int(rgba[y, x, 2])
            if abs(r-bgR) + abs(g-bgG) + abs(b-bgB) <= thresh:
                continue
            queue = deque([(x, y)])
            pixels = []
            visited[y, x] = True
            ri, gi, bi = 0, 0, 0
            while queue:
                cx, cy = queue.popleft()
                pixels.append((cx, cy))
                ri += int(rgba[cy, cx, 0])
                gi += int(rgba[cy, cx, 1])
                bi += int(rgba[cy, cx, 2])
                for nx, ny in [(cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)]:
                    if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx]:
                        nr, ng, nb = int(rgba[ny, nx, 0]), int(rgba[ny, nx, 1]), int(rgba[ny, nx, 2])
                        if abs(nr-bgR) + abs(ng-bgG) + abs(nb-bgB) > thresh:
                            visited[ny, nx] = True
                            queue.append((nx, ny))
            if len(pixels) < min_size:
                continue
            n = len(pixels)
            cx_mean = sum(p[0] for p in pixels) / n
            cy_mean = sum(p[1] for p in pixels) / n
            mr, mg, mb = ri/n, gi/n, bi/n
            sat = saturation(mr, mg, mb)
            if sat < min_sat:
                continue
            blobs.append({'cx': cx_mean, 'cy': cy_mean, 'size': n, 'r': mr, 'g': mg, 'b': mb, 'sat': sat})
    return sorted(blobs, key=lambda b: b['size'], reverse=True)


def detect_sat_threshold(rgba, w, h, bgR, bgG, bgB):
    all_blobs = find_blobs(rgba, w, h, bgR, bgG, bgB, 22, 4, 0)
    if len(all_blobs) < 3:
        return 0
    sats = sorted(b['sat'] for b in all_blobs)
    max_gap, gap_at = 0, 0
    for i in range(1, len(sats)):
        gap = sats[i] - sats[i-1]
        if gap > max_gap:
            max_gap = gap
            gap_at = sats[i-1]
    threshold = (gap_at + max_gap * 0.5) if max_gap > 0.10 else 0
    n_above = sum(1 for s in sats if s > threshold)
    return threshold if (threshold > 0 and n_above >= 3) else 0


def track_blobs(composed, w, h, bgR, bgG, bgB, seeds, thresh=22, min_size=10, max_dist=60, min_sat=0):
    tracks = [[{'cx': b['cx'], 'cy': b['cy'], 'r': b['r'], 'g': b['g'], 'b': b['b'], 'sat': b['sat']}] for b in seeds]
    for fi in range(1, len(composed)):
        frame_blobs = find_blobs(composed[fi], w, h, bgR, bgG, bgB, thresh, min_size, min_sat)
        pairs = []
        for ai, track in enumerate(tracks):
            valid = [p for p in track if p is not None]
            if not valid:
                continue
            last = valid[-1]
            pred_cx, pred_cy = last['cx'], last['cy']
            if len(valid) >= 2:
                prev = valid[-2]
                pred_cx = last['cx'] + (last['cx'] - prev['cx'])
                pred_cy = last['cy'] + (last['cy'] - prev['cy'])
            for bi, fb in enumerate(frame_blobs):
                if math.hypot(fb['cx'] - last['cx'], fb['cy'] - last['cy']) >= max_dist:
                    continue
                sp_pred = math.hypot(fb['cx'] - pred_cx, fb['cy'] - pred_cy)
                cd = math.sqrt((fb['r']-last['r'])**2 + (fb['g']-last['g'])**2 + (fb['b']-last['b'])**2)
                pairs.append({'score': sp_pred + cd * 0.25, 'ai': ai, 'bi': bi, 'fb': fb})
        pairs.sort(key=lambda p: p['score'])
        used_a, used_b, asgn = set(), set(), {}
        for p in pairs:
            if p['ai'] in used_a or p['bi'] in used_b:
                continue
            used_a.add(p['ai'])
            used_b.add(p['bi'])
            asgn[p['ai']] = p['fb']
        for ai in range(len(tracks)):
            tracks[ai].append(asgn.get(ai))
    return tracks

# ── MATH UTILS ───────────────────────────────────────────────────────────────

def fit_circle(pts):
    n = len(pts)
    if n < 4:
        return None
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    u = [[p[0]-mx, p[1]-my] for p in pts]
    suu = sum(ux*ux for ux, uy in u)
    svv = sum(uy*uy for ux, uy in u)
    suv = sum(ux*uy for ux, uy in u)
    suuu = sum(ux**3 for ux, uy in u)
    svvv = sum(uy**3 for ux, uy in u)
    suvv = sum(ux*uy*uy for ux, uy in u)
    svuu = sum(uy*ux*ux for ux, uy in u)
    r1 = 0.5 * (suuu + suvv)
    r2 = 0.5 * (svvv + svuu)
    det = suu * svv - suv * suv
    if abs(det) < 1e-8:
        return None
    uc = (r1 * svv - r2 * suv) / det
    vc = (r2 * suu - r1 * suv) / det
    radius = math.sqrt(uc*uc + vc*vc + (suu + svv) / n)
    if not math.isfinite(radius) or radius < 1 or radius > 3000:
        return None
    return {'cx': uc + mx, 'cy': vc + my, 'r': radius}


def unwrap_angles(angles):
    if not angles:
        return []
    out = [angles[0]]
    for i in range(1, len(angles)):
        d = angles[i] - out[-1]
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        out.append(out[-1] + d)
    return out


def lin_reg(xs, ys):
    n = len(xs)
    if n < 3:
        return {'slope': 0, 'r2': 0}
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x-mx)**2 for x in xs)
    sxy = sum((xs[i]-mx) * (ys[i]-my) for i in range(n))
    syy = sum((y-my)**2 for y in ys)
    if sxx < 1e-12:
        return {'slope': 0, 'r2': 0}
    slope = sxy / sxx
    ss_res = sum((ys[i] - (slope * xs[i] + my - slope * mx))**2 for i in range(n))
    r2 = max(0, 1 - ss_res/syy if syy > 1e-12 else 1)
    return {'slope': slope, 'r2': r2}


def shoelace_dir(pts):
    n = len(pts)
    if n < 4:
        return None
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    pos, neg = 0, 0
    for i in range(1, n):
        ax, ay = pts[i-1][0] - mx, pts[i-1][1] - my
        bx, by = pts[i][0] - mx, pts[i][1] - my
        cross = ax * by - ay * bx
        if cross > 0:
            pos += cross
        else:
            neg -= cross
    total = pos + neg
    if total < 1e-6:
        return None
    return {'dir': 'CCW' if pos > neg else 'CW', 'dominance': max(pos, neg) / total}

# ── SOLVERS ──────────────────────────────────────────────────────────────────

def solve_driftodd(gif, composed):
    w, h = gif['w'], gif['h']
    bg = detect_bg(composed[0], w, h)
    bgR, bgG, bgB = bg['bgR'], bg['bgG'], bg['bgB']
    n_frames = len(composed)
    sat_thresh = detect_sat_threshold(composed[0], w, h, bgR, bgG, bgB)

    seeds = None
    for min_sz in [8, 15, 30, 50, 80]:
        blobs = find_blobs(composed[0], w, h, bgR, bgG, bgB, 22, min_sz, sat_thresh)
        if 3 <= len(blobs) <= 20:
            seeds = blobs[:14]
            break
    if not seeds or len(seeds) < 3:
        for fi in range(1, min(n_frames, 6)):
            for min_sz in [8, 15, 30]:
                blobs = find_blobs(composed[fi], w, h, bgR, bgG, bgB, 22, min_sz, sat_thresh)
                if 3 <= len(blobs) <= 20 and len(blobs) > len(seeds or []):
                    seeds = blobs[:14]
    if not seeds or len(seeds) < 2:
        return {'answer': None, 'reason': 'no seeds'}

    seeds = seeds[:10]
    tracks = track_blobs(composed, w, h, bgR, bgG, bgB, seeds, 22, 8, 60, sat_thresh)

    classified = []
    for ti, track in enumerate(tracks):
        valid = [(i, p) for i, p in enumerate(track) if p is not None]
        if len(valid) < max(4, n_frames * 0.25):
            continue
        pts = [p for _, p in valid]
        xy_pts = [[p['cx'], p['cy']] for p in pts]
        circ = fit_circle(xy_pts)
        mean_cx = sum(p[0] for p in xy_pts) / len(xy_pts)
        mean_cy = sum(p[1] for p in xy_pts) / len(xy_pts)
        orbit_cx = circ['cx'] if circ else mean_cx
        orbit_cy = circ['cy'] if circ else mean_cy
        max_disp = max(math.hypot(p[0]-xy_pts[0][0], p[1]-xy_pts[0][1]) for p in xy_pts)
        if (circ and circ['r'] < 5 or not circ) and max_disp < 8:
            continue
        frame_idxs = [i for i, _ in valid]
        raw_angles = [math.atan2(p['cy']-orbit_cy, p['cx']-orbit_cx) for p in pts]
        unwrapped = unwrap_angles(raw_angles)
        reg = lin_reg(frame_idxs, unwrapped)
        dir_result = None
        confidence = 0
        if abs(reg['slope']) > 0.005 and reg['r2'] > 0.45:
            dir_result = 'CCW' if reg['slope'] > 0 else 'CW'
            confidence = reg['r2']
        else:
            vote = shoelace_dir(xy_pts)
            if vote and vote['dominance'] > 0.75:
                dir_result = vote['dir']
                confidence = vote['dominance'] * 0.5
        if not dir_result:
            continue
        classified.append({
            'ti': ti, 'dir': dir_result, 'confidence': confidence, 'r2': reg['r2'],
            'validFrames': len(valid), 'clickCx': seeds[ti]['cx'], 'clickCy': seeds[ti]['cy']
        })

    if len(classified) < 2:
        return {'answer': None, 'reason': f'only {len(classified)} classified'}

    cw = [c for c in classified if c['dir'] == 'CW']
    ccw = [c for c in classified if c['dir'] == 'CCW']

    if not cw or not ccw:
        present_dir = 'CW' if cw else 'CCW'
        opposite_dir = 'CCW' if present_dir == 'CW' else 'CW'
        in_set = set(c['ti'] for c in classified)
        for ti, track in enumerate(tracks):
            if ti in in_set:
                continue
            valid = [(i, p) for i, p in enumerate(track) if p is not None]
            if len(valid) < 4:
                continue
            xy_pts = [[p['cx'], p['cy']] for _, p in valid]
            max_disp = max(math.hypot(p[0]-xy_pts[0][0], p[1]-xy_pts[0][1]) for p in xy_pts)
            if max_disp < 8:
                continue
            vote = shoelace_dir(xy_pts)
            if not vote or vote['dominance'] < 0.80 or vote['dir'] != opposite_dir:
                continue
            classified.append({'ti': ti, 'dir': opposite_dir, 'confidence': vote['dominance']*0.4,
                                'validFrames': len(valid), 'clickCx': seeds[ti]['cx'], 'clickCy': seeds[ti]['cy']})
        cw = [c for c in classified if c['dir'] == 'CW']
        ccw = [c for c in classified if c['dir'] == 'CCW']

    if not cw or not ccw:
        return {'answer': None, 'reason': 'all tracks same direction after recovery'}

    if len(cw) != len(ccw):
        odd = cw if len(cw) < len(ccw) else ccw
    else:
        cw_conf = sum(c['confidence'] for c in cw)
        ccw_conf = sum(c['confidence'] for c in ccw)
        odd = cw if cw_conf <= ccw_conf else ccw

    if len(odd) > 1:
        odd = [sorted(odd, key=lambda x: x['confidence'], reverse=True)[0]]

    best = odd[0]
    return {'answer': {'cx': best['clickCx'], 'cy': best['clickCy']}, 'confidence': round(best['confidence'], 6)}


def solve_coherence(gif, composed):
    w, h = gif['w'], gif['h']
    bg = detect_bg(composed[0], w, h)
    bgR, bgG, bgB = bg['bgR'], bg['bgG'], bg['bgB']
    cell = max(20, min(35, round(math.sqrt(w*h)/14)))

    attempts = [
        {'THRESH': 18, 'MIN_SIZE': 4, 'MAX_MATCH': 22, 'minDots': 5},
        {'THRESH': 18, 'MIN_SIZE': 3, 'MAX_MATCH': 35, 'minDots': 3},
        {'THRESH': 22, 'MIN_SIZE': 2, 'MAX_MATCH': 50, 'minDots': 2},
        {'THRESH': 26, 'MIN_SIZE': 2, 'MAX_MATCH': 70, 'minDots': 2},
    ]

    all_vecs, dot_frames = None, None
    for attempt in attempts:
        dot_frames_try = []
        for rgba in composed:
            visited = np.zeros((h, w), dtype=bool)
            dots = []
            for y in range(h):
                for x in range(w):
                    if visited[y, x]:
                        continue
                    r, g, b = int(rgba[y, x, 0]), int(rgba[y, x, 1]), int(rgba[y, x, 2])
                    if abs(r-bgR) + abs(g-bgG) + abs(b-bgB) <= attempt['THRESH']:
                        continue
                    queue = deque([(x, y)])
                    pix = []
                    visited[y, x] = True
                    while queue:
                        cx, cy = queue.popleft()
                        pix.append((cx, cy))
                        for nx, ny in [(cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)]:
                            if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx]:
                                nr, ng, nb = int(rgba[ny, nx, 0]), int(rgba[ny, nx, 1]), int(rgba[ny, nx, 2])
                                if abs(nr-bgR) + abs(ng-bgG) + abs(nb-bgB) > attempt['THRESH']:
                                    visited[ny, nx] = True
                                    queue.append((nx, ny))
                    if len(pix) < attempt['MIN_SIZE']:
                        continue
                    dots.append([sum(p[0] for p in pix)/len(pix), sum(p[1] for p in pix)/len(pix)])
            dot_frames_try.append(dots)

        all_vecs_try = []
        for step in [1, 2]:
            weight = 1.0 if step == 1 else 0.6
            match_radius = attempt['MAX_MATCH'] * (1.6 if step == 2 else 1)
            for fi in range(len(dot_frames_try) - step):
                p0, p1 = dot_frames_try[fi], dot_frames_try[fi+step]
                if len(p0) < attempt['minDots'] or len(p1) < attempt['minDots']:
                    continue
                for dx0, dy0 in p0:
                    best_d, best_idx = match_radius, -1
                    for j, (dx1, dy1) in enumerate(p1):
                        d = math.hypot(dx1-dx0, dy1-dy0)
                        if d < best_d:
                            best_d = d
                            best_idx = j
                    if best_idx < 0:
                        continue
                    vx = (p1[best_idx][0] - dx0) / step
                    vy = (p1[best_idx][1] - dy0) / step
                    if math.hypot(vx, vy) < 0.5:
                        continue
                    all_vecs_try.append([dx0, dy0, vx, vy, weight])

        if len(all_vecs_try) >= 20:
            all_vecs = all_vecs_try
            dot_frames = dot_frames_try
            break
        if not all_vecs or len(all_vecs_try) > len(all_vecs):
            all_vecs = all_vecs_try
            dot_frames = dot_frames_try

    if not all_vecs or len(all_vecs) < 20:
        return {'answer': None, 'reason': 'too few vectors'}

    nx, ny = w // cell, h // cell
    cell_vecs = [[[] for _ in range(nx)] for _ in range(ny)]
    for cx2, cy2, vx, vy, wgt in all_vecs:
        bx = min(int(cx2 / cell), nx-1)
        by = min(int(cy2 / cell), ny-1)
        angle = math.atan2(vy, vx)
        speed = math.hypot(vx, vy)
        cell_vecs[by][bx].append([angle, speed, wgt])

    cmap = [[0.0]*nx for _ in range(ny)]
    for by in range(ny):
        for bx in range(nx):
            v = cell_vecs[by][bx]
            if len(v) < 6:
                continue
            tot_w = sum(wgt for _, _, wgt in v)
            mean_spd = sum(sp*wgt for _, sp, wgt in v) / tot_w
            sx = sum(math.sin(a)*wgt for a, _, wgt in v)
            cx3 = sum(math.cos(a)*wgt for a, _, wgt in v)
            cv = 1 - math.sqrt((sx/tot_w)**2 + (cx3/tot_w)**2)
            cmap[by][bx] = mean_spd * (1 - cv)

    gauss = [[1, 2, 1], [2, 4, 2], [1, 2, 1]]
    sm = [[0.0]*nx for _ in range(ny)]
    for by in range(ny):
        for bx in range(nx):
            s, wt = 0.0, 0
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    y2, x2 = by+dy, bx+dx
                    if 0 <= y2 < ny and 0 <= x2 < nx:
                        w2 = gauss[dy+1][dx+1]
                        s += cmap[y2][x2] * w2
                        wt += w2
            border = 0.60 if (by == 0 or by == ny-1 or bx == 0 or bx == nx-1) else 1.0
            sm[by][bx] = (s / wt if wt else 0) * border

    best_val, best_bx, best_by, second_val = -1, 0, 0, -1
    for by in range(ny):
        for bx in range(nx):
            if sm[by][bx] > best_val:
                second_val = best_val
                best_val = sm[by][bx]
                best_bx, best_by = bx, by
            elif sm[by][bx] > second_val:
                second_val = sm[by][bx]

    cell_vecs_win = [[math.atan2(vy, vx), math.hypot(vx, vy), wgt]
                     for cx2, cy2, vx, vy, wgt in all_vecs
                     if int(cx2/cell) == best_bx and int(cy2/cell) == best_by]
    if cell_vecs_win:
        win_angle = math.atan2(
            sum(math.sin(a)*wgt for a, _, wgt in cell_vecs_win),
            sum(math.cos(a)*wgt for a, _, wgt in cell_vecs_win)
        )
    else:
        win_angle = 0

    near_dots = []
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            nbx, nby = best_bx+dx, best_by+dy
            if 0 <= nbx < nx and 0 <= nby < ny and sm[nby][nbx] > 0:
                for ddx, ddy in dot_frames[0]:
                    if int(ddx/cell) == nbx and int(ddy/cell) == nby:
                        near_dots.append([ddx, ddy, sm[nby][nbx]])

    if near_dots:
        weights = []
        for ddx, ddy, cw2 in near_dots:
            my_vec = next((v for cx2, cy2, vx, vy, wgt in all_vecs
                           if math.hypot(cx2-ddx, cy2-ddy) < cell
                           for v in [[math.atan2(vy, vx), math.hypot(vx, vy), wgt]]), None)
            align = 0.5 + 0.5 * math.cos(my_vec[0] - win_angle) if my_vec else 0.5
            weights.append(cw2 * align)
        w_sum = sum(weights) or 1
        click_cx = sum(ddx * w for (ddx, _, _), w in zip(near_dots, weights)) / w_sum
        click_cy = sum(ddy * w for (_, ddy, _), w in zip(near_dots, weights)) / w_sum
    else:
        click_cx = (best_bx + 0.5) * cell
        click_cy = (best_by + 0.5) * cell

    return {'answer': {'cx': click_cx, 'cy': click_cy}, 'confidence': round(min(1, best_val / 5), 6)}

# ── FINGERPRINT & SESSION ────────────────────────────────────────────────────

def _random_fingerprint():
    plat_name = random.choice(list(PLATFORMS))
    plat = PLATFORMS[plat_name]
    v = random.choice(CHROME_VERSIONS)
    res = random.choice(SCREEN_RESOLUTIONS)
    brand_orders = [
        f'"Chromium";v="{v}", "Not:A-Brand";v="24", "Google Chrome";v="{v}"',
        f'"Google Chrome";v="{v}", "Chromium";v="{v}", "Not:A-Brand";v="24"',
    ]
    return {
        "user_agent":         plat["ua"].format(v=v),
        "platform":           plat_name,
        "navigator_platform": plat["nav"],
        "sec_ch_ua":          random.choice(brand_orders),
        "sec_ch_ua_platform": plat["sec"],
        "language":           random.choice(LANGUAGES),
        "resolution":         res,
        "chrome_version":     v,
    }


def _build_session(fp):
    session = cffi_requests.Session(impersonate=IMPERSONATE_MAP[fp["chrome_version"]])
    session.headers.update({
        "User-Agent":                fp["user_agent"],
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language":           fp["language"],
        "Accept-Encoding":           "gzip, deflate, br, zstd",
        "Connection":                "keep-alive",
        "Sec-CH-UA":                 fp["sec_ch_ua"],
        "Sec-CH-UA-Mobile":          "?0",
        "Sec-CH-UA-Platform":        fp["sec_ch_ua_platform"],
        "Sec-Fetch-Dest":            "document",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-Site":            "none",
        "Sec-Fetch-User":            "?1",
        "Upgrade-Insecure-Requests": "1",
    })
    return session


def _get_param(url, param):
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    values = params.get(param, [])
    return values[0] if values else None

# ── CAPTCHA SOLVER ───────────────────────────────────────────────────────────

def solve_captcha():
    """Solve one PlatoRelay GIF CAPTCHA. Returns the signed token or None."""
    for _ in range(37):
        cap_session = None
        try:
            fp = _random_fingerprint()
            cap_session = _build_session(fp)
            cap_session.headers.update({
                "Accept":         "application/json",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "cross-site",
                "Origin":         "https://auth.platorelay.com",
                "Referer":        "https://auth.platorelay.com/",
            })
            cap_session.headers.pop("Upgrade-Insecure-Requests", None)
            cap_session.headers.pop("Sec-Fetch-User", None)

            challenge = cap_session.get("https://captcha.platorelay.com/api/challenge").json()
            chalid = challenge.get("challenge_id")
            challenge_type = challenge.get("type", "")
            img_url = "https://captcha.platorelay.com" + challenge.get("image", "")

            buf = stdlib_requests.get(img_url).content
            gif = parse_gif(bytearray(buf))
            composed = composite_frames(gif)

            if challenge_type == "driftodd":
                result = solve_driftodd(gif, composed)
            elif challenge_type == "coherence":
                result = solve_coherence(gif, composed)
            else:
                result = solve_driftodd(gif, composed)
                if not result.get("answer"):
                    result = solve_coherence(gif, composed)

            if not result.get("answer"):
                continue

            x, y = result["answer"]["cx"], result["answer"]["cy"]
            resp = cap_session.post(
                "https://captcha.platorelay.com/api/answer",
                json={"challenge_id": chalid, "x": x, "y": y}
            ).json()

            if resp.get("success"):
                token = resp.get("token", "")
                print(f"[token] {token}")
                return token
        except Exception:
            pass
        finally:
            if cap_session:
                try:
                    cap_session.close()
                except Exception:
                    pass
    return None

# ── CRYPTO / META ────────────────────────────────────────────────────────────

def generate_stream(ticket: str, screen_width=1920, screen_height=1080) -> str:
    try:
        now = int(time.time() * 1000)
        base_time = now - (random.random() * 4000 + 1500)
        events = []
        is_mobile = random.random() < 0.15
        event_count = random.randint(1, 3) if is_mobile else random.randint(2, 6)
        last_x = random.randint(0, screen_width)
        last_y = random.randint(0, screen_height)
        for i in range(event_count):
            prev_time = events[-1]["data"]["time"] if events else base_time
            if is_mobile:
                event_type = 5 if random.random() < 0.85 else 2
                gap_size = random.random() * 1500 + 300
                length = random.randint(80, 480)
                move_distance = (random.random() * 80 - 40) if random.random() < 0.3 else 0
            else:
                rand = random.random()
                if rand < 0.65:
                    event_type = 5
                    gap_size = random.random() * 800 + 200
                    length = random.randint(100, 1700)
                    move_distance = random.random() * 200 - 100
                elif rand < 0.85:
                    event_type = 2
                    gap_size = random.random() * 1200 + 400
                    length = random.randint(80, 880)
                    move_distance = random.random() * 150 - 75
                else:
                    event_type = 3
                    gap_size = random.random() * 1000 + 350
                    length = random.randint(100, 1000)
                    move_distance = random.random() * 180 - 90
            event_time = prev_time + gap_size
            if is_mobile:
                last_x = max(0, min(screen_width, last_x + move_distance))
                last_y = max(0, min(screen_height, last_y + (random.random() * 60 - 30)))
            else:
                if random.random() < 0.65:
                    last_x = max(0, min(screen_width, last_x + move_distance))
                    last_y = max(0, min(screen_height, last_y + (random.random() * 200 - 100)))
                else:
                    last_x = random.randint(0, screen_width)
                    last_y = random.randint(0, screen_height)
            events.append({"event": event_type, "data": {"time": int(event_time), "length": length, "x": int(last_x), "y": int(last_y)}})
        payload = json.dumps({"events": events})
        key = bytes(ord(c) for c in ticket[1:17])
        iv_bytes = bytes(ord(c) for c in ticket[17:33])
        ctr = Counter.new(128, initial_value=int.from_bytes(iv_bytes, "big"))
        cipher = AES.new(key, AES.MODE_CTR, counter=ctr)
        return cipher.encrypt(payload.encode("utf-8")).hex()
    except Exception:
        return ""


def getMeta(ticket: str, screen_res: str, user_agent: str, nav_platform: str) -> str:
    try:
        if not ticket or len(ticket) < 32:
            return "empty"
        key = bytes(ord(c) for c in ticket[0:16])
        iv_bytes = bytes(ord(c) for c in ticket[16:32])
        screen = screen_res.split("x")
        info = [
            {"name": "screen", "data": {"width": int(screen[0]), "height": int(screen[1]), "availWidth": int(screen[0]), "availHeight": int(screen[1])}},
            {"name": "navigator", "data": {"userAgent": user_agent, "platform": nav_platform}},
            {"name": "performance", "data": int(time.time() * 1000)},
            {"name": "history", "data": random.randint(1, 4)},
            {"name": "webdriver", "data": False},
        ]
        payload = json.dumps({"browserInfo": info}, separators=(",", ":"))
        ctr = Counter.new(128, initial_value=int.from_bytes(iv_bytes, "big"))
        cipher = AES.new(key, AES.MODE_CTR, counter=ctr)
        return cipher.encrypt(payload.encode("utf-8")).hex()
    except Exception:
        return "empty"


def checkKey(ticket, session):
    key = session.get(
        f"https://auth.platorelay.com/api/session/status?ticket={ticket}"
    ).json().get("data", {}).get("key")
    return None if (not key or key == "KEY_NOT_FOUND") else key


def _resolve_service(pref, meta):
    """
    Return the numeric service integer for the step API.

    Mirrors getAvailableService() from the userscript:
      - If pref (int) is given, use it directly as the service bit.
      - Otherwise read meta.activeRevenueProfile.service bitmask and
        return the first set bit in priority order 1 → 2 → 4.
      - Default to 1 if nothing is set.
    """
    if isinstance(pref, int):
        return pref

    # userscript: getAvailableService — first available bit, 1 → 2 → 4
    service_bits = (meta.get("activeRevenueProfile") or {}).get("service", 0) or 0
    if service_bits & 1:
        return 1
    if service_bits & 2:
        return 2
    if service_bits & 4:
        return 4
    return 1


def _get_metadata(ticket, session):
    try:
        j = session.get(
            f"https://auth.platorelay.com/api/session/metadata?ticket={ticket}"
        ).json()
        if j.get("success"):
            return j.get("data") or {}
    except Exception:
        pass
    return None


def _bypass_loot(loot_url):
    try:
        try:
            apikey = stdlib_requests.get(
                "https://trw.lat/api/lvlol/captchaLess", timeout=8
            ).json().get("freeKey", "free")
        except Exception:
            apikey = "free"

        r = stdlib_requests.get(
            f"https://trw.lat/api/bypass?url={urllib.parse.quote(loot_url)}&mode=normal",
            headers={"x-api-key": apikey},
            timeout=30,
        ).json()
        if r.get("success") and r.get("result"):
            return r["result"]
        print(f"[bypass] {json.dumps(r)}")
    except Exception as e:
        print(f"[\u2717] bypass error: {e}")
    return None

# ── MAIN BYPASS ──────────────────────────────────────────────────────────────

def getKey(url, verbose_cb=None, service=None):
    """
    Bypass a PlatoRelay checkpoint link and return the key.

    Parameters
    ----------
    url : str
        Full auth.platorelay.com URL.
    verbose_cb : callable | None
        Optional callback for progress messages, e.g. ``verbose_cb=print``.
    service : int | None
        Preferred service bitmask bit (1, 2, or 4).  When given, that value
        is sent directly.  None = auto-detect from the link's metadata bitmask,
        identical to getAvailableService() in the userscript (first set bit,
        1 → 2 → 4, default 1).

    Returns
    -------
    str
        The key on success, or a string starting with "bypass fail!" on error.
    """
    vcb = verbose_cb or (lambda msg: None)
    vcb("Obtaining DeltaX session...")

    fp = _random_fingerprint()
    session = _build_session(fp)
    session.headers.update({
        "Accept":           "application/json",
        "X-Client-Name":    "platoboost webclient",
        "X-Client-Version": "5.3.2",
        "Sec-Fetch-Dest":   "empty",
        "Sec-Fetch-Mode":   "cors",
        "Sec-Fetch-Site":   "same-origin",
    })
    session.headers.pop("Sec-Fetch-User", None)
    session.headers.pop("Upgrade-Insecure-Requests", None)

    try:
        ticket     = _get_param(url, "d") or _get_param(url, "ticket")
        hash_param = _get_param(url, "hash")
        screen_res = fp["resolution"]
        sw         = int(screen_res.split("x")[0])
        sh         = int(screen_res.split("x")[1])
        user_agent = fp["user_agent"]
        nav_plat   = fp["navigator_platform"]

        session.headers["Referer"] = f"https://auth.platorelay.com/a?d={ticket}"

        # ── Early key check ────────────────────────────────────────────────
        key = checkKey(ticket, session)
        if key:
            vcb("Key already available")
            return key

        vcb("Starting DeltaX bypass...")

        # ── Checkpoint loop ────────────────────────────────────────────────
        for _outer in range(20):
            meta = _get_metadata(ticket, session)
            if meta is None:
                print("[\u2717] metadata fetch failed")
                break

            completed   = meta.get("completed", 0)
            total       = (meta.get("activeRevenueProfile") or {}).get("checkpointCount", 0)
            et_on       = meta.get("enableEventTracker", False)
            svc         = _resolve_service(service, meta)

            vcb(f"[*] {completed}/{total} checkpoints")

            if total > 0 and completed >= total:
                break

            step_url = (
                f"https://auth.platorelay.com/api/session/step"
                f"?ticket={ticket}&service={svc}"
            )
            if hash_param:
                step_url += f"&hash={hash_param}"

            def _stream():
                return generate_stream(ticket, sw, sh) if et_on else ""

            # Try without captcha first
            payload = {
                "captcha":  None,
                "meta":     getMeta(ticket, screen_res, user_agent, nav_plat),
                "stream":   _stream(),
                "resolved": True,
            }
            resp     = session.put(step_url, json=payload).json()
            loot_url = (resp.get("data") or {}).get("url") if resp.get("success") else None

            if not loot_url:
                print(f"[step no-cap] {json.dumps(resp)}")

                vcb("Solving captcha...")
                cap = solve_captcha()
                if not cap:
                    print("[\u2717] captcha returned None, retrying loop")
                    time.sleep(2)
                    continue

                print(f"[token] {cap}")
                payload["captcha"] = cap
                payload["stream"]  = _stream()
                payload["meta"]    = getMeta(ticket, screen_res, user_agent, nav_plat)
                resp     = session.put(step_url, json=payload).json()
                loot_url = (resp.get("data") or {}).get("url") if resp.get("success") else None

            if not loot_url:
                print(f"[step no-url] {json.dumps(resp)}")
                key = checkKey(ticket, session)
                if key:
                    return key
                time.sleep(2)
                continue

            vcb("Bypassing loot link...")
            print(f"[loot] {loot_url}")

            result = _bypass_loot(loot_url)
            if not result:
                print("[\u2717] loot bypass failed, retrying loop")
                time.sleep(2)
                continue

            print(f"[solved] {result}")

            new_ticket = _get_param(result, "d") or _get_param(result, "ticket")
            if new_ticket:
                ticket     = new_ticket
                hash_param = _get_param(result, "hash")
                session.headers["Referer"] = f"https://auth.platorelay.com/a?d={ticket}"

            for _visit in (loot_url, result):
                try:
                    session.get(_visit, timeout=6)
                except Exception:
                    pass

            time.sleep(1)

        # ── Final unlock PUT ───────────────────────────────────────────────
        vcb("Unlocking key...")
        meta     = _get_metadata(ticket, session) or {}
        et_on    = meta.get("enableEventTracker", False)
        svc      = _resolve_service(service, meta)
        step_url = (
            f"https://auth.platorelay.com/api/session/step"
            f"?ticket={ticket}&service={svc}"
        )
        if hash_param:
            step_url += f"&hash={hash_param}"

        unlock_resp = session.put(step_url, json={
            "captcha":  None,
            "meta":     getMeta(ticket, screen_res, user_agent, nav_plat),
            "stream":   generate_stream(ticket, sw, sh) if et_on else "",
            "resolved": True,
        }).json()
        print(f"[unlock] {json.dumps(unlock_resp)}")

        time.sleep(1.5)

        vcb("Fetching key...")
        final_meta = _get_metadata(ticket, session) or {}
        mk = final_meta.get("key")
        if mk and mk != "KEY_NOT_FOUND":
            return mk

        key = checkKey(ticket, session)
        if key:
            return key

        return "bypass fail!"

    except Exception:
        print(f"[\u2717] {traceback.format_exc()}")
        return "bypass fail!"
    finally:
        try:
            session.close()
        except Exception:
            pass


def get_token():
    """Solve one PlatoRelay GIF CAPTCHA and return the raw token string (or None)."""
    return solve_captcha()


__all__ = ["getKey", "get_token"]


if __name__ == "__main__":
    url = input("URL: ").strip()
    result = getKey(url, verbose_cb=print)
    if result and not result.startswith("bypass fail"):
        print(f"\n[\u2713] {result}")
    else:
        print(f"\n[\u2717] {result}")
