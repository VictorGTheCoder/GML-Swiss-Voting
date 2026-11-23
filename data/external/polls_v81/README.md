# V8.1 poll inputs

**Exploratory only**, no historical edition certified. The production polls
and models are untouched. No outcome, winner or retrospective accuracy column
is copied from any report.

- `leewas_latest_2016_2022.csv`: numerical latest yes shares from LeeWas,
  *20 Minuten-/Tamedia-Abstimmungsumfrage*, 9 June 2024 vote, second wave,
  embargo 29 May 2024. Tables 43 and 44, printed pages 53–54.
  Source: https://leewas.ch/wp-content/uploads/2024/05/bericht_welle_2_adobe.pdf
  The body states these are the latest published surveys before each historic
  vote. The exact historical release time and version are not independently
  verified. The first numerical column is Tamedia, the second SRG;
  this is independently checked against the 48 existing directly collected
  last-wave SSR observations. One missing SSR margin is explicit (FPMG).
  The object mapping is checked against Swissvotes metadata only. Table 43
  reorders certain objects within voting dates; do not infer from row number.
  PDF screenshots were attempted but unavailable; values transcribed from
  accessible text and checked against existing national poll observations.
  Source discrepancies remain visible and never overwrite stronger sources.
- `srg_missing_two_waves.csv`: 17 two-wave pairs for all currently missing
  SRG-polled development objects. Values are YES shares only; no invented
  undecided/no shares. Contemporary SRG/SWI publications and institute reports
  before the vote, exact URL per pair. Previous-wave values may be reconstructed
  arithmetically from explicitly published point changes in the second wave
  (Feb 2016, service public, Asylgesetz, Geldspielgesetz). Midpoints are
  reported when available, otherwise floor of fieldwork interval as noted.
  Source reports: Feb 2016 table 1 and reference days 12 Jan / 9 Feb;
  June 2018 table 1, technical table 2. June 2016 intervals Apr 18–23,
  May 13–21. Sept 2016 Aug 2–12, Aug 31–Sep 8. Feb 2017 Dec 19–30,
  Jan 18–25. June 2018 Apr 16–26 and May 20 reported. Feb 2019 Dec 7
  reported, Jan 16–23 interval. The second-wave document is the actual
  publication boundary for a pair recovered from that document.
  Values latest from primary take precedence over retrospective conflicts
  (notably Pro Service public, 46 instead of 40); no SSR poll existed
  for FPMG as confirmed by SWI May 2016.
- Dates and title mappings validated from an allowlisted metadata projection
  of local Swissvotes. All 66 development objects retained. No results 2023+
  enter model evaluation; both files deliberately restricted to 2016–2022.
