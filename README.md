# project-nightfall

### Summary
A data-driven supply chain insights generator for the Philippines, designed to navigate its unique geographic and climate challenges. It produces actionable insights on the best course of action over a period of months and years, based on satellite and mobility data.

### Problem Statement
Businesses in the Philippines often take losses as a given during every typhoon season, absorbing the financial hit. Without a reliable way to understand the intersection of weather patterns and the entire supply chain, businesses are essentially flying blind.

### Success Metrics
* **Improved Decision-Making:** Businesses making better monthly and seasonal decisions regarding crops, logistics, and manning.
* **Loss Reduction:** A measurable decrease in overall losses attributed to weather, geography, and movement inefficiencies.

## Scope and Objectives

### Core Deliverables

**1. Data Aggregation**
* Weather patterns and forecasts.
* Supply chain routing.
* Mobility (Flight and ship paths).
* Approximate population density (Using standard WorldPop data and satellite night light data for visual effects).

**2. Insights Generation**
* Optimal timelines for planting crops.
* Strategic manpower allocation timing.
* Recommendations on which logistics methodology to utilize.
* Typhoon preparation protocols.
* Identification of underutilized or isolated markets.

**3. Web Application**
* Interactive map of the target site and nearby cities.
* Animation of all converging factors (weather, mobility, density).

### Out-of-Scope
* Paid version of data of any kind. Project strictly uses public or free tier data.
* Validation of the data against official census records.
* Guarantees on the absolute accuracy of the generated results.
* Use of LLMs to make autonomous key business decisions.
* Advanced satellite data processing (e.g., SAR - Synthetic Aperture Radar).
* Primary customer interviews.
* Mobile application version.

### Key Dependencies
* Reliable access to satellite data (including night imagery).
* Access to flight and ship path data.
* Access to historical and live weather data APIs.

## Implementation Details

### Technology Stack
* **Frontend:** To be decided.
* **Backend:** To be decided.
* **Database & Storage:** To be decided.
* **Infrastructure:** To be decided.

### System Architecture
To be decided.

### Risks and Mitigations
* **Risk:** Processing and animating multiple heavy spatial datasets (mobility paths + weather + nightlights) can cause severe UI lag and browser crashing.
  * **Mitigation:** To be decided.
* **Risk:** API rate limits or downtime from weather/flight data dependencies.
  * **Mitigation:** To be decided.

## Milestones

* **Phase 1 (Map Generation and Initial Data Overlay):** Develop the core web app with a free ship and flight path data overlay.
* **Phase 2 (Secondary and Live Data Overlay):** Estimate population additions from WorldPop (with Satellite Nightlight visualization) and overlay live weather data onto the map.
* **Phase 3 (Processing and Insights Generation):** Generate useful business insights from the available data. Ensure insights are configurable per specific site.
* **Phase 4 (Testing & Launch):** Conduct quality assurance, refine rendering performance, execute deployment, and gather initial user feedback.
