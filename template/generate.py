#!/usr/bin/env python3
"""Builds the finished installer files in output/ from installer.conf and the templates.

    python3 template/generate.py linux   USER/REPO v1.0.1
    python3 template/generate.py windows USER/REPO v1.0.1

Settings in installer.conf are on without "#" in front and off with "#" in front.
"""
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "output")


def read_conf():
    conf = {}
    with open(os.path.join(ROOT, "installer.conf"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r'\s*([A-Z_]+)\s*=\s*"(.*)"\s*(#.*)?$', line)   # lines starting with "#" are off
            if m:
                conf[m.group(1)] = m.group(2)
    for required in ("APP_NAME", "APP_ID"):
        if not conf.get(required):
            sys.exit(f"installer.conf: {required} is missing")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", conf["APP_ID"]):
        sys.exit("installer.conf: APP_ID may only contain letters, digits, dot, dash and underscore")
    if conf.get("VERSION") and not re.fullmatch(r"\d+(\.\d+){0,3}", conf["VERSION"]):
        sys.exit("installer.conf: VERSION must look like 1.2.3")
    return conf


def version(conf, tag):
    """VERSION from installer.conf if switched on, otherwise from the release tag (v1.2.3 -> 1.2.3)."""
    return conf.get("VERSION") or re.sub(r"^[vV]", "", tag) or "1.0.0"


def sh_double(text):   # content for "…" in the shell
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")


def sh_single(text):   # content for '…' in the shell
    return text.replace("'", "'\\''")


def fill(template, values):
    text = open(os.path.join(HERE, template), encoding="utf-8").read()
    for k, v in values.items():
        text = text.replace(f"@{k}@", v)
    left = re.findall(r"@[A-Z_]+@", text)
    if left:
        sys.exit(f"{template}: not replaced: {sorted(set(left))}")
    return text


def linux(conf, repo, tag):
    if not conf.get("LINUX_FILE"):
        print("LINUX_FILE is off – no Linux installers")
        return
    values = {k: sh_double(conf.get(k, "")) for k in ("APP_NAME", "APP_ID", "LINUX_FILE", "LINUX_RUN", "ICON_PNG",
                                                       "PKGS_ARCH", "PKGS_DEB", "PKGS_RPM", "PKGS_SUSE")}
    values["REPO"] = repo
    values["VERSION"] = version(conf, tag)
    values["ROOT_CMDS"] = sh_single(conf.get("ROOT_CMDS", ""))
    values["APP_COMMENT"] = conf.get("APP_COMMENT", "").replace("$", "\\$").replace("`", "\\`")
    script = f"{conf['APP_ID']}-install.sh"
    with open(os.path.join(OUT, script), "w", encoding="utf-8", newline="\n") as f:
        f.write(fill("install.sh", values))
    os.chmod(os.path.join(OUT, script), 0o755)
    # Double-click files: download the latest install script and run it
    url = f"https://github.com/{repo}/releases/latest/download/{script}"
    for short, suffix in (("arch", " (Arch)"), ("deb", " (Debian/Ubuntu)"), ("", "")):
        name = f"{conf['APP_ID']}{'-' + short if short else ''}-installer.desktop"
        error = "Download failed. Is there an internet connection?"
        exec_ = (f'bash -c "curl -fsSL -o /tmp/{script} {url} || {{ kdialog --error \\"{error}\\" || '
                 f'zenity --error --text=\\"{error}\\"; exit 1; }}; bash /tmp/{script}"')
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as f:
            f.write("[Desktop Entry]\nType=Application\n"
                    f"Name=Install {conf['APP_NAME']}{suffix}\n"
                    "Comment=Downloads the latest version and installs it\n"
                    "Icon=system-software-install\n"
                    f"Exec={exec_}\nTerminal=false\nCategories=Utility;\n")
    print(f"Linux installers built (version {values['VERSION']})")


def windows(conf, repo, tag):
    if not conf.get("WINDOWS_FILE"):
        print("WINDOWS_FILE is off – no Windows setup")
        return
    icon = conf.get("ICON_ICO", "")
    values = {"APP_NAME": conf["APP_NAME"].replace('"', "'"), "APP_ID": conf["APP_ID"], "VERSION": version(conf, tag),
              "WINDOWS_FILE": conf["WINDOWS_FILE"], "REPO": repo,
              "APP_GUID": str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://github.com/{repo}")).upper(),
              "SETUP_ICON": f"SetupIconFile=..\\{icon.replace('/', chr(92))}" if icon else ""}
    with open(os.path.join(OUT, "setup.iss"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(fill("setup.iss", values))
    print(f"Windows setup script built (version {values['VERSION']})")


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("linux", "windows"):
        sys.exit(__doc__)
    os.makedirs(OUT, exist_ok=True)
    c = read_conf()
    (linux if sys.argv[1] == "linux" else windows)(c, sys.argv[2], sys.argv[3])
