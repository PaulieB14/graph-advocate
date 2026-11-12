"""Guard: the free-tier story must be one rule everywhere (see a2a_server llms.txt 'What is free')."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).parent
FILES = ["a2a_server.py", "README.md", "CLAUDE.md", "erc8004-registration.json",
         "docs/route.mdx", "docs/quickstart.mdx", "docs/index.mdx", "docs/REFERENCE.md", "docs/X402-USAGE.md",
         "docs/AGENTVERSE_README.md", "openclaw-skill/graph-advocate/SKILL.md",
         "plugins/graph-advocate/skills/graph-advocate/SKILL.md"]
# Phrases that contradicted the code: /route has no daily quota; the A2A quota is 3, never 10.
BANNED = [r"free /route\s+queries", r"free-tier users \(10/day\)", r"10 queries\s*/\s*sender", r"free tier is 10 calls",
          r"3 free /route", r"/route\s+\|\s+free 3/day"]


class TestFreeTierCopy(unittest.TestCase):
    def test_no_contradicting_phrases(self):
        for f in FILES:
            text = (ROOT / f).read_text(encoding="utf-8")
            for pat in BANNED:
                self.assertIsNone(re.search(pat, text, re.I), f"{f}: {pat}")

    def test_cdp_description_within_limit(self):
        text = (ROOT / "a2a_server.py").read_text(encoding="utf-8")
        m = re.search(r'description=\(\s*"Onchain data router for AI agents\. Plain-English question(.*?)\),\s*mime_type', text, re.S)
        self.assertIsNotNone(m)
        desc = "Onchain data router for AI agents. Plain-English question" + "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
        self.assertLessEqual(len(desc), 500)


if __name__ == "__main__":
    unittest.main()
