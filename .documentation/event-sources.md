# Event Category Framework

Spec for categorizing imported Yale and New Haven events. Companion to `event-sources.md`. Written 2026-11-15.

## Principle

Each event gets **exactly one primary category**, chosen by what the attendee **mainly does**. Everything else (format, audience, cost, host, topic) is a separate **filter**, never a category. Do not reuse any source's own categories directly: they mix activity, format, audience and host in one list.

## Primary categories (12)

| Group | Slug | Label | Attendee mainly... | Examples |
|---|---|---|---|---|
| Culture | `music_performance` | Music & Performance | watches or joins a live performance | concert, play, dance, comedy, a cappella, open mic, spoken word |
| Culture | `art_film_exhibits` | Art, Film & Exhibits | views art, film or exhibits | exhibition, screening, guided museum or gallery tour |
| Culture | `festivals_seasonal` | Festivals & Seasonal | attends a named multi-activity festival, fair, market or holiday event | International Festival of Arts & Ideas, Firelight Festival |
| Learning & Career | `talks_panels` | Talks & Panels | listens and discusses | lecture, panel, speaker series, seminar, conference, reading |
| Learning & Career | `workshops_skills` | Workshops & Skills | practices something hands-on | writing workshop, crafting class, training session |
| Learning & Career | `career_networking` | Career & Networking | pursues jobs, recruiting or professional contacts | recruiting bootcamp, alumni networking, employer event |
| Social & Lifestyle | `social_community` | Social & Community | hangs out. **Default/residual bucket** | mixers, trivia, game nights, cultural celebrations, study breaks |
| Social & Lifestyle | `food_drink` | Food & Drink | comes for the food or drink | tastings, dining events |
| Social & Lifestyle | `sports_outdoors_wellness` | Sports, Outdoors & Wellness | plays or watches sport, exercises, hikes, does a wellness practice | game, yoga, hike, beach trip, peer support |
| Community & Campus | `service_civic` | Service, Civic & Advocacy | volunteers, fundraises, takes part in civic life | volunteering, fundraiser, voting drive |
| Community & Campus | `faith_spirituality` | Faith & Spirituality | worships or studies together | services, prayer, interfaith events |
| Community & Campus | `campus_admin` | Campus & Admin | handles official university business | orientation, commencement, official info sessions |

## Decision order (first match wins)

This order makes the categories mutually exclusive. The fallback (step 12) makes them collectively exhaustive.

0. **Not a discoverable event** (deadline, academic calendar entry, rehearsal, office hours, study hall, exam, closed group meeting): set `is_discoverable = false`. No category shown.
1. Worship or prayer: `faith_spirituality`
2. Named multi-activity festival, fair or holiday event: `festivals_seasonal`
3. Main purpose is jobs, recruiting or professional networking: `career_networking`
4. Orientation, ceremony or official university info session: `campus_admin`
5. Volunteering, fundraising, advocacy or voting: `service_civic`
6. Sport, fitness, outdoors or wellness practice: `sports_outdoors_wellness`
7. Food or drink is the main draw: `food_drink`
8. Live performance: `music_performance`
9. Exhibit, gallery, museum tour or screening: `art_film_exhibits`
10. Hands-on skill-building: `workshops_skills`
11. Listening or discussion: `talks_panels`
12. Everything else: `social_community`

## Filters (separate fields, combinable)

| Filter | Values | Notes |
|---|---|---|
| Format | in_person / online / hybrid | Yale Connect Location Type: On-Campus Room Reservation, Other Location, Online Only, Hybrid |
| Audience | open_to_all / undergrad / grad_professional / international / family_friendly | Yale tags cover class years, First Generation, Graduate Students. Ticketmaster has a `family` boolean |
| Cost | free / paid | Ticketmaster price or event text |
| Host | university / school / student_org / city_venue | Derived from the import source |
| When | today, this weekend, evening | Derived from `starts_at` |
| Topic tags | optional, free-form | e.g. Sustainability, Entrepreneurship |

## Django model

```python
class EventCategory(models.TextChoices):
    MUSIC_PERFORMANCE = "music_performance", "Music & Performance"
    ART_FILM_EXHIBITS = "art_film_exhibits", "Art, Film & Exhibits"
    FESTIVALS_SEASONAL = "festivals_seasonal", "Festivals & Seasonal"
    TALKS_PANELS = "talks_panels", "Talks & Panels"
    WORKSHOPS_SKILLS = "workshops_skills", "Workshops & Skills"
    CAREER_NETWORKING = "career_networking", "Career & Networking"
    SOCIAL_COMMUNITY = "social_community", "Social & Community"
    FOOD_DRINK = "food_drink", "Food & Drink"
    SPORTS_OUTDOORS_WELLNESS = "sports_outdoors_wellness", "Sports, Outdoors & Wellness"
    SERVICE_CIVIC = "service_civic", "Service, Civic & Advocacy"
    FAITH_SPIRITUALITY = "faith_spirituality", "Faith & Spirituality"
    CAMPUS_ADMIN = "campus_admin", "Campus & Admin"
```

Event fields: `category` (EventCategory, single value), `is_discoverable` (bool, default true), `format`, `audience` (multi), `is_free` (nullable bool), `tags` (multi). Keep the raw source category values in the `raw` JSON field for debugging.

## Source mapping (importer step 1)

### Yale Connect (`ical_yale.ics`) and SOM: read from CATEGORIES (`event_type`, `event_tags`)

| Yale Connect `event_type` | Category |
|---|---|
| Performance | `music_performance` |
| Exhibitions, Film and Media Screenings | `art_film_exhibits` |
| Fair/Festival | `festivals_seasonal` |
| Lecture/Talk/Panel, Speaker/Lecture Series, Seminar, Conference/Symposium, Conversation, Town Hall or Forum | `talks_panels` |
| Training/Workshop | `workshops_skills` |
| Social, Book Club, Competition/Debate | `social_community` |
| Sport/Recreation, Health/Wellness | `sports_outdoors_wellness` |
| Community Service & Volunteer, Fundraiser | `service_civic` |
| Spiritual/Worship | `faith_spirituality` |
| Orientation, Ceremony, Info Session | `campus_admin` |
| Tour, Trip/Trek/Retreat | keyword: museum/gallery/art -> `art_film_exhibits`; hike/beach/game/sport -> `sports_outdoors_wellness`; else `social_community` |
| Academic Calendar, Due Date or Deadline, Office Hours/Drop in Hours, Study Hall, Rehearsal, Group Meeting | `is_discoverable = false` |
| Yale & New Haven | no signal: use tags and keywords |

**Tag override:** if tags include Career, Employer Event, Networking, Recruit, Internship or Job Search, set `career_networking` (this includes Info Sessions).

**SOM:** `event_type` describes the host or occasion (School Event, Club Event, Speaker Event, Alumni-Student Event, Student Government Event, Student Life Event, Study Break), not the activity. Ignore it except Speaker Event -> `talks_panels` and Study Break -> `social_community`. Use tags instead: Career, Recruiting Skills, Consulting, Networking -> `career_networking`; Workshop, Training Session -> `workshops_skills`; Alumni Panel, Presentation -> `talks_panels`; Sporting Event -> `sports_outdoors_wellness`; Social Event -> `social_community`.

### Ticketmaster
Segment Music, Arts & Theatre -> `music_performance`. Film -> `art_film_exhibits`. Sports -> `sports_outdoors_wellness`. Miscellaneous -> by genre or keyword. The full segment list is unconfirmed: call `/discovery/v2/classifications.json` with a real key and update this table.

### Arts Council / INFO New Haven (if ever imported)
Performing Arts, Concerts & Live Music, Open Mic & Jam Sessions -> `music_performance`. Visual Arts -> `art_film_exhibits`. Literary Arts -> `talks_panels` (poetry slams -> `music_performance`). Crafting Workshops -> `workshops_skills`. Hobbyist Meetups, Community & Family, Cultural & International -> `social_community`. Outdoors & Nature, Fitness/Health & Wellness -> `sports_outdoors_wellness`. Food & Drink, Culinary Events -> `food_drink`. Civic & Service Organizations -> `service_civic`. Seasonal & Holiday -> `festivals_seasonal`.

### Visit New Haven and Localist
Visit New Haven has no event categories: classify by keyword or LLM. Localist (events.yale.edu) event types were not seen because the site blocked my fetch. Map them before using that adapter.

## Classifier pipeline

1. **Source mapping** from the tables above. Stop if it gives a confident, unambiguous result.
2. **Keyword overrides** applied in the decision order above (title, description, location text).
3. **LLM fallback** via OpenRouter, server-side only, for anything still ambiguous. Use structured output restricted to the 12 slugs plus `not_discoverable`. Never let the model return a free-form category.
4. **Eval set:** hand-label about 50 real events from the feeds (stored in `tests/fixtures/`), and assert accuracy in tests with the LLM mocked. Track the rate of events that reached step 3.
5. Store which step produced the category (`category_source`: `mapping`, `keyword` or `llm`) so mislabels can be traced.

## Caveats

- Built from the full Yale Connect filter list, but only the first ~100,000 characters of each ICS feed were sampled. The Yale sample was mostly international-student programming from Aug-Sep 2026, so tag counts are skewed.
- Arts Council / INFO New Haven categories were read from listing labels because their filter dropdowns did not render. The list may be incomplete.
- The 12-category cut and the decision order are design choices, not something the sources dictate. Candidate changes: fold Faith into Social & Community, or split Wellness from Sports.
