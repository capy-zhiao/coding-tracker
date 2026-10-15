"""Fetch LeetCode study plans into data/<plan>.json.

The study plan pages are rendered client-side, so this asks LeetCode's public GraphQL API
for the same data the pages load. Re-run it if LeetCode changes a plan.

    python3 scripts/fetch_study_plans.py
"""
import json
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
PLANS = {                       # LeetCode slug -> output file
    "top-interview-150": "top_interview_150.json",
    "leetcode-75": "leetcode_75.json",
}
QUERY = """query studyPlanDetail($slug: String!) {
  studyPlanV2Detail(planSlug: $slug) {
    name
    planSubGroups { name questions { questionFrontendId title titleSlug difficulty } }
  }
}"""


def fetch(slug: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"slug": slug}}).encode()
    req = urllib.request.Request(
        "https://leetcode.com/graphql", data=body,
        headers={"Content-Type": "application/json",
                 "Referer": f"https://leetcode.com/studyplan/{slug}/",
                 # LeetCode answers 403 to urllib's default "Python-urllib/x.y" agent
                 "User-Agent": "Mozilla/5.0 (coding-tracker study-plan fetch)"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]["studyPlanV2Detail"]


def main() -> None:
    for slug, filename in PLANS.items():
        plan = fetch(slug)
        problems = []
        for group in plan["planSubGroups"]:
            for q in group["questions"]:
                problems.append({
                    "position": len(problems),        # order within the study plan
                    "number": int(q["questionFrontendId"]),
                    "title": q["title"],
                    "slug": q["titleSlug"],
                    "difficulty": q["difficulty"].capitalize(),
                    "group": group["name"],
                })
        out = DATA / filename
        out.write_text(json.dumps({"plan": plan["name"], "slug": slug, "count": len(problems),
                                   "problems": problems}, indent=2) + "\n")
        print(f"{plan['name']}: {len(problems)} problems -> {out.name}")


if __name__ == "__main__":
    main()
