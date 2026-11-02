# Project Proposal MGT 656 Final Project

**Team:**Gowri Balagopal Warrier, Harshita Srivastava, Khushbu Dhingra, Tung Trinh, Ace Bonkowski
**Due:** Monday, November 2, 2026, 11:59pm

Three project ideas, ranked by preference.

| Rank | Idea | Tagline |
|------|------|---------|
| 1 | Event App | Event discovery app for Yale graduate students |
| 2 | Ridesharing App | [_one-line tagline_]|
| 3 | Coffee App | A café discovery app helping New Haven students and residents find cafés based on coffee preferences, purpose of visit, and atmosphere |

---

## Priority 1: Event App

### 1. Tagline
> Event discovery app for Yale graduate students

### 2. Major User Journeys

**Journey A: As a Yale graduate student looking to attend an event,**
1. I sign up, login and see a map of New Haven will different types of events and filtering options.
2. I filter the shown events to reflect my preferred event type and time.
3. I read the event details of suggestions that interest me and share the one I like most with my friends. 
4. Result: My friends and me are going out this weekend.

**Journey B: As a event organizer**
1. I sign up, log in and see a button to add my event.
2. I create the event page, fill out all its details, add photos and add any relevant links.
3. I submit the event so it shows up on the map and share the event link across Social Media.
4. Result: The event I wanted to host has super many super cool guests. 

### 3. Core Features (MVP, 3-5)

1. **Registration & Login:** Users need to create an account to persistently store relevant data with their profile and to manage platform access controls (event & attendance visibility). Each attendee account needs a username, email, password, profile photo, and degree program. Each
2. **Event Search:** Users can search for events by text input, time, event type, price, and whether the event is attended by friends
3. **Event Creation:** Users can create events by adding the event data (name, date, time, location, description, price, category) and a visual to the event before publishing it.
4. **Community:** Users can add their friends via their email or username to see the events they are going to and invite them to events. They can also add their friends as co-editors of the event page. Users can share events both in & outside of the app.

**Deliberately skipped for the MVP:**
- Yale Auth Flow: Integration of sign in via Yale NetID is likely too technically/administratively complex
- Payment Flow for Business Organizers: interesting for monetization but not to demonstrate the ID
- Ticket Booking: Payment integration for paid events exceeds scope and would likely require coordination with external vendors

### 4. AI Feature

- **What the LLM does for the user:** Autofill event creation form
- **Input:** Event characteristics key:value pairs & text input
- **Output:** A generated event visual & filled out event creation form
- **Why an LLM (vs. plain code or a database query):** The friction of filling out the form can only be effectively lowered by generating new content (text + image) based on user input (e.g., the categories & description) that is likely to match what the user wants.
- **Failure mode / fallback:** Error notification appears, form has to be filled out manually & instead of generating a visual, the img is the event category's icon if empty.

---

## Priority 2: Ridesharing App

### 1. Tagline
> ...

### 2. Major User Journeys

**Journey A: As a [rider]**
1. ...

**Journey B: As a [driver]**
1. ...

**Journey C (optional): As an admin**
1. ...

### 3. Core Features (MVP, 3-5)

1. **Feature 1:** ...
2. **Feature 2:** ...
3. **Feature 3:** ...

**Deliberately skipped for the MVP:**
- ...

### 4. AI Feature

- **What the LLM does for the user:** ...
- **Input:** ...
- **Output:** ...
- **Why an LLM:** ...
- **Failure mode / fallback:** ...

---

## Priority 3: Coffee App

### 1. Tagline
> A café discovery app helping New Haven students and residents find cafés based on coffee preferences, purpose of visit, and atmosphere.

### 2. Major User Journeys

**Journey A: As a student or remote worker looking for a café**
1. I open the café directory and search for a place to study or work, specifying preferences such as quiet seating, reliable Wi-Fi, outlets, and proximity to Yale.
2. I review matching cafés, compare their amenities, atmosphere ratings, opening hours, and recent community-reported busyness.
3. I open a café profile to read reviews and choose a location that fits my plans.

**Journey B: As a coffee enthusiast or visitor**
1. I browse cafés or search for a preferred drink (such as a cold brew or oat milk latte) and the type of visit I have in mind (such as a date or casual meetup).
2. I compare cafés based on available drinks, overall coffee ratings, atmosphere, and customer reviews.
3. After visiting, I log in to submit a coffee and space review that helps other users discover the café.
4. If I notice a discrepancy in review or café details, I will tap "Report this" and select a reason which will be sent to admin for review

**Journey C: As a customer checking in**
1. I log in and open the profile of the café I am visiting.
2. I submit a one-tap report of its current busyness (quiet, moderately busy, or crowded).
3. I receive confirmation that my check-in has been submitted.
4. Other visitors can view recent community-reported busyness information when deciding whether to visit.

**Journey D: As a Café Admin**
1. I log in to the café administration interface to manage listings and user-generated content.
2. I add new cafés or update existing details, including operating hours, locations, amenities, and drink offerings.
3. I review user-reported inaccuracies flagged through "Report this" or inappropriate reviews and decide whether corrections or removals are needed.
4. I approve and publish changes so users see updated café information and appropriate reviews.

### 3. Core Features (MVP)

1. **Café profiles and directory:** A curated directory of approximately 25–30 New Haven cafés, featuring locations, hours, drink selections, amenities, and in-app community ratings. Each café is stored with its latitude and longitude, along with a short list of common landmarks (e.g., Yale SOM, Sterling Library, Union Station), so the app can calculate distance and support “near X” searches without an interactive map. Data source- Admin-entered, Rating scores from users
2. **Search and filtering:** Browse cafés using keyword search and filters for location, opening hours, drinks, noise level, Wi-Fi, purpose of visit, atmosphere and outlets; natural-language search is the AI-powered alternative. Data source- both users/crowd-sourced and admin-entered
3. **Space and coffee reviews:** Signed-in users rate overall coffee quality, seating, noise, Wi-Fi, and outlet availability and can write short reviews. Café-level ratings take priority over individual drink ratings. Users can flag inappropriate reviews or incorrect café details with a “Report this” button; flagged items go to an admin queue. Data source- Crowd sourced
4. **User accounts:** Sign up and log in to submit reviews and check-ins and view personal review history; basic café administration uses Django's built-in admin tools. Data source- User-entered (sign-up details)
5. **Community-reported busyness:** One-tap, timestamped check-ins report how busy a café feels. Show recent reports and, where sufficient data exists, aggregated patterns by time of day; otherwise show an explicit insufficient-data flag. These are community estimates, not live occupancy or confirmed seat availability. Data-source- Crowd-sourced

**Deliberately skipped for the MVP:**
- Google Reviews integration: A potential stretch feature; external review access and display add API and compliance complexity. MVP ratings come from in-app users.
- Individual drink ratings and leaderboards: Café-level coffee ratings and a curated list of drink offerings are sufficient initially.
- Photos, interactive maps, reservations, orders/payments, and loyalty rewards: Additional storage, integrations, or workflows that are not necessary to validate the core discovery experience.
- AI-generated review summaries: A possible later enhancement; the MVP focuses on an AI-powered search capability that interprets users’ natural-language requirements and converts them into structured filters to retrieve relevant cafés from the database.

### 4. AI Feature

- **What the LLM does for the user:** Translates conversational café requests into structured search filters that the app uses to find matching cafés.
- **Input:** A free-text request such as "Find a quiet café near Yale SOM with Wi-Fi, outlets, oat milk, and hours after 7 PM," alongside supported filter definitions.
- **Output:** Validated filters (e.g., quiet atmosphere, near Yale SOM, Wi-Fi, outlets, oat milk, open after 7 PM) are applied to the café database; the user sees matching café profiles and ratings, not invented recommendations.
- **Why an LLM:** Users can describe several needs and occasions in everyday language rather than translating each preference into separate filters. The LLM interprets the request; database queries still determine actual matches.
- **Failure mode / fallback:** Validate the LLM's structured output before running a query. If it produces unsupported filters, no matches, or an API error, explain the limitation and offer regular keyword search and manual filters.

---

## Submission Checklist

- [ ] All 3 ideas have: tagline, user journeys, 3-5 core features, AI feature
- [ ] Ideas are ranked by preference (1 = most wanted)
- [ ] Every journey names a concrete user role and concrete screens/actions
- [ ] Every AI feature is something only an LLM can reasonably do
- [ ] Document is hosted on GitHub (or Google Docs) with a shareable URL
- [ ] URL submitted before 11:59pm ET on Nov 2, 2026
