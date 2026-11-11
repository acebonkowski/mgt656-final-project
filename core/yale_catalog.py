"""Provisional degree-level choices, not a complete list of specializations.

Source: https://catalog.yale.edu/ycps/work-of-yale-university/ (2026–27).
Reviewed 2026-11-10. Graduate/professional audience: excludes Yale College.
Cross-school degrees appear under each school where the source lists them;
the listed school is the student's affiliation, not necessarily the awarding school.
Team approval remains pending. No external request is needed to seed the catalog.
"""

CATALOG = {
    "Graduate School of Arts and Sciences": ["Master of Arts (M.A.)", "Master of Science (M.S.)", "Master of Philosophy (M.Phil.)", "Doctor of Philosophy (Ph.D.)"],
    "School of Medicine": ["Doctor of Medicine (M.D.)", "Medicine / Health Science (M.D./M.H.S.)", "Medicine / Philosophy (M.D./Ph.D.)", "Physician Associate (M.M.Sc.)", "Physician Assistant Online (M.M.Sc.)"],
    "Divinity School": ["Master of Divinity (M.Div.)", "Master of Arts in Religion (M.A.R.)", "Master of Sacred Theology (S.T.M.)"],
    "Law School": ["Juris Doctor (J.D.)", "Master of Laws (LL.M.)", "Doctor of the Science of Law (J.S.D.)", "Master of Studies in Law (M.S.L.)", "Doctor of Philosophy (Ph.D.)"],
    "School of Engineering & Applied Science": ["Master of Science (M.S.)", "Doctor of Philosophy (Ph.D.)"],
    "School of Art": ["Master of Fine Arts (M.F.A.)"],
    "School of Music": ["Certificate in Performance", "Master of Music (M.M.)", "Master of Musical Arts (M.M.A.)", "Artist Diploma", "Doctor of Musical Arts (D.M.A.)"],
    "School of the Environment": ["Master of Forestry (M.F.)", "Master of Forest Science (M.F.S.)", "Master of Environmental Science (M.E.Sc.)", "Master of Environmental Management (M.E.M.)", "Doctor of Philosophy (Ph.D.)"],
    "School of Public Health": ["Master of Public Health (M.P.H.)", "Master of Science (M.S.)", "Doctor of Philosophy (Ph.D.)"],
    "School of Architecture": ["Master of Architecture (M.Arch.)", "Master of Environmental Design (M.E.D.)", "Doctor of Philosophy (Ph.D.)"],
    "School of Nursing": ["Master of Science in Nursing (M.S.N.)", "Post Master's Certificate", "Doctor of Nursing Practice (D.N.P.)", "Doctor of Philosophy (Ph.D.)"],
    "David Geffen School of Drama": ["Master of Fine Arts (M.F.A.)", "Certificate in Drama", "Doctor of Fine Arts (D.F.A.)"],
    "School of Management": ["Master of Business Administration (M.B.A.)", "Master of Advanced Management (M.A.M.)", "Master of Management Studies (M.M.S.)", "Doctor of Philosophy (Ph.D.)"],
    "Jackson School of Global Affairs": ["Master in Public Policy (M.P.P.)", "Master of Advanced Study (M.A.S.)"],
}


def seed_catalog():
    from core.models import Program, School

    # Retain old development rows for recovery and existing references, but hide
    # them from the selectable catalog. Never remove student data during seeding.
    School.objects.filter(name__in=["Sample school A — local demo", "Sample school B — local demo"]).update(is_active=False)
    for name, degrees in CATALOG.items():
        school, _ = School.objects.update_or_create(name=name, defaults={"is_active": True})
        for degree in degrees:
            Program.objects.get_or_create(school=school, name=degree)
