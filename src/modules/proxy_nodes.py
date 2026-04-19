import json
import time
import threading
import requests
import secrets
import string
from datetime import datetime
from modules.database import _execute_with_retry, get_connection_with_retry


def _gen_api_key():
    return 'vpn_' + ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))


def add_node(host, api_port=8899, api_key='', country='', label='',
             max_bandwidth_gb=0, protocols='HTTP,SOCKS5', proxy_ports=None):
    if not api_key:
        api_key = _gen_api_key()
    if proxy_ports is None:
        proxy_ports = json.dumps({"http": 8080, "socks5": 1080})
    elif isinstance(proxy_ports, dict):
        proxy_ports = json.dumps(proxy_ports)
    return _execute_with_retry("""
        INSERT INTO proxy_nodes (host, api_port, api_key, country, label, max_bandwidth_gb,
                                  protocols, proxy_ports, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'offline')
        RETURNING id
    """, (host, api_port, api_key, country, label, max_bandwidth_gb, protocols, proxy_ports),
        fetch_one=True)


def update_node(node_id, **kwargs):
    updates = []
    params = []
    for key in ['host', 'api_port', 'api_key', 'country', 'label',
                'max_bandwidth_gb', 'protocols', 'proxy_ports', 'active']:
        if key in kwargs:
            updates.append(f"{key} = %s")
            val = kwargs[key]
            if key == 'proxy_ports' and isinstance(val, dict):
                val = json.dumps(val)
            params.append(val)
    if not updates:
        return False
    params.append(node_id)
    return _execute_with_retry(
        f"UPDATE proxy_nodes SET {', '.join(updates)} WHERE id = %s",
        params, return_rowcount=True
    )


def delete_node(node_id):
    return _execute_with_retry(
        "DELETE FROM proxy_nodes WHERE id = %s", (node_id,), return_rowcount=True
    )


def get_nodes(active_only=True):
    cond = "WHERE active = TRUE" if active_only else ""
    return _execute_with_retry(
        f"SELECT * FROM proxy_nodes {cond} ORDER BY id", fetch=True
    ) or []


def get_node(node_id):
    return _execute_with_retry(
        "SELECT * FROM proxy_nodes WHERE id = %s", (node_id,), fetch_one=True
    )


def get_node_proxy_ports(node):
    try:
        return json.loads(node.get('proxy_ports', '{}'))
    except (json.JSONDecodeError, TypeError):
        return {"http": 8080, "socks5": 1080}


def _api_call(node, endpoint, method='GET', data=None, timeout=10):
    scheme = 'https' if node.get('use_ssl') else 'http'
    url = f"{scheme}://{node['host']}:{node['api_port']}{endpoint}"
    headers = {'X-API-Key': node['api_key'], 'Content-Type': 'application/json'}
    verify_ssl = not node.get('self_signed', False)
    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, timeout=timeout, verify=verify_ssl)
        else:
            resp = requests.post(url, headers=headers, json=data or {}, timeout=timeout, verify=verify_ssl)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def ping_node(node):
    result = _api_call(node, '/api/health')
    if result and result.get('status') == 'ok':
        _execute_with_retry("""
            UPDATE proxy_nodes SET status = 'online', last_seen = NOW(),
                connected_users = %s, used_bandwidth_gb = %s
            WHERE id = %s
        """, (
            result.get('connected_users', 0),
            result.get('used_bandwidth_gb', 0),
            node['id']
        ))
        return True
    else:
        _execute_with_retry(
            "UPDATE proxy_nodes SET status = 'offline' WHERE id = %s",
            (node['id'],)
        )
        return False


def push_credentials(node, credentials_list):
    return _api_call(node, '/api/credentials', method='POST', data={
        'credentials': credentials_list
    })


def pull_bandwidth(node):
    result = _api_call(node, '/api/bandwidth')
    if result and 'users' in result:
        for username, bw_bytes in result['users'].items():
            bw_gb = bw_bytes / (1024 ** 3)
            _execute_with_retry("""
                UPDATE proxy_purchases SET bandwidth_used_gb = %s
                WHERE proxy_user = %s AND status = 'active' AND node_id = %s
            """, (bw_gb, username, node['id']))
        return result
    return None


def sync_node_credentials(node):
    purchases = _execute_with_retry("""
        SELECT proxy_user, proxy_pass, bandwidth_gb FROM proxy_purchases
        WHERE node_id = %s AND status = 'active'
    """, (node['id'],), fetch=True) or []

    creds = []
    for p in purchases:
        creds.append({
            'username': p['proxy_user'],
            'password': p['proxy_pass'],
            'bandwidth_limit_gb': float(p.get('bandwidth_gb', 0))
        })

    return push_credentials(node, creds)


def find_available_node(proxy_type='HTTP', country='', bw_gb=0):
    conditions = ["active = TRUE", "status = 'online'"]
    params = []

    if proxy_type:
        conditions.append("UPPER(protocols) LIKE %s")
        params.append(f"%{proxy_type.upper()}%")

    if country:
        conditions.append("LOWER(country) = LOWER(%s)")
        params.append(country)

    if bw_gb > 0:
        conditions.append("(max_bandwidth_gb <= 0 OR (max_bandwidth_gb - COALESCE(used_bandwidth_gb, 0)) >= %s)")
        params.append(bw_gb)

    where = " AND ".join(conditions)
    return _execute_with_retry(
        f"SELECT * FROM proxy_nodes WHERE {where} ORDER BY RANDOM() LIMIT 1 FOR UPDATE",
        params, fetch_one=True
    )


_poller_running = False


def _poller_loop(interval_seconds=60):
    global _poller_running
    _poller_running = True
    while _poller_running:
        try:
            nodes = get_nodes(active_only=True)
            for node in nodes:
                try:
                    online = ping_node(node)
                    if online:
                        pull_bandwidth(node)
                except Exception as e:
                    print(f"[NodePoller] Error polling node {node.get('id')}: {e}")
        except Exception as e:
            print(f"[NodePoller] Loop error: {e}")

        for _ in range(interval_seconds):
            if not _poller_running:
                break
            time.sleep(1)


def start_node_poller(interval_seconds=60):
    global _poller_running
    if _poller_running:
        return False
    t = threading.Thread(target=_poller_loop, args=(interval_seconds,), daemon=True)
    t.start()
    print(f"[NodePoller] Background thread started (interval: {interval_seconds}s)")
    return True


def stop_node_poller():
    global _poller_running
    _poller_running = False


def generate_deploy_script(node):
    api_key = node.get('api_key', '')
    ports = get_node_proxy_ports(node)
    http_port = ports.get('http', 8080)
    socks5_port = ports.get('socks5', 1080)
    api_port = node.get('api_port', 8899)

    return f'''#!/usr/bin/env python3
"""
Onichan Proxy Daemon - Deploy on your VPS
Run: python3 proxy_daemon.py

Requirements: pip install aiohttp aiosocks
"""
import asyncio
import json
import os
import sys
import time
import hashlib
import struct
import socket
import signal
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import ssl

API_KEY = "{api_key}"
API_PORT = {api_port}
HTTP_PROXY_PORT = {http_port}
SOCKS5_PROXY_PORT = {socks5_port}
CREDS_FILE = "credentials.json"
BW_FILE = "bandwidth.json"

credentials = {{}}
bandwidth = {{}}
connected_users = set()

def load_credentials():
    global credentials
    if os.path.exists(CREDS_FILE):
        with open(CREDS_FILE) as f:
            credentials = json.load(f)
    return credentials

def save_credentials():
    with open(CREDS_FILE, 'w') as f:
        json.dump(credentials, f, indent=2)

def load_bandwidth():
    global bandwidth
    if os.path.exists(BW_FILE):
        with open(BW_FILE) as f:
            bandwidth = json.load(f)
    return bandwidth

def save_bandwidth():
    with open(BW_FILE, 'w') as f:
        json.dump(bandwidth, f)

def track_bandwidth(username, bytes_count):
    if username not in bandwidth:
        bandwidth[username] = 0
    bandwidth[username] += bytes_count

def check_auth(username, password):
    if username in credentials:
        return credentials[username].get('password') == password
    return False

def check_bandwidth_limit(username):
    if username not in credentials:
        return False
    limit_gb = credentials[username].get('bandwidth_limit_gb', 0)
    if limit_gb <= 0:
        return True
    used_bytes = bandwidth.get(username, 0)
    used_gb = used_bytes / (1024 ** 3)
    return used_gb < limit_gb


async def handle_http_proxy(reader, writer):
    username = None
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=30)
        if not request_line:
            writer.close()
            return
        request_str = request_line.decode('utf-8', errors='ignore').strip()
        headers = {{}}
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            if line == b'\\r\\n' or line == b'\\n' or not line:
                break
            try:
                key, val = line.decode('utf-8', errors='ignore').strip().split(':', 1)
                headers[key.strip().lower()] = val.strip()
            except ValueError:
                continue

        import base64
        auth_header = headers.get('proxy-authorization', '')
        if not auth_header.startswith('Basic '):
            writer.write(b'HTTP/1.1 407 Proxy Authentication Required\\r\\n')
            writer.write(b'Proxy-Authenticate: Basic realm="Onichan Proxy"\\r\\n')
            writer.write(b'\\r\\n')
            await writer.drain()
            writer.close()
            return
        try:
            decoded = base64.b64decode(auth_header[6:]).decode('utf-8')
            username, password = decoded.split(':', 1)
        except Exception:
            writer.write(b'HTTP/1.1 407 Proxy Authentication Required\\r\\n\\r\\n')
            await writer.drain()
            writer.close()
            return

        if not check_auth(username, password):
            writer.write(b'HTTP/1.1 403 Forbidden\\r\\n\\r\\n')
            await writer.drain()
            writer.close()
            return

        if not check_bandwidth_limit(username):
            writer.write(b'HTTP/1.1 403 Bandwidth Exceeded\\r\\n\\r\\n')
            await writer.drain()
            writer.close()
            return

        connected_users.add(username)

        if request_str.upper().startswith('CONNECT '):
            target = request_str.split(' ')[1]
            host, port = target.rsplit(':', 1)
            port = int(port)
            try:
                remote_reader, remote_writer = await asyncio.open_connection(host, port)
                writer.write(b'HTTP/1.1 200 Connection Established\\r\\n\\r\\n')
                await writer.drain()
                await _pipe(reader, writer, remote_reader, remote_writer, username)
            except Exception:
                writer.write(b'HTTP/1.1 502 Bad Gateway\\r\\n\\r\\n')
                await writer.drain()
        else:
            parts = request_str.split(' ')
            if len(parts) >= 3:
                method, url, version = parts[0], parts[1], parts[2]
                from urllib.parse import urlparse
                parsed = urlparse(url)
                host = parsed.hostname
                port = parsed.port or 80
                path = parsed.path or '/'
                if parsed.query:
                    path += '?' + parsed.query
                try:
                    remote_reader, remote_writer = await asyncio.open_connection(host, port)
                    fwd_headers = {{k: v for k, v in headers.items() if not k.startswith('proxy-')}}
                    fwd_headers['host'] = host
                    req = f"{{method}} {{path}} {{version}}\\r\\n"
                    for k, v in fwd_headers.items():
                        req += f"{{k}}: {{v}}\\r\\n"
                    req += "\\r\\n"
                    remote_writer.write(req.encode())
                    await remote_writer.drain()
                    await _pipe(reader, writer, remote_reader, remote_writer, username)
                except Exception:
                    writer.write(b'HTTP/1.1 502 Bad Gateway\\r\\n\\r\\n')
                    await writer.drain()

    except Exception:
        pass
    finally:
        if username:
            connected_users.discard(username)
        try:
            writer.close()
        except:
            pass


async def handle_socks5(reader, writer):
    username = None
    try:
        header = await asyncio.wait_for(reader.readexactly(2), timeout=30)
        ver, nmethods = struct.unpack('!BB', header)
        if ver != 5:
            writer.close()
            return
        methods = await reader.readexactly(nmethods)
        writer.write(struct.pack('!BB', 5, 2))
        await writer.drain()

        auth_ver = await reader.readexactly(1)
        ulen = struct.unpack('!B', await reader.readexactly(1))[0]
        uname = (await reader.readexactly(ulen)).decode('utf-8', errors='ignore')
        plen = struct.unpack('!B', await reader.readexactly(1))[0]
        passwd = (await reader.readexactly(plen)).decode('utf-8', errors='ignore')

        if not check_auth(uname, passwd) or not check_bandwidth_limit(uname):
            writer.write(struct.pack('!BB', 1, 1))
            await writer.drain()
            writer.close()
            return

        username = uname
        connected_users.add(username)
        writer.write(struct.pack('!BB', 1, 0))
        await writer.drain()

        req_header = await reader.readexactly(4)
        ver, cmd, rsv, atyp = struct.unpack('!BBBB', req_header)
        if cmd != 1:
            writer.write(struct.pack('!BBBBIH', 5, 7, 0, 1, 0, 0))
            await writer.drain()
            writer.close()
            return

        if atyp == 1:
            raw_addr = await reader.readexactly(4)
            dest_addr = socket.inet_ntoa(raw_addr)
        elif atyp == 3:
            addr_len = struct.unpack('!B', await reader.readexactly(1))[0]
            dest_addr = (await reader.readexactly(addr_len)).decode('utf-8', errors='ignore')
        elif atyp == 4:
            raw_addr = await reader.readexactly(16)
            dest_addr = socket.inet_ntop(socket.AF_INET6, raw_addr)
        else:
            writer.close()
            return

        dest_port = struct.unpack('!H', await reader.readexactly(2))[0]

        try:
            remote_reader, remote_writer = await asyncio.open_connection(dest_addr, dest_port)
            bind_addr = remote_writer.get_extra_info('sockname')
            reply = struct.pack('!BBBB', 5, 0, 0, 1)
            reply += socket.inet_aton(bind_addr[0])
            reply += struct.pack('!H', bind_addr[1])
            writer.write(reply)
            await writer.drain()
            await _pipe(reader, writer, remote_reader, remote_writer, username)
        except Exception:
            writer.write(struct.pack('!BBBBIH', 5, 5, 0, 1, 0, 0))
            await writer.drain()

    except Exception:
        pass
    finally:
        if username:
            connected_users.discard(username)
        try:
            writer.close()
        except:
            pass


async def _pipe(client_reader, client_writer, remote_reader, remote_writer, username):
    async def forward(src, dst, track_user):
        try:
            while True:
                data = await asyncio.wait_for(src.read(8192), timeout=300)
                if not data:
                    break
                dst.write(data)
                await dst.drain()
                if track_user:
                    track_bandwidth(track_user, len(data))
        except Exception:
            pass
        finally:
            try:
                dst.close()
            except:
                pass

    await asyncio.gather(
        forward(client_reader, remote_writer, username),
        forward(remote_reader, client_writer, username)
    )


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _check_auth(self):
        key = self.headers.get('X-API-Key', '')
        if key != API_KEY:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'{{"error":"unauthorized"}}')
            return False
        return True

    def do_GET(self):
        if not self._check_auth():
            return
        if self.path == '/api/health':
            total_bw = sum(bandwidth.values()) / (1024 ** 3)
            resp = json.dumps({{
                'status': 'ok',
                'connected_users': len(connected_users),
                'used_bandwidth_gb': round(total_bw, 2),
                'total_credentials': len(credentials),
                'uptime': int(time.time() - start_time)
            }})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(resp.encode())
        elif self.path == '/api/bandwidth':
            resp = json.dumps({{'users': bandwidth}})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(resp.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self._check_auth():
            return
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {{}}

        if self.path == '/api/credentials':
            global credentials
            creds = body.get('credentials', [])
            credentials = {{}}
            for c in creds:
                credentials[c['username']] = {{
                    'password': c['password'],
                    'bandwidth_limit_gb': c.get('bandwidth_limit_gb', 0)
                }}
            save_credentials()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({{'status': 'ok', 'count': len(credentials)}}).encode())
        else:
            self.send_response(404)
            self.end_headers()


start_time = time.time()

def run_api_server():
    server = HTTPServer(('0.0.0.0', API_PORT), APIHandler)
    print(f"[API] Listening on port {{API_PORT}}")
    server.serve_forever()

async def main():
    load_credentials()
    load_bandwidth()

    bw_save_task = asyncio.create_task(periodic_bw_save())

    http_server = await asyncio.start_server(handle_http_proxy, '0.0.0.0', HTTP_PROXY_PORT)
    print(f"[HTTP] Proxy listening on port {{HTTP_PROXY_PORT}}")

    socks5_server = await asyncio.start_server(handle_socks5, '0.0.0.0', SOCKS5_PROXY_PORT)
    print(f"[SOCKS5] Proxy listening on port {{SOCKS5_PROXY_PORT}}")

    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()

    print(f"\\n=== Onichan Proxy Daemon Running ===")
    print(f"HTTP Proxy  : 0.0.0.0:{{HTTP_PROXY_PORT}}")
    print(f"SOCKS5 Proxy: 0.0.0.0:{{SOCKS5_PROXY_PORT}}")
    print(f"API Server  : 0.0.0.0:{{API_PORT}}")
    print(f"Credentials : {{len(credentials)}} loaded")
    print(f"====================================\\n")

    await asyncio.gather(
        http_server.serve_forever(),
        socks5_server.serve_forever(),
    )

async def periodic_bw_save():
    while True:
        await asyncio.sleep(30)
        save_bandwidth()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        save_bandwidth()
        print("\\nShutdown.")
'''
