"""Vorlagen für neue Dateien und Ordner. Hier anpassen."""

from __future__ import annotations

import re
from datetime import date

FOLDER_FILE = ".pandora.yaml"

FOLDER_TEMPLATE = """\
owner: thomas
visibility: private

security:
  local_allowed: true
  company_allowed: true
  cloud_allowed: false
"""

FRONTMATTER_TEMPLATE = """\
---
title: {title}

tags:

summary:

priority: normal

status: active

created: {today}
updated:
reviewed:

aliases:

---

"""

YAML_WORDS = {"true", "false", "yes", "no", "on", "off", "null", "y", "n"}


def yaml_string(value: str) -> str:
    """Setzt nur dann Anführungszeichen, wenn YAML den Text sonst falsch läse."""
    if re.fullmatch(r"[^\W\d_][\w ,.()-]*", value) and value.lower() not in YAML_WORDS:
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def frontmatter(title: str, today: date | None = None) -> str:
    return FRONTMATTER_TEMPLATE.format(
        title=yaml_string(title), today=(today or date.today()).isoformat()
    )
