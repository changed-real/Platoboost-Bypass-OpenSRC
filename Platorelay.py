#!/usr/bin/env python3
# made by https://rip.linkvertise.lol -> https://trw.lat/ds
# warning : this code works fine for some links / min but for mass solving its blocked by platoboost system with a really good message "get a job"
# you can make it better, idk how plato is detecting it tbh (or if its detected or my proxies are detected)
# maybe when i tried the issues was my proxies getting detected, maybe works for mass solvig, maybe not

# Thanks to the bbg Verity for the help (https://discord.com/user/1517355254117568595) <@1517355254117568595>
# sorry for my bad english and lack of comments, bing.ai is retarded and i don't want to waste my time explaining this code, if you want to understand it, read it and understand it yourself

from curl_cffi import requests as cffi_requests
import requests as stdlib_requests
import re, urllib.parse, hashlib, random, traceback, uuid, json, time, base64, math 

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from Crypto.Cipher import AES
from Crypto.Util import Counter


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
        "user_agent":        plat["ua"].format(v=v),
        "platform":          plat_name,
        "navigator_platform": plat["nav"],
        "sec_ch_ua":         random.choice(brand_orders),
        "sec_ch_ua_platform": plat["sec"],
        "language":          random.choice(LANGUAGES),
        "resolution":        res,
        "chrome_version":    v,
    }


def _build_session(fp):
    impersonate = IMPERSONATE_MAP[fp["chrome_version"]]
    session = cffi_requests.Session(impersonate=impersonate)

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


def encrypt_ctr(plain: str, key: bytes, iv: bytes) -> str:
    cipher = Cipher(
        algorithms.AES(key),
        modes.CTR(iv),
        backend=default_backend()
    )
    encryptor = cipher.encryptor()
    ct = encryptor.update(plain.encode('utf-8')) + encryptor.finalize()
    return ct.hex()


def is_mobile_device():
    return random.random() < 0.15


def generate_stream(ticket: str, screen_width=1920, screen_height=1080) -> str:
    try:
        now = int(time.time() * 1000)
        base_time = now - (random.random() * 4000 + 1500)
        events = []
        is_mobile = is_mobile_device()
        
        event_count = random.randint(1, 3) if is_mobile else random.randint(2, 6)
        last_x = random.randint(0, screen_width)
        last_y = random.randint(0, screen_height)
        
        for i in range(event_count):
            prev_time = events[-1]["data"]["time"] if events else base_time
            
            if is_mobile:
                event_type = 5 if random.random() < 0.85 else 2
                gap_size = random.random() * 1500 + 300
                length = random.randint(80, 480)
                touch_drift = random.random() < 0.3
                move_distance = (random.random() * 80 - 40) if touch_drift else 0
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
                drift = random.random() < 0.65
                if drift:
                    last_x = max(0, min(screen_width, last_x + move_distance))
                    last_y = max(0, min(screen_height, last_y + (random.random() * 200 - 100)))
                else:
                    last_x = random.randint(0, screen_width)
                    last_y = random.randint(0, screen_height)
            
            events.append({
                "event": event_type,
                "data": {
                    "time": int(event_time),
                    "length": length,
                    "x": int(last_x),
                    "y": int(last_y)
                }
            })
        
        payload = json.dumps({"events": events})
        
        key = bytes(ord(c) for c in ticket[1:17])
        iv_bytes = bytes(ord(c) for c in ticket[17:33])
        ctr = Counter.new(128, initial_value=int.from_bytes(iv_bytes, "big"))
        cipher = AES.new(key, AES.MODE_CTR, counter=ctr)
        return cipher.encrypt(payload.encode("utf-8")).hex()
    except Exception:
        return ""


def solve_captcha():
    for _ in range(37):
        cap_session = None
        try:
            fp = _random_fingerprint()
            cap_session = _build_session(fp)

            cap_session.headers.update({
                "Accept": "application/json",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "cross-site",
                "Origin": "https://auth.platorelay.com",
                "Referer": "https://auth.platorelay.com/",
            })
            cap_session.headers.pop("Upgrade-Insecure-Requests", None)
            cap_session.headers.pop("Sec-Fetch-User", None)

            orchesta = cap_session.get("https://captcha.platorelay.com/api/challenge").json()
            chalid = orchesta.get("challenge_id")

            if random.randint(1, 2) == 1:
                x, y = 285.8291457286432, 88.97690559924033
            else:
                x, y = 209.84924623115577, 152.5210684836765

            dead = cap_session.post(
                "https://captcha.platorelay.com/api/answer",
                json={"challenge_id": chalid, "x": x, "y": y},
            ).json()

            if dead.get("success", False):
                print(f"[✓] Captcha solved")
                return dead.get("token")
        except Exception:
            pass
        finally:
            if cap_session:
                try:
                    cap_session.close()
                except Exception:
                    pass

    return None


def checkKey(ticket, session):
    return session.get(
        f"https://auth.platorelay.com/api/session/status?ticket={ticket}"
    ).json().get("data", {}).get("key")


def get_available_service(meta):
    if not meta or not meta.get("activeRevenueProfile"):
        return 2
    service_bits = meta.get("activeRevenueProfile", {}).get("service", 0)
    if (service_bits & 1) != 0:
        return 1
    if (service_bits & 2) != 0:
        return 2
    if (service_bits & 4) != 0:
        return 4
    return 2


def getMeta(ticket: str, screen_res: str, user_agent: str, nav_platform: str) -> str:
    try:
        if not ticket or len(ticket) < 32:
            return "empty"

        key = bytes(ord(c) for c in ticket[0:16])
        iv_bytes = bytes(ord(c) for c in ticket[16:32])
        
        screen = screen_res.split("x")
        
        info = [
            {
                "name": "screen",
                "data": {
                    "width": int(screen[0]),
                    "height": int(screen[1]),
                    "availWidth": int(screen[0]),
                    "availHeight": int(screen[1]),
                }
            },
            {
                "name": "navigator",
                "data": {
                    "userAgent": user_agent,
                    "platform": nav_platform,
                }
            },
            {
                "name": "performance",
                "data": int(time.time() * 1000)
            },
            {
                "name": "history",
                "data": random.randint(1, 4)
            },
            {
                "name": "webdriver",
                "data": False
            },
        ]

        payload = json.dumps({"browserInfo": info}, separators=(",", ":"))
        
        ctr = Counter.new(128, initial_value=int.from_bytes(iv_bytes, "big"))
        cipher = AES.new(key, AES.MODE_CTR, counter=ctr)
        return cipher.encrypt(payload.encode("utf-8")).hex()
    except Exception:
        return "empty"


def getKey(url, verbose_cb=None):
    vcb = verbose_cb or (lambda msg: None)
    vcb("Obtaining DeltaX session...")

    fp = _random_fingerprint()
    session = _build_session(fp)

    session.headers.update({
        "Accept":            "application/json",
        "X-Client-Name":     "platoboost webclient",
        "X-Client-Version":  "5.3.2",
        "Sec-Fetch-Dest":    "empty",
        "Sec-Fetch-Mode":    "cors",
        "Sec-Fetch-Site":    "same-origin",
    })
    session.headers.pop("Sec-Fetch-User", None)
    session.headers.pop("Upgrade-Insecure-Requests", None)

    try:
        ticket = _get_param(url, "d")
        hash_param = _get_param(url, "hash")

        session.headers["Referer"] = f"https://auth.platorelay.com/{ticket}/"

        if checkKey(ticket, session) != "KEY_NOT_FOUND":
            vcb("Key already available")
            return checkKey(ticket, session)

        vcb("Starting DeltaX bypass...")

        resolved = True
        completed = 0
        total_checkpoints = 0
        current_meta = None
        
        screen_res = fp["resolution"]
        user_agent = fp["user_agent"]
        nav_platform = fp["navigator_platform"]

        while True:
            try:
                meta_resp = session.get(f"https://auth.platorelay.com/api/session/metadata?ticket={ticket}").json()
                if meta_resp.get("data"):
                    current_meta = meta_resp.get("data", {})
                    completed = current_meta.get("completed", 0)
                    total_checkpoints = current_meta.get("activeRevenueProfile", {}).get("checkpointCount", 0)
                    print(f"[INFO] Progress: {completed}/{total_checkpoints}")
            except:
                pass

            if total_checkpoints > 0 and completed >= total_checkpoints:
                print("[✓] All checkpoints done")
                break

            time.sleep(2)

            meta = getMeta(ticket, screen_res, user_agent, nav_platform)
            stream = generate_stream(ticket, int(screen_res.split("x")[0]), int(screen_res.split("x")[1]))
            
            service = get_available_service(current_meta)

            for i in range(3):
                vcb(f"Step {i + 1}/3...")
                print(f"[*] Step {i + 1}/3 (checkpoint {completed + 1}, service={service})")

                payload = {
                    "captcha": None,
                    "meta": meta,
                    "stream": stream,
                    "resolved": resolved,
                }

                step_url = f"https://auth.platorelay.com/api/session/step?ticket={ticket}&service={service}"
                if hash_param:
                    step_url += f"&hash={hash_param}"

                stepsis = session.put(step_url, json=payload).json()

                if stepsis.get("data", {}).get("url"):
                    print("[✓] Got loot URL")
                    break

                vcb("Solving captcha...")
                print("[*] Solving captcha...")
                cap = solve_captcha()

                if not cap:
                    print("[✗] Captcha failed")
                    continue

                payload["captcha"] = cap
                payload["stream"] = generate_stream(ticket, int(screen_res.split("x")[0]), int(screen_res.split("x")[1]))

                stepsis = session.put(step_url, json=payload).json()
                if "please complete" not in str(stepsis):
                    print("[✓] Step ok")
                    break
            else:
                return "bypass fail! captcha"

            vcb("Got loot link, bypassing...")
            print("[*] Bypassing loot link...")
            loot_url = stepsis.get("data", {}).get("url")

            if not loot_url:
                print("[✗] No loot URL")
                continue

            try:
                with stdlib_requests.get("https://trw.lat/api/lvlol/captchaLess") as apikey_resp:
                    apikey = apikey_resp.json()["freeKey"]
            except:
                apikey = "free"

            result = None
            try:
                with stdlib_requests.get(
                    f"https://trw.lat/api/bypass?url={urllib.parse.quote(loot_url)}&mode=stream&verbose=true",
                    headers={"x-api-key": apikey},
                    stream=True
                ) as r:
                    for line in r.iter_lines():
                        if not line:
                            continue
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            line = line[6:]
                        data = json.loads(line)
                        if data.get("status") == "success":
                            result = data["result"]
                            break
            except Exception as e:
                print(f"[✗] Bypass failed: {e}")

            if not result:
                print("[✗] Loot bypass failed")
                continue

            ticket = _get_param(result, "d")
            hash_param = _get_param(result, "hash")

            session.headers["Referer"] = f"https://auth.platorelay.com/{ticket}/"

            if checkKey(ticket, session) != "KEY_NOT_FOUND":
                print("[✓] Key from loot")
                return checkKey(ticket, session)

            session.get(f"https://auth.platorelay.com/api/session/status?ticket={ticket}").close()
            session.get(f"https://auth.platorelay.com/api/session/metadata?ticket={ticket}").close()

            meta = getMeta(ticket, screen_res, user_agent, nav_platform)
            time.sleep(2)

            payload = {
                "captcha": None,
                "meta": meta,
                "stream": generate_stream(ticket, int(screen_res.split("x")[0]), int(screen_res.split("x")[1])),
                "resolved": resolved,
            }

            step_url = f"https://auth.platorelay.com/api/session/step?ticket={ticket}&service={service}"
            if hash_param:
                step_url += f"&hash={hash_param}"

            session.put(step_url, json=payload).json()

            if checkKey(ticket, session) != "KEY_NOT_FOUND":
                print("[✓] Got key")
                return checkKey(ticket, session)

            print("[*] Next checkpoint...")

        final_key = checkKey(ticket, session)
        if final_key and final_key != "KEY_NOT_FOUND":
            print(f"[✓✓✓] Key: {final_key[:20]}...")
            return final_key

        return "bypass fail!"

    except Exception:
        print(f"[✗] Error: {traceback.format_exc()}")
        return "bypass fail!"
    finally:
        try:
            session.close()
        except Exception:
            pass


if __name__ == "__main__":
    url = input("URL: ").strip()
    result = getKey(url, verbose_cb=print)
    
    if result and not result.startswith("bypass fail"):
        print(f"\n[✓✓✓] {result}")
    else:
        print(f"\n[✗✗✗] {result}")