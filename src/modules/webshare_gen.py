import random
import string
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import List, Optional, Dict
import threading


class WebshareGenerator:
    WEBSITE_KEY = "6LeHZ6UUAAAAAKat_YS--O2tj_by3gv3r_l03j9d"
    BASE = "https://proxy.webshare.io/api/v2"
    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
    TIMEOUT = (5, 30)

    DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "icloud.com"]
    ROOTS = ["pixel", "alpha", "drift", "neo", "astro", "zenith", "echo", "nova", "crypt", "orbit",
             "dash", "cloud", "vibe", "frost", "hex", "pulse", "quant", "terra", "lumen", "flux"]
    SUFFIXES = ["tv", "hub", "io", "xd", "on", "lab", "it", "max", "sys", "hq"]

    def __init__(self, cap_key: str, cap_service: str = "capsolver"):
        self.cap_key = cap_key
        self.cap_service = cap_service.lower()
        self.session = self._create_session()

    def _create_session(self):
        s = requests.Session()
        s.headers["User-Agent"] = self.UA
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=Retry(total=2, backoff_factor=0.2)
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        return s

    def _solve_captcha(self) -> str:
        if self.cap_service == "capmonster":
            from capmonster_python import RecaptchaV2Task
            task = RecaptchaV2Task(self.cap_key)
            tid = task.create_task("https://webshare.io", self.WEBSITE_KEY)
            result = task.join_task_result(tid)
            return result["gRecaptchaResponse"]
        elif self.cap_service == "nocaptchaai":
            return self._solve_nocaptchaai()
        else:
            import capsolver
            capsolver.api_key = self.cap_key
            result = capsolver.solve({
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteURL": "https://webshare.io",
                "userAgent": self.UA,
                "websiteKey": self.WEBSITE_KEY
            })
            return result["gRecaptchaResponse"]

    def _solve_nocaptchaai(self) -> str:
        import time
        create_url = "https://api.nocaptchaai.com/createTask"
        result_url = "https://api.nocaptchaai.com/getTaskResult"
        headers = {"Content-Type": "application/json"}

        payload = {
            "clientKey": self.cap_key,
            "task": {
                "type": "RecaptchaV2TaskProxyless",
                "websiteURL": "https://webshare.io",
                "websiteKey": self.WEBSITE_KEY,
                "isInvisible": False
            }
        }
        resp = self.session.post(create_url, json=payload, headers=headers, timeout=self.TIMEOUT)
        data = resp.json()
        if data.get("errorId", 0) != 0:
            err_desc = data.get("errorDescription") or data.get("errorCode") or str(data)
            raise RuntimeError(f"NoCaptchaAI error: {err_desc}")
        task_id = data.get("taskId")
        if not task_id:
            raise RuntimeError(f"NoCaptchaAI: no taskId returned: {data}")

        for _ in range(60):
            time.sleep(3)
            resp = self.session.post(result_url, json={"clientKey": self.cap_key, "taskId": task_id}, headers=headers, timeout=self.TIMEOUT)
            result = resp.json()
            status = result.get("status", "")
            if status == "ready":
                solution = result.get("solution", {})
                token = solution.get("gRecaptchaResponse", "")
                if token:
                    return token
                raise RuntimeError(f"NoCaptchaAI: empty solution: {result}")
            elif status == "processing":
                continue
            else:
                raise RuntimeError(f"NoCaptchaAI unexpected status: {result}")
        raise RuntimeError("NoCaptchaAI: timeout waiting for solution")

    def _random_email(self) -> str:
        base = random.choice(self.ROOTS)
        suf = random.choice(self.SUFFIXES)
        num = str(random.randint(10, 999)) if random.random() < 0.4 else ""
        return f"{base}{suf}{num}@{random.choice(self.DOMAINS)}"

    def _random_password(self) -> str:
        chars = (
            random.choices(string.ascii_lowercase, k=random.randint(4, 6)) +
            random.choices(string.ascii_uppercase, k=random.randint(2, 4)) +
            random.choices(string.digits, k=random.randint(2, 4)) +
            random.choices("!@#$%^&*", k=random.randint(1, 2))
        )
        random.shuffle(chars)
        return "".join(chars)

    def _register(self, captcha_token: str) -> str:
        payload = {
            "email": self._random_email(),
            "password": self._random_password(),
            "tos_accepted": True,
            "recaptcha": captcha_token
        }
        r = self.session.post(f"{self.BASE}/register/", json=payload, timeout=self.TIMEOUT)
        data = r.json()
        token = data.get("token")
        if not token:
            detail = data.get("detail", str(data))
            raise RuntimeError(f"Registration failed: {detail}")
        return token

    def _download_proxies(self, token: str, fmt: str = "ip:port:user:pass", page_size: int = 50) -> List[str]:
        self.session.headers["Authorization"] = f"Token {token}"
        r = self.session.get(
            f"{self.BASE}/proxy/list/?mode=direct&page=1&page_size={page_size}",
            timeout=self.TIMEOUT
        )
        results = r.json().get("results", [])
        if not results:
            raise RuntimeError("No proxies returned from account")

        proxies = []
        for p in results:
            addr = p.get("proxy_address", "")
            port = p.get("port", "")
            user = p.get("username", "")
            pwd = p.get("password", "")

            if fmt == "ip:port":
                proxies.append(f"{addr}:{port}")
            elif fmt in ("ip:port:user:pass", "ip:port:username:password"):
                proxies.append(f"{addr}:{port}:{user}:{pwd}")
            elif fmt in ("user:pass@ip:port", "username:password@ip:port"):
                proxies.append(f"{user}:{pwd}@{addr}:{port}")
            else:
                proxies.append(f"{addr}:{port}:{user}:{pwd}")

        return proxies

    def generate(self, fmt: str = "ip:port:user:pass", count: int = 1) -> Dict:
        all_proxies = []
        errors = []
        accounts_created = 0

        for i in range(count):
            try:
                captcha_token = self._solve_captcha()
                token = self._register(captcha_token)
                accounts_created += 1
                proxies = self._download_proxies(token, fmt)
                all_proxies.extend(proxies)
            except Exception as e:
                errors.append(f"Account {i+1}: {str(e)[:100]}")

        return {
            "status": "success" if all_proxies else "error",
            "proxies": all_proxies,
            "count": len(all_proxies),
            "accounts": accounts_created,
            "errors": errors
        }
