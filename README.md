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
* Approximate population density (Utilizing satellite night light data for visual effects rather than standard WorldPop data).

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
* **Frontend:** Next.js and Tailwind CSS for the web application UI. Deck.gl or Mapbox GL JS for rendering high-performance animated map overlays.
* **Backend:** Python with FastAPI for handling heavy data processing, insights generation, and serving APIs. 
* **Database & Storage:** PostgreSQL with the PostGIS extension for spatial data querying, and Supabase for authentication and real-time database syncing. BigQuery for storing and querying massive datasets (like historical mobility and weather logs).
* **Infrastructure:** Docker for containerization to ensure consistency across environments.

### System Architecture
A containerized microservices architecture. Python worker scripts will handle the scheduled ingestion and processing of satellite nightlight and weather data, converting them into optimized spatial formats (like GeoJSON). The Next.js frontend will query the PostgreSQL and BigQuery databases via the FastAPI backend to dynamically generate site-specific insights and render the animated mapping interface on the client side.

### Risks and Mitigations
* **Risk:** Processing and animating multiple heavy spatial datasets (mobility paths + weather + nightlights) can cause severe UI lag and browser crashing.
  * **Mitigation:** Pre-process spatial data on the backend using Python (Pandas/GeoPandas) and serve lightweight, simplified GeoJSON vector tiles to the frontend rather than raw data. 
* **Risk:** API rate limits or downtime from weather/flight data dependencies.
  * **Mitigation:** Implement a robust caching layer for historical data and fallback protocols if live feeds fail.

## Milestones

* **Phase 1 (Map Generation and Initial Data Overlay):** Develop the core web app with a free ship and flight path data overlay.
* **Phase 2 (Secondary and Live Data Overlay):** Estimate population additions from satellite nightlight data and overlay live weather data onto the map.
* **Phase 3 (Processing and Insights Generation):** Generate useful business insights from the available data. Ensure insights are configurable per specific site.
* **Phase 4 (Testing & Launch):** Conduct quality assurance, refine rendering performance, execute deployment, and gather initial user feedback.
