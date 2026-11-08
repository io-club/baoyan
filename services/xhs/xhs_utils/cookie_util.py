def trans_cookies(cookies_str):
    value = cookies_str.strip()
    if value.lower().startswith('cookie:'):
        value = value.split(':', 1)[1].strip()
    cookies = {}
    for part in value.split(';'):
        name, separator, content = part.strip().partition('=')
        if separator and name.strip():
            cookies[name.strip()] = content.strip()
    return cookies
