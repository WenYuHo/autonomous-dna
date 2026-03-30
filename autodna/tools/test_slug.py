
import sys
from autodna.tools.research import slugify_topic

topics = [
    "how to use agent browser for research",
    "what is the difference between playwright and selenium",
    "researching autonomous dna patterns"
]

for t in topics:
    slug = slugify_topic(t)
    print(f"Topic: {t} -> Slug: {slug} (Len: {len(slug)})")
