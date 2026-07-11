# Campaign 27 Product Spec (V7.1)

A posting-level Summer 2027 internship matcher for Ahaan Anand.

## Non-negotiables
- Unit of prediction is ONE EXACT POSTING, never a company.
- Eligibility is a HARD GATE (posting language), not a weighted score.
- No interview probability is published until a lane has 20+ logged outcomes; everything else is PRIOR_ONLY and labelled.
- No point ranks. Group by eligibility state + fit tier only.
- Headline is a portfolio curve (apply to top N → expected interviews) with honest bands.
- Heavy computation stays in scripts writing JSON; the frontend is a thin viewer.

## Sections
Portfolio (headline curve), Matches (grouped, never ranked), Model (robustness bake-off),
Companies (162 target list), Network (LinkedIn layer), Method (ground rules).
