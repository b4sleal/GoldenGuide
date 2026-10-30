"""
robots.txt rules per RFC 9309 (https://www.rfc-editor.org/rfc/rfc9309).

- The group whose user-agent matches the crawler's product token applies, else the `*` group;
  several groups for the same agent are merged.
- The longest matching rule wins; on equal length, allow wins. No match means allowed.
- `*` matches any characters and a trailing `$` anchors the end (the stdlib robotparser
  supports neither, which is why this exists).
- Paths are compared percent-decoded, so `/a%20b` and `/a b` are the same rule.

Fetch outcomes (see RobotsRules.for_status): 2xx -> parse; 4xx -> "unavailable", allow all;
5xx or a network failure -> "unreachable", disallow all, never silently allow.
"""
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

WILDCARD = "*"


@dataclass(frozen=True)
class RobotsRule:
    allow: bool
    path: str
    pattern: re.Pattern[str]

    @classmethod
    def build(cls, allow: bool, path: str) -> "RobotsRule":
        decoded = unquote(path)
        anchored = decoded.endswith("$")
        body = decoded[:-1] if anchored else decoded
        regex = ".*".join(re.escape(part) for part in body.split(WILDCARD))
        return cls(allow=allow, path=decoded, pattern=re.compile(regex + ("$" if anchored else "")))

    def matches(self, path: str) -> bool:
        return self.pattern.match(path) is not None


@dataclass(frozen=True)
class RobotsRules:
    rules: tuple[RobotsRule, ...]
    allow_all: bool = False
    disallow_all: bool = False

    @classmethod
    def allowing_everything(cls) -> "RobotsRules":
        return cls(rules=(), allow_all=True)

    @classmethod
    def disallowing_everything(cls) -> "RobotsRules":
        return cls(rules=(), disallow_all=True)

    @classmethod
    def for_status(cls, status_code: int, body: str, product_token: str) -> "RobotsRules":
        if 200 <= status_code < 300:
            return cls.parse(body, product_token)
        if 400 <= status_code < 500:
            return cls.allowing_everything()
        return cls.disallowing_everything()

    @classmethod
    def parse(cls, text: str, product_token: str) -> "RobotsRules":
        token = product_token.lower()
        groups: list[tuple[set[str], list[RobotsRule]]] = []
        agents: set[str] = set()
        rules: list[RobotsRule] = []
        in_rules = False

        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.lower()

            if field == "user-agent":
                if in_rules:  # A user-agent line after rules starts a new group.
                    groups.append((agents, rules))
                    agents, rules, in_rules = set(), [], False
                agents.add(value.lower())
            elif field in ("allow", "disallow") and agents:
                in_rules = True
                if value:  # An empty Disallow allows everything: no rule.
                    rules.append(RobotsRule.build(field == "allow", value))

        if agents:
            groups.append((agents, rules))

        specific = [rule for group_agents, group_rules in groups if token in group_agents for rule in group_rules]
        if any(token in group_agents for group_agents, _ in groups):
            return cls(rules=tuple(specific))
        return cls(rules=tuple(
            rule for group_agents, group_rules in groups if WILDCARD in group_agents for rule in group_rules
        ))

    def can_fetch(self, url: str) -> bool:
        if self.disallow_all:
            return False
        if self.allow_all:
            return True

        parts = urlsplit(url)
        path = unquote(parts.path or "/") + (f"?{unquote(parts.query)}" if parts.query else "")
        matching = [rule for rule in self.rules if rule.matches(path)]
        if not matching:
            return True

        # Longest path wins; for equal lengths allow (True) sorts above disallow (False).
        best = max(matching, key=lambda rule: (len(rule.path), rule.allow))
        return best.allow
