"""Deterministic subset of .documentation/event-sources.md.

Unmatched events use the documented residual bucket; no paid LLM fallback.
"""

SOURCE_TYPES = {
    "music_performance": ("performance",),
    "art_film_exhibits": ("exhibitions", "film and media screenings"),
    "festivals_seasonal": ("fair/festival",),
    "talks_panels": ("lecture/talk/panel", "speaker/lecture series", "seminar",
                     "conference/symposium", "conversation", "town hall or forum",
                     "speaker event", "alumni panel", "presentation"),
    "workshops_skills": ("training/workshop", "workshop", "training session"),
    "social_community": ("social", "book club", "competition/debate", "study break", "social event"),
    "sports_outdoors_wellness": ("sport/recreation", "health/wellness", "sporting event"),
    "service_civic": ("community service & volunteer", "fundraiser"),
    "faith_spirituality": ("spiritual/worship",),
    "campus_admin": ("orientation", "ceremony", "info session"),
}
HIDDEN = {"academic calendar", "due date or deadline", "office hours/drop in hours",
          "study hall", "rehearsal", "group meeting"}
CAREER = {"career", "employer event", "networking", "recruit", "internship",
          "job search", "recruiting skills", "consulting"}
KEYWORDS = (
    ("faith_spirituality", ("worship", "prayer", "interfaith")),
    ("festivals_seasonal", ("festival", "fair", "holiday")),
    ("career_networking", ("recruiting", "networking", "employer", "internship")),
    ("campus_admin", ("orientation", "commencement", "ceremony")),
    ("service_civic", ("volunteer", "volunteering", "fundraiser", "voting")),
    ("sports_outdoors_wellness", ("sport", "sports", "yoga", "hike", "beach", "wellness")),
    ("food_drink", ("tasting", "dining", "dinner")),
    ("music_performance", ("concert", "performance", "comedy", "dance")),
    ("art_film_exhibits", ("museum", "gallery", "exhibit", "screening")),
    ("workshops_skills", ("workshop", "training", "crafting")),
    ("talks_panels", ("lecture", "panel", "seminar", "conference")),
)


def classify(categories, text):
    """Return (category, method); None category means not discoverable."""
    import re

    signals = {re.sub(r"\s*\(event_(?:type|tags?)\)$", "", c.casefold()).strip()
               for c in categories}
    if signals & HIDDEN:
        return None, "mapping"
    if signals & CAREER:
        return "career_networking", "mapping"
    matches = {slug for slug, values in SOURCE_TYPES.items() if signals.intersection(values)}
    if len(matches) == 1:
        return matches.pop(), "mapping"
    words = set(re.findall(r"\w+", text.casefold()))
    for slug, keywords in KEYWORDS:
        if words.intersection(keywords):
            return slug, "keyword"
    return "social_community", "default"
