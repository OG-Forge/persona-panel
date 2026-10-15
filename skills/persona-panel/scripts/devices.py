"""Device profiles shared by capture, probe and walk.

Sizes are the CSS viewports people actually browse at: 1366x768 and 1536x864
are the most common Windows laptop viewports (1536x864 is 1920x1080 at 125%
scaling), and 360x780 is a typical budget Android phone.
"""

ANDROID_UA = ("Mozilla/5.0 (Linux; Android 13; SM-A145F) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Mobile Safari/537.36")
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/17.4 Mobile/15E148 Safari/604.1")
IPAD_UA = ("Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
           "Version/17.4 Mobile/15E148 Safari/604.1")
DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")

PROFILES = {
    "mobile":       {"label": "budget Android phone 360x780", "viewport": {"width": 360, "height": 780},
                     "ua": ANDROID_UA, "mobile": True},
    "mobile_large": {"label": "iPhone 393x852", "viewport": {"width": 393, "height": 852},
                     "ua": IPHONE_UA, "mobile": True},
    "tablet":       {"label": "tablet 820x1180 (portrait)", "viewport": {"width": 820, "height": 1180},
                     "ua": IPAD_UA, "mobile": True},
    "laptop":       {"label": "laptop 1366x768", "viewport": {"width": 1366, "height": 768},
                     "ua": DESKTOP_UA, "mobile": False},
    "laptop_hd":    {"label": "laptop 1536x864 (1080p at 125%)", "viewport": {"width": 1536, "height": 864},
                     "ua": DESKTOP_UA, "mobile": False},
    "desktop":      {"label": "desktop monitor 1920x1080", "viewport": {"width": 1920, "height": 1080},
                     "ua": DESKTOP_UA, "mobile": False},
}

# Old profile name kept so earlier runs still load.
PROFILES["desktop_legacy"] = {"label": "desktop 1366x800", "viewport": {"width": 1366, "height": 800},
                              "ua": DESKTOP_UA, "mobile": False}


def context_options(name):
    """Keyword arguments for playwright's browser.new_context()."""
    p = PROFILES[name]
    opts = {"viewport": dict(p["viewport"]), "device_scale_factor": 1, "user_agent": p["ua"]}
    if p["mobile"]:
        opts.update(is_mobile=True, has_touch=True)
    return opts
