import os
import secrets
import string
import json
from datetime import datetime, timedelta
from modules.database import _execute_with_retry, get_connection_with_retry


PROXY_TYPES = ['SOCKS5', 'HTTP', 'HTTPS', 'SOCKS4']
PROXY_CATEGORIES = ['residential', 'rotating', 'datacenter', 'premium']
SOURCE_TYPES = ['vps', 'pool']


def _generate_credentials():
    username = 'oni_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10))
    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    return username, password


def create_proxy_plan(name, proxy_type, bandwidth_gb, price, duration_days=30,
                      country='', description='', category='datacenter', source_type='vps'):
    return _execute_with_retry("""
        INSERT INTO proxy_plans (name, proxy_type, bandwidth_gb, price, duration_days,
                                  country, description, category, source_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (name, proxy_type.upper(), bandwidth_gb, price, duration_days,
          country, description, category, source_type), fetch_one=True)


def update_proxy_plan(plan_id, name=None, proxy_type=None, bandwidth_gb=None, price=None,
                      duration_days=None, country=None, description=None, active=None,
                      category=None, source_type=None):
    updates = []
    params = []
    field_map = {
        'name': name, 'proxy_type': proxy_type, 'bandwidth_gb': bandwidth_gb,
        'price': price, 'duration_days': duration_days, 'country': country,
        'description': description, 'active': active,
        'category': category, 'source_type': source_type
    }
    for key, val in field_map.items():
        if val is not None:
            updates.append(f"{key} = %s")
            if key == 'proxy_type':
                val = val.upper()
            params.append(val)
    if not updates:
        return False
    params.append(plan_id)
    return _execute_with_retry(
        f"UPDATE proxy_plans SET {', '.join(updates)} WHERE id = %s",
        params, return_rowcount=True
    )


def delete_proxy_plan(plan_id):
    return _execute_with_retry(
        "DELETE FROM proxy_plans WHERE id = %s", (plan_id,), return_rowcount=True
    )


def get_proxy_plans(proxy_type=None, country=None, active_only=True, category=None, source_type=None):
    conditions = []
    params = []
    if active_only:
        conditions.append("active = TRUE")
    if proxy_type:
        conditions.append("proxy_type = %s")
        params.append(proxy_type.upper())
    if country:
        conditions.append("(LOWER(country) LIKE %s OR country = '')")
        params.append(f"%{country.lower()}%")
    if category:
        conditions.append("category = %s")
        params.append(category)
    if source_type:
        conditions.append("source_type = %s")
        params.append(source_type)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return _execute_with_retry(
        f"SELECT * FROM proxy_plans {where} ORDER BY category, proxy_type, bandwidth_gb",
        params, fetch=True
    ) or []


def get_proxy_plan(plan_id):
    return _execute_with_retry(
        "SELECT * FROM proxy_plans WHERE id = %s",
        (plan_id,), fetch_one=True
    )


def add_proxy_server(host, port, proxy_type, username='', password='',
                     country='', max_bandwidth_gb=0, label=''):
    return _execute_with_retry("""
        INSERT INTO proxy_servers (host, port, proxy_type, username, password,
                                   country, max_bandwidth_gb, used_bandwidth_gb, label)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s)
        RETURNING id
    """, (host, port, proxy_type.upper(), username, password, country, max_bandwidth_gb, label),
        fetch_one=True)


def update_proxy_server(server_id, **kwargs):
    updates = []
    params = []
    for key in ['host', 'port', 'proxy_type', 'username', 'password', 'country',
                'max_bandwidth_gb', 'used_bandwidth_gb', 'label', 'active']:
        if key in kwargs:
            updates.append(f"{key} = %s")
            val = kwargs[key]
            if key == 'proxy_type':
                val = val.upper()
            params.append(val)
    if not updates:
        return False
    params.append(server_id)
    return _execute_with_retry(
        f"UPDATE proxy_servers SET {', '.join(updates)} WHERE id = %s",
        params, return_rowcount=True
    )


def delete_proxy_server(server_id):
    return _execute_with_retry(
        "DELETE FROM proxy_servers WHERE id = %s", (server_id,), return_rowcount=True
    )


def get_proxy_servers(proxy_type=None, active_only=True):
    conditions = []
    params = []
    if active_only:
        conditions.append("active = TRUE")
    if proxy_type:
        conditions.append("proxy_type = %s")
        params.append(proxy_type.upper())
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return _execute_with_retry(
        f"SELECT * FROM proxy_servers {where} ORDER BY proxy_type, host",
        params, fetch=True
    ) or []


def get_proxy_server(server_id):
    return _execute_with_retry(
        "SELECT * FROM proxy_servers WHERE id = %s",
        (server_id,), fetch_one=True
    )


def purchase_proxy(user_id, plan_id):
    from psycopg2.extras import RealDictCursor
    conn = get_connection_with_retry()
    if not conn:
        return {'error': 'Database connection failed'}

    old_autocommit = conn.autocommit
    try:
        conn.autocommit = False

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM proxy_plans WHERE id = %s AND active = TRUE FOR UPDATE",
                (plan_id,)
            )
            plan = cur.fetchone()
            if not plan:
                conn.rollback()
                return {'error': 'Plan not available'}

            price = float(plan['price'])
            duration = int(plan.get('duration_days', 30) or 30)
            bw_gb = float(plan['bandwidth_gb'])
            source_type = plan.get('source_type', 'vps')
            plan_country = (plan.get('country') or '').strip()

            cur.execute(
                "SELECT shop_balance FROM users WHERE user_id = %s FOR UPDATE",
                (user_id,)
            )
            user = cur.fetchone()
            if not user:
                conn.rollback()
                return {'error': 'User not found'}

            balance = float(user.get('shop_balance', 0) or 0)
            if balance < price:
                conn.rollback()
                return {'error': f'Insufficient balance. Need ${price:.2f}, have ${balance:.2f}'}

            proxy_user, proxy_pass = _generate_credentials()
            proxy_host = ''
            proxy_port = 0
            server_id = None
            node_id = None
            pool_proxy_id = None

            plan_category = (plan.get('category') or 'datacenter').lower()
            is_rotating = plan_category == 'rotating'
            pool_list_size = 10 if is_rotating else 1
            proxy_list_data = []

            if source_type == 'pool':
                pool_conds = ["alive = TRUE"]
                pool_params = []

                if plan['proxy_type'] and plan['proxy_type'] not in ('HTTPS', 'ALL'):
                    pool_conds.append("proxy_type = %s")
                    pool_params.append(plan['proxy_type'])
                if plan_country:
                    pool_conds.append("LOWER(country) LIKE LOWER(%s)")
                    pool_params.append(f"%{plan_country}%")
                if plan_category == 'residential':
                    pool_conds.append("classification = 'residential'")
                elif plan_category == 'datacenter':
                    pool_conds.append("classification = 'datacenter'")

                pool_where = " AND ".join(pool_conds)
                cur.execute(f"""
                    SELECT * FROM proxy_pool
                    WHERE {pool_where}
                    ORDER BY speed_ms ASC, RANDOM()
                    LIMIT %s
                """, pool_params + [pool_list_size])
                pool_proxies = cur.fetchall()

                if not pool_proxies:
                    fallback_conds = ["alive = TRUE"]
                    fallback_params = []
                    if plan['proxy_type'] and plan['proxy_type'] not in ('HTTPS', 'ALL'):
                        fallback_conds.append("proxy_type = %s")
                        fallback_params.append(plan['proxy_type'])
                    fallback_where = " AND ".join(fallback_conds)
                    cur.execute(f"""
                        SELECT * FROM proxy_pool
                        WHERE {fallback_where}
                        ORDER BY speed_ms ASC, RANDOM()
                        LIMIT %s
                    """, fallback_params + [pool_list_size])
                    pool_proxies = cur.fetchall()

                if not pool_proxies:
                    conn.rollback()
                    return {'error': 'No proxies available in pool right now. Try again later.'}

                proxy_host = pool_proxies[0]['host']
                proxy_port = pool_proxies[0]['port']
                pool_proxy_id = pool_proxies[0]['id']
                proxy_user = pool_proxies[0].get('username', '') or proxy_user
                proxy_pass = pool_proxies[0].get('password', '') or proxy_pass

                for pp in pool_proxies:
                    proxy_list_data.append({
                        'host': pp['host'], 'port': pp['port'],
                        'user': pp.get('username', ''), 'pass': pp.get('password', ''),
                        'country': pp.get('country', ''), 'type': pp.get('proxy_type', ''),
                        'pool_id': pp['id'],
                    })
            else:
                node_conds = ["active = TRUE"]
                node_params = []

                if plan['proxy_type']:
                    node_conds.append("UPPER(protocols) LIKE %s")
                    node_params.append(f"%{plan['proxy_type'].upper()}%")
                if plan_country:
                    node_conds.append("LOWER(country) = LOWER(%s)")
                    node_params.append(plan_country)
                if bw_gb > 0:
                    node_conds.append("(max_bandwidth_gb <= 0 OR (max_bandwidth_gb - COALESCE(used_bandwidth_gb, 0)) >= %s)")
                    node_params.append(bw_gb)

                node_where = " AND ".join(node_conds)
                cur.execute(f"""
                    SELECT * FROM proxy_nodes WHERE {node_where}
                    ORDER BY RANDOM() LIMIT 1 FOR UPDATE
                """, node_params)
                node = cur.fetchone()

                if not node:
                    if plan_country:
                        cur.execute("""
                            SELECT * FROM proxy_servers
                            WHERE proxy_type = %s AND active = TRUE
                              AND LOWER(country) = LOWER(%s)
                              AND (max_bandwidth_gb <= 0 OR (max_bandwidth_gb - COALESCE(used_bandwidth_gb, 0)) >= %s)
                            ORDER BY RANDOM() LIMIT 1 FOR UPDATE
                        """, (plan['proxy_type'], plan_country, bw_gb))
                    else:
                        cur.execute("""
                            SELECT * FROM proxy_servers
                            WHERE proxy_type = %s AND active = TRUE
                              AND (max_bandwidth_gb <= 0 OR (max_bandwidth_gb - COALESCE(used_bandwidth_gb, 0)) >= %s)
                            ORDER BY RANDOM() LIMIT 1 FOR UPDATE
                        """, (plan['proxy_type'], bw_gb))
                    server = cur.fetchone()
                    if not server:
                        conn.rollback()
                        reason = f'No active {plan["proxy_type"]} nodes/servers'
                        if plan_country:
                            reason += f' in {plan_country}'
                        reason += ' with sufficient bandwidth. Contact admin.'
                        return {'error': reason}
                    proxy_host = server['host']
                    proxy_port = server['port']
                    server_id = server['id']
                    cur.execute(
                        "UPDATE proxy_servers SET used_bandwidth_gb = COALESCE(used_bandwidth_gb, 0) + %s WHERE id = %s",
                        (bw_gb, server_id)
                    )
                else:
                    node_id = node['id']
                    proxy_host = node['host']
                    try:
                        ports = json.loads(node.get('proxy_ports', '{}'))
                    except (json.JSONDecodeError, TypeError):
                        ports = {"http": 8080, "socks5": 1080}

                    ptype = plan['proxy_type'].upper()
                    if ptype in ('SOCKS5', 'SOCKS4'):
                        proxy_port = ports.get('socks5', 1080)
                    else:
                        proxy_port = ports.get('http', 8080)

                    cur.execute(
                        "UPDATE proxy_nodes SET used_bandwidth_gb = COALESCE(used_bandwidth_gb, 0) + %s WHERE id = %s",
                        (bw_gb, node_id)
                    )

            expires_at = datetime.utcnow() + timedelta(days=duration)

            proxy_list_json = json.dumps(proxy_list_data) if proxy_list_data else ''

            cur.execute(
                "UPDATE users SET shop_balance = shop_balance - %s, updated_at = NOW() WHERE user_id = %s",
                (price, user_id)
            )

            cur.execute("""
                INSERT INTO proxy_purchases
                    (user_id, plan_id, server_id, node_id, pool_proxy_id,
                     proxy_host, proxy_port, proxy_user, proxy_pass,
                     proxy_type, bandwidth_gb, bandwidth_used_gb, price,
                     source_type, proxy_list, status, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, 'active', %s)
                RETURNING id
            """, (
                user_id, plan_id, server_id, node_id, pool_proxy_id,
                proxy_host, proxy_port, proxy_user, proxy_pass,
                plan['proxy_type'], bw_gb, price, source_type, proxy_list_json, expires_at
            ))
            purchase = cur.fetchone()

        conn.commit()

        if node_id:
            try:
                from modules.proxy_nodes import get_node, sync_node_credentials
                node_obj = get_node(node_id)
                if node_obj:
                    sync_node_credentials(node_obj)
            except Exception as e:
                print(f"[ProxyShop] Credential sync failed for node {node_id}: {e}")

        return {
            'success': True,
            'purchase_id': purchase['id'],
            'proxy_host': proxy_host,
            'proxy_port': proxy_port,
            'proxy_user': proxy_user,
            'proxy_pass': proxy_pass,
            'proxy_type': plan['proxy_type'],
            'bandwidth_gb': bw_gb,
            'duration_days': duration,
            'price': price,
            'new_balance': balance - price,
            'expires_at': expires_at.strftime('%Y-%m-%d %H:%M UTC'),
            'source_type': source_type,
        }
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        return {'error': f'Purchase failed: {str(e)}'}
    finally:
        conn.autocommit = old_autocommit


def get_user_proxy_purchases(user_id, page=1, per_page=20):
    offset = (page - 1) * per_page
    count_result = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM proxy_purchases WHERE user_id = %s",
        (user_id,), fetch_one=True
    )
    total = count_result.get('cnt', 0) if count_result else 0

    purchases = _execute_with_retry("""
        SELECT pp.*, p.name as plan_name, p.description as plan_desc,
               p.duration_days as plan_duration, p.category as plan_category
        FROM proxy_purchases pp
        LEFT JOIN proxy_plans p ON pp.plan_id = p.id
        WHERE pp.user_id = %s
        ORDER BY pp.purchased_at DESC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset), fetch=True)

    return {
        'purchases': purchases or [],
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page if total > 0 else 1
    }


def get_proxy_purchase(purchase_id):
    return _execute_with_retry("""
        SELECT pp.*, p.name as plan_name
        FROM proxy_purchases pp
        LEFT JOIN proxy_plans p ON pp.plan_id = p.id
        WHERE pp.id = %s
    """, (purchase_id,), fetch_one=True)


def get_proxy_shop_stats():
    result = _execute_with_retry("""
        SELECT
            COUNT(*) as total_purchases,
            COUNT(*) FILTER (WHERE status = 'active') as active_purchases,
            COUNT(*) FILTER (WHERE status = 'expired') as expired_purchases,
            COALESCE(SUM(price), 0) as total_revenue,
            COALESCE(SUM(bandwidth_used_gb), 0) as total_bandwidth_used
        FROM proxy_purchases
    """, fetch_one=True)

    plans_count = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM proxy_plans WHERE active = TRUE",
        fetch_one=True
    )
    servers_count = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM proxy_servers WHERE active = TRUE",
        fetch_one=True
    )
    nodes_count = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM proxy_nodes WHERE active = TRUE",
        fetch_one=True
    )
    nodes_online = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM proxy_nodes WHERE active = TRUE AND status = 'online'",
        fetch_one=True
    )
    pool_count = _execute_with_retry(
        "SELECT COUNT(*) as cnt FROM proxy_pool WHERE alive = TRUE",
        fetch_one=True
    )

    if result:
        return {
            'total_purchases': result.get('total_purchases', 0) or 0,
            'active_purchases': result.get('active_purchases', 0) or 0,
            'expired_purchases': result.get('expired_purchases', 0) or 0,
            'total_revenue': float(result.get('total_revenue', 0) or 0),
            'total_bandwidth_used': float(result.get('total_bandwidth_used', 0) or 0),
            'active_plans': (plans_count.get('cnt', 0) if plans_count else 0),
            'active_servers': (servers_count.get('cnt', 0) if servers_count else 0),
            'active_nodes': (nodes_count.get('cnt', 0) if nodes_count else 0),
            'online_nodes': (nodes_online.get('cnt', 0) if nodes_online else 0),
            'pool_proxies': (pool_count.get('cnt', 0) if pool_count else 0),
        }
    return {
        'total_purchases': 0, 'active_purchases': 0, 'expired_purchases': 0,
        'total_revenue': 0, 'total_bandwidth_used': 0, 'active_plans': 0,
        'active_servers': 0, 'active_nodes': 0, 'online_nodes': 0, 'pool_proxies': 0
    }


def get_all_proxy_purchases(page=1, per_page=50, status=None):
    conditions = ["1=1"]
    params = []
    if status:
        conditions.append("pp.status = %s")
        params.append(status)
    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    count_result = _execute_with_retry(
        f"SELECT COUNT(*) as cnt FROM proxy_purchases pp WHERE {where}",
        params, fetch_one=True
    )
    total = count_result.get('cnt', 0) if count_result else 0

    purchases = _execute_with_retry(f"""
        SELECT pp.*, p.name as plan_name
        FROM proxy_purchases pp
        LEFT JOIN proxy_plans p ON pp.plan_id = p.id
        WHERE {where}
        ORDER BY pp.purchased_at DESC
        LIMIT %s OFFSET %s
    """, params + [per_page, offset], fetch=True)

    return {
        'purchases': purchases or [],
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page if total > 0 else 1
    }


def expire_old_purchases():
    return _execute_with_retry("""
        UPDATE proxy_purchases SET status = 'expired'
        WHERE status = 'active' AND expires_at < NOW()
    """, return_rowcount=True) or 0


def cancel_proxy_purchase(purchase_id):
    return _execute_with_retry(
        "UPDATE proxy_purchases SET status = 'cancelled' WHERE id = %s AND status = 'active'",
        (purchase_id,), return_rowcount=True
    )


def refresh_rotating_proxies(purchase_id):
    from psycopg2.extras import RealDictCursor
    conn = get_connection_with_retry()
    if not conn:
        return {'error': 'Database connection failed'}

    old_autocommit = conn.autocommit
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT pp.*, p.category, p.country FROM proxy_purchases pp LEFT JOIN proxy_plans p ON pp.plan_id = p.id WHERE pp.id = %s AND pp.status = 'active' FOR UPDATE",
                (purchase_id,)
            )
            purchase = cur.fetchone()
            if not purchase:
                conn.rollback()
                return {'error': 'Purchase not found or not active'}

            if purchase.get('source_type') != 'pool':
                conn.rollback()
                return {'error': 'Refresh only available for pool-based plans'}

            plan_category = (purchase.get('category') or 'datacenter').lower()
            proxy_type = purchase.get('proxy_type', 'HTTP')
            plan_country = (purchase.get('country') or '').strip()
            pool_size = 10 if plan_category == 'rotating' else 1

            pool_conds = ["alive = TRUE"]
            pool_params = []
            if proxy_type and proxy_type != 'HTTPS':
                pool_conds.append("proxy_type = %s")
                pool_params.append(proxy_type)
            if plan_country:
                pool_conds.append("LOWER(country) LIKE LOWER(%s)")
                pool_params.append(f"%{plan_country}%")
            if plan_category == 'residential':
                pool_conds.append("classification = 'residential'")
            elif plan_category == 'datacenter':
                pool_conds.append("classification = 'datacenter'")

            pool_where = " AND ".join(pool_conds)
            cur.execute(f"""
                SELECT * FROM proxy_pool WHERE {pool_where}
                ORDER BY RANDOM() LIMIT %s
            """, pool_params + [pool_size])
            pool_proxies = cur.fetchall()
            if not pool_proxies:
                conn.rollback()
                return {'error': 'No proxies available in pool for refresh'}

            proxy_list_data = []
            for pp in pool_proxies:
                proxy_list_data.append({
                    'host': pp['host'], 'port': pp['port'],
                    'user': pp.get('username', ''), 'pass': pp.get('password', ''),
                    'country': pp.get('country', ''), 'type': pp.get('proxy_type', ''),
                    'pool_id': pp['id'],
                })

            new_host = pool_proxies[0]['host']
            new_port = pool_proxies[0]['port']
            new_pool_id = pool_proxies[0]['id']
            proxy_list_json = json.dumps(proxy_list_data)

            new_user = pool_proxies[0].get('username', '') or ''
            new_pass = pool_proxies[0].get('password', '') or ''

            cur.execute("""
                UPDATE proxy_purchases SET proxy_host = %s, proxy_port = %s,
                    pool_proxy_id = %s, proxy_list = %s,
                    proxy_user = %s, proxy_pass = %s
                WHERE id = %s
            """, (new_host, new_port, new_pool_id, proxy_list_json, new_user, new_pass, purchase_id))

        conn.commit()
        return {'success': True, 'count': len(proxy_list_data), 'proxies': proxy_list_data}
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        return {'error': f'Refresh failed: {str(e)}'}
    finally:
        conn.autocommit = old_autocommit


def get_proxy_list(purchase):
    proxy_list_str = purchase.get('proxy_list', '') or ''
    if not proxy_list_str:
        return [format_proxy_string(purchase)]
    try:
        items = json.loads(proxy_list_str)
        result = []
        for item in items:
            host = item.get('host', '')
            port = item.get('port', 0)
            user = item.get('user', '')
            pwd = item.get('pass', '')
            if user and pwd:
                result.append(f"{host}:{port}:{user}:{pwd}")
            else:
                result.append(f"{host}:{port}")
        return result if result else [format_proxy_string(purchase)]
    except (json.JSONDecodeError, TypeError):
        return [format_proxy_string(purchase)]


def format_proxy_string(purchase):
    host = purchase.get('proxy_host', '')
    port = purchase.get('proxy_port', 0)
    user = purchase.get('proxy_user', '')
    pwd = purchase.get('proxy_pass', '')
    if user and pwd:
        return f"{host}:{port}:{user}:{pwd}"
    return f"{host}:{port}"


def bandwidth_meter_data(purchase):
    bw_total = float(purchase.get('bandwidth_gb', 0))
    bw_used = float(purchase.get('bandwidth_used_gb', 0))
    if bw_total <= 0:
        return {
            'total': 0, 'used': bw_used, 'remaining': 0,
            'percent': 0, 'unlimited': True,
            'label': f'{bw_used:.2f} GB Used',
            'color': '#4ade80',
        }
    remaining = max(0, bw_total - bw_used)
    pct = min(100, (bw_used / bw_total * 100))
    if pct < 60:
        color = '#4ade80'
    elif pct < 85:
        color = '#facc15'
    else:
        color = '#ef4444'
    return {
        'total': bw_total, 'used': bw_used, 'remaining': remaining,
        'percent': pct, 'unlimited': False,
        'label': f'{bw_used:.2f} / {bw_total:.0f} GB ({pct:.0f}%)',
        'color': color,
    }


def _update_pool_bandwidth():
    try:
        pool_purchases = _execute_with_retry("""
            SELECT pp.id, pp.purchased_at, pp.bandwidth_gb, pp.proxy_list
            FROM proxy_purchases pp
            WHERE pp.status = 'active' AND pp.source_type = 'pool'
        """, fetch=True) or []
        for p in pool_purchases:
            proxy_count = 1
            if p.get('proxy_list'):
                try:
                    proxy_count = max(1, len(json.loads(p['proxy_list'])))
                except (json.JSONDecodeError, TypeError):
                    pass
            created = p['purchased_at']
            if isinstance(created, str):
                created = datetime.strptime(created[:19], '%Y-%m-%d %H:%M:%S')
            hours_active = max(1, (datetime.utcnow() - created).total_seconds() / 3600)
            estimated_gb = round(proxy_count * hours_active * 0.005, 4)
            bw_limit = p.get('bandwidth_gb') or 0
            if bw_limit > 0:
                estimated_gb = min(estimated_gb, bw_limit)
            _execute_with_retry(
                "UPDATE proxy_purchases SET bandwidth_used_gb = %s WHERE id = %s",
                (estimated_gb, p['id'])
            )
    except Exception as e:
        print(f"[ProxyShop] Pool bandwidth update error: {e}")


def _auto_refresh_rotating_loop(interval_minutes=30):
    import time as _time
    while True:
        try:
            _update_pool_bandwidth()
        except Exception as e:
            print(f"[ProxyShop] Pool bandwidth update error: {e}")

        try:
            active_rotating = _execute_with_retry("""
                SELECT pp.id FROM proxy_purchases pp
                LEFT JOIN proxy_plans p ON pp.plan_id = p.id
                WHERE pp.status = 'active' AND pp.source_type = 'pool'
                  AND p.category = 'rotating'
            """, fetch=True) or []
            for purchase in active_rotating:
                try:
                    refresh_rotating_proxies(purchase['id'])
                except Exception:
                    pass
            if active_rotating:
                print(f"[ProxyShop] Auto-refreshed {len(active_rotating)} rotating purchases")
        except Exception as e:
            print(f"[ProxyShop] Auto-refresh error: {e}")
        _time.sleep(interval_minutes * 60)


def start_rotating_refresh_thread(interval_minutes=30):
    import threading
    t = threading.Thread(target=_auto_refresh_rotating_loop, args=(interval_minutes,), daemon=True)
    t.start()
    print(f"[ProxyShop] Rotating auto-refresh thread started (interval: {interval_minutes}min)")
    return True


def bandwidth_meter_text(purchase):
    m = bandwidth_meter_data(purchase)
    if m['unlimited']:
        return f"📊 {m['used']:.2f} GB Used (Unlimited)"
    filled = int(m['percent'] / 10)
    empty = 10 - filled
    bar = '▓' * filled + '░' * empty
    return f"📊 [{bar}] {m['label']}"
