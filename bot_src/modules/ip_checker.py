import aiohttp
import re
import os
from typing import Dict, Any, Optional

VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")
ABUSEIPDB_API_KEY = os.getenv("ABUSEIPDB_API_KEY", "")

def is_valid_ip(ip: str) -> bool:
    """Validate IPv4 address"""
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False
    parts = ip.split('.')
    return all(0 <= int(part) <= 255 for part in parts)

async def check_ip_api(ip: str) -> Dict[str, Any]:
    """Get IP info from ip-api.com (free, no key required)"""
    result = {"source": "ip-api.com", "success": False}
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,mobile,proxy,hosting,query"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        result["success"] = True
                        result["ip"] = data.get("query", ip)
                        result["country"] = data.get("country", "Unknown")
                        result["country_code"] = data.get("countryCode", "")
                        result["region"] = data.get("regionName", "")
                        result["city"] = data.get("city", "")
                        result["isp"] = data.get("isp", "Unknown")
                        result["org"] = data.get("org", "")
                        result["as"] = data.get("as", "")
                        result["is_mobile"] = data.get("mobile", False)
                        result["is_proxy"] = data.get("proxy", False)
                        result["is_hosting"] = data.get("hosting", False)
                        result["lat"] = data.get("lat", 0)
                        result["lon"] = data.get("lon", 0)
                        result["timezone"] = data.get("timezone", "")
    except Exception as e:
        result["error"] = str(e)
    return result

async def check_ipinfo(ip: str) -> Dict[str, Any]:
    """Get IP info from ipinfo.io (free tier)"""
    result = {"source": "ipinfo.io", "success": False}
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://ipinfo.io/{ip}/json"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result["success"] = True
                    result["ip"] = data.get("ip", ip)
                    result["hostname"] = data.get("hostname", "")
                    result["city"] = data.get("city", "")
                    result["region"] = data.get("region", "")
                    result["country"] = data.get("country", "")
                    result["org"] = data.get("org", "")
                    result["postal"] = data.get("postal", "")
    except Exception as e:
        result["error"] = str(e)
    return result

async def check_virustotal(ip: str) -> Dict[str, Any]:
    """Check IP reputation on VirusTotal (requires API key)"""
    result = {"source": "VirusTotal", "success": False}
    
    if not VIRUSTOTAL_API_KEY:
        result["error"] = "API key not configured"
        return result
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://www.virustotal.com/api/v3/ip_addresses/{ip}"
            headers = {"accept": "application/json", "x-apikey": VIRUSTOTAL_API_KEY}
            
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    attrs = data.get("data", {}).get("attributes", {})
                    stats = attrs.get("last_analysis_stats", {})
                    
                    result["success"] = True
                    result["malicious"] = stats.get("malicious", 0)
                    result["suspicious"] = stats.get("suspicious", 0)
                    result["harmless"] = stats.get("harmless", 0)
                    result["undetected"] = stats.get("undetected", 0)
                    result["as_owner"] = attrs.get("as_owner", "Unknown")
                    result["reputation"] = attrs.get("reputation", 0)
                    result["total_votes"] = attrs.get("total_votes", {})
                elif resp.status == 401:
                    result["error"] = "Invalid API key"
                else:
                    result["error"] = f"API error: {resp.status}"
    except Exception as e:
        result["error"] = str(e)
    return result

async def check_abuseipdb(ip: str) -> Dict[str, Any]:
    """Check IP reputation on AbuseIPDB (requires API key)"""
    result = {"source": "AbuseIPDB", "success": False}
    
    if not ABUSEIPDB_API_KEY:
        result["error"] = "API key not configured"
        return result
    
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.abuseipdb.com/api/v2/check"
            params = {"ipAddress": ip, "maxAgeInDays": "90"}
            headers = {"Accept": "application/json", "Key": ABUSEIPDB_API_KEY}
            
            async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    info = data.get("data", {})
                    
                    result["success"] = True
                    result["ip"] = info.get("ipAddress", ip)
                    result["is_public"] = info.get("isPublic", True)
                    result["abuse_score"] = info.get("abuseConfidenceScore", 0)
                    result["country_code"] = info.get("countryCode", "")
                    result["usage_type"] = info.get("usageType", "")
                    result["isp"] = info.get("isp", "")
                    result["domain"] = info.get("domain", "")
                    result["is_tor"] = info.get("isTor", False)
                    result["is_whitelisted"] = info.get("isWhitelisted", False)
                    result["total_reports"] = info.get("totalReports", 0)
                    result["num_distinct_users"] = info.get("numDistinctUsers", 0)
                    result["last_reported"] = info.get("lastReportedAt", "")
                elif resp.status == 401:
                    result["error"] = "Invalid API key"
                else:
                    result["error"] = f"API error: {resp.status}"
    except Exception as e:
        result["error"] = str(e)
    return result

async def check_proxycheck(ip: str) -> Dict[str, Any]:
    """Check if IP is a proxy using proxycheck.io (free tier)"""
    result = {"source": "proxycheck.io", "success": False}
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://proxycheck.io/v2/{ip}?vpn=1&asn=1&risk=1"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "ok" and ip in data:
                        ip_data = data[ip]
                        result["success"] = True
                        result["is_proxy"] = ip_data.get("proxy") == "yes"
                        result["proxy_type"] = ip_data.get("type", "")
                        result["provider"] = ip_data.get("provider", "")
                        result["country"] = ip_data.get("country", "")
                        result["risk"] = ip_data.get("risk", 0)
                        result["asn"] = ip_data.get("asn", "")
    except Exception as e:
        result["error"] = str(e)
    return result

def calculate_risk_score(results: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate overall risk score based on all checks"""
    score = 0
    max_score = 100
    factors = []
    
    ip_api = results.get("ip_api", {})
    if ip_api.get("success"):
        if ip_api.get("is_proxy"):
            score += 30
            factors.append("Proxy detected")
        if ip_api.get("is_hosting"):
            score += 15
            factors.append("Hosting/Datacenter IP")
        if ip_api.get("is_mobile"):
            score += 5
            factors.append("Mobile network")
    
    proxycheck = results.get("proxycheck", {})
    if proxycheck.get("success"):
        if proxycheck.get("is_proxy"):
            score += 25
            if proxycheck.get("proxy_type"):
                factors.append(f"Proxy type: {proxycheck['proxy_type']}")
        risk = proxycheck.get("risk", 0)
        if risk > 50:
            score += 20
            factors.append(f"High risk score: {risk}")
    
    vt = results.get("virustotal", {})
    if vt.get("success"):
        malicious = vt.get("malicious", 0)
        suspicious = vt.get("suspicious", 0)
        if malicious > 0:
            score += min(malicious * 5, 40)
            factors.append(f"VirusTotal: {malicious} malicious detections")
        if suspicious > 0:
            score += min(suspicious * 2, 15)
            factors.append(f"VirusTotal: {suspicious} suspicious detections")
    
    abuseipdb = results.get("abuseipdb", {})
    if abuseipdb.get("success"):
        abuse_score = abuseipdb.get("abuse_score", 0)
        if abuse_score > 0:
            score += min(abuse_score // 2, 40)
            factors.append(f"AbuseIPDB confidence: {abuse_score}%")
        if abuseipdb.get("is_tor"):
            score += 20
            factors.append("TOR exit node")
        reports = abuseipdb.get("total_reports", 0)
        if reports > 0:
            factors.append(f"Reported {reports} times")
    
    score = min(score, max_score)
    
    if score >= 70:
        risk_level = "HIGH"
        risk_emoji = "🔴"
    elif score >= 40:
        risk_level = "MEDIUM"
        risk_emoji = "🟡"
    elif score >= 15:
        risk_level = "LOW"
        risk_emoji = "🟢"
    else:
        risk_level = "CLEAN"
        risk_emoji = "✅"
    
    return {
        "score": score,
        "max_score": max_score,
        "level": risk_level,
        "emoji": risk_emoji,
        "factors": factors
    }

async def full_ip_check(ip: str) -> Dict[str, Any]:
    """Run all IP checks and compile results"""
    import asyncio
    
    if not is_valid_ip(ip):
        return {"error": "Invalid IP address format", "success": False}
    
    tasks = {
        "ip_api": check_ip_api(ip),
        "ipinfo": check_ipinfo(ip),
        "proxycheck": check_proxycheck(ip),
    }
    
    if VIRUSTOTAL_API_KEY:
        tasks["virustotal"] = check_virustotal(ip)
    
    if ABUSEIPDB_API_KEY:
        tasks["abuseipdb"] = check_abuseipdb(ip)
    
    results = {}
    task_results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    
    for key, result in zip(tasks.keys(), task_results):
        if isinstance(result, Exception):
            results[key] = {"success": False, "error": str(result)}
        else:
            results[key] = result
    
    results["risk"] = calculate_risk_score(results)
    results["ip"] = ip
    results["success"] = True
    
    return results

def format_ip_report(results: Dict[str, Any]) -> str:
    """Format IP check results for Telegram message"""
    if not results.get("success"):
        return f"❌ <b>Error:</b> {results.get('error', 'Unknown error')}"
    
    ip = results.get("ip", "Unknown")
    risk = results.get("risk", {})
    ip_api = results.get("ip_api", {})
    ipinfo = results.get("ipinfo", {})
    proxycheck = results.get("proxycheck", {})
    vt = results.get("virustotal", {})
    abuseipdb = results.get("abuseipdb", {})
    
    report = f"""🔍 <b>IP Reputation Report</b>

📍 <b>IP:</b> <code>{ip}</code>
{risk.get('emoji', '❓')} <b>Risk Level:</b> {risk.get('level', 'UNKNOWN')} ({risk.get('score', 0)}/100)

"""
    
    if ip_api.get("success"):
        report += f"""<b>📌 Location Info</b>
├ Country: {ip_api.get('country', 'N/A')} ({ip_api.get('country_code', '')})
├ Region: {ip_api.get('region', 'N/A')}
├ City: {ip_api.get('city', 'N/A')}
├ ISP: {ip_api.get('isp', 'N/A')}
├ Org: {ip_api.get('org', 'N/A')}
├ AS: {ip_api.get('as', 'N/A')}
├ Proxy: {'Yes ⚠️' if ip_api.get('is_proxy') else 'No ✅'}
├ Hosting: {'Yes' if ip_api.get('is_hosting') else 'No'}
└ Mobile: {'Yes' if ip_api.get('is_mobile') else 'No'}

"""
    
    if proxycheck.get("success"):
        report += f"""<b>🛡️ Proxy Check</b>
├ Is Proxy/VPN: {'Yes ⚠️' if proxycheck.get('is_proxy') else 'No ✅'}
├ Type: {proxycheck.get('proxy_type', 'N/A') or 'N/A'}
└ Risk Score: {proxycheck.get('risk', 0)}

"""
    
    if vt.get("success"):
        report += f"""<b>🦠 VirusTotal</b>
├ Malicious: {vt.get('malicious', 0)} {'⚠️' if vt.get('malicious', 0) > 0 else '✅'}
├ Suspicious: {vt.get('suspicious', 0)}
├ Harmless: {vt.get('harmless', 0)}
└ AS Owner: {vt.get('as_owner', 'N/A')}

"""
    elif vt.get("error") == "API key not configured":
        report += "<i>VirusTotal: API key not set</i>\n\n"
    
    if abuseipdb.get("success"):
        report += f"""<b>🚨 AbuseIPDB</b>
├ Abuse Score: {abuseipdb.get('abuse_score', 0)}% {'⚠️' if abuseipdb.get('abuse_score', 0) > 25 else '✅'}
├ Total Reports: {abuseipdb.get('total_reports', 0)}
├ Is TOR: {'Yes ⚠️' if abuseipdb.get('is_tor') else 'No'}
├ Domain: {abuseipdb.get('domain', 'N/A')}
└ Last Reported: {abuseipdb.get('last_reported', 'Never') or 'Never'}

"""
    elif abuseipdb.get("error") == "API key not configured":
        report += "<i>AbuseIPDB: API key not set</i>\n\n"
    
    factors = risk.get("factors", [])
    if factors:
        report += "<b>⚡ Risk Factors:</b>\n"
        for factor in factors[:5]:
            report += f"• {factor}\n"
    
    return report
