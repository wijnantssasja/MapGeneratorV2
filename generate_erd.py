import os
import subprocess

svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1620 1140" width="1620" height="1140" style="background-color: #0b1120; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <defs>
    <filter id="shadow" x="-5%" y="-5%" width="110%" height="110%">
      <feDropShadow dx="0" dy="8" stdDeviation="6" flood-color="#000000" flood-opacity="0.5" />
    </filter>
    <linearGradient id="grad-red" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ef4444" />
      <stop offset="100%" stop-color="#b91c1c" />
    </linearGradient>
    <linearGradient id="grad-blue" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#3b82f6" />
      <stop offset="100%" stop-color="#1d4ed8" />
    </linearGradient>
    <linearGradient id="grad-teal" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#14b8a6" />
      <stop offset="100%" stop-color="#0f766e" />
    </linearGradient>
    <linearGradient id="grad-purple" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#a855f7" />
      <stop offset="100%" stop-color="#7e22ce" />
    </linearGradient>
    <linearGradient id="grad-amber" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b" />
      <stop offset="100%" stop-color="#b45309" />
    </linearGradient>
    <linearGradient id="grad-slate" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#475569" />
      <stop offset="100%" stop-color="#1e293b" />
    </linearGradient>
    
    <!-- Markers for Relational Lines -->
    <marker id="dot-blue" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6">
      <circle cx="5" cy="5" r="4" fill="#38bdf8" />
    </marker>
    <marker id="arrow-blue" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 1 2 L 8 5 L 1 8 z" fill="#38bdf8" />
    </marker>
    <marker id="dot-red" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6">
      <circle cx="5" cy="5" r="4" fill="#f87171" />
    </marker>
    <marker id="arrow-red" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 1 2 L 8 5 L 1 8 z" fill="#f87171" />
    </marker>
  </defs>

  <!-- Canvas Grid Background -->
  <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
    <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="1" opacity="0.4"/>
  </pattern>
  <rect width="100%" height="100%" fill="url(#grid)" />

  <!-- Diagram Title Header -->
  <rect x="50" y="30" width="1520" height="70" rx="12" fill="#1e293b" stroke="#334155" stroke-width="1.5" filter="url(#shadow)"/>
  <text x="80" y="66" fill="#f8fafc" font-size="22" font-weight="700">Rode Kruis-Vlaanderen Map Generator — Database ERD</text>
  <text x="80" y="87" fill="#94a3b8" font-size="13">PostgreSQL + PostGIS Ruimtelijk Datamodel | SQLAlchemy ORM &amp; GeoAlchemy2</text>
  
  <rect x="1350" y="47" width="190" height="34" rx="8" fill="#d32f2f" />
  <text x="1445" y="69" fill="#ffffff" font-size="13" font-weight="700" text-anchor="middle">RELATIONAL SCHEMA</text>

  <!-- ================= RELATIE LIJNEN ================= -->
  <g stroke-width="2.2" fill="none">
    <!-- REGIONS -> CLUSTERS -->
    <path d="M 210 280 L 210 370" stroke="#38bdf8" marker-start="url(#dot-blue)" marker-end="url(#arrow-blue)" />

    <!-- REGIONS -> DEPARTMENTS -->
    <path d="M 370 200 L 450 200 L 450 290 L 530 290" stroke="#38bdf8" marker-start="url(#dot-blue)" marker-end="url(#arrow-blue)" />

    <!-- CLUSTERS -> DEPARTMENTS -->
    <path d="M 370 450 L 450 450 L 450 460 L 530 460" stroke="#38bdf8" marker-start="url(#dot-blue)" marker-end="url(#arrow-blue)" />

    <!-- DEPARTMENTS -> VEHICLES -->
    <path d="M 850 260 L 910 260 L 910 220 L 970 220" stroke="#f87171" marker-start="url(#dot-red)" marker-end="url(#arrow-red)" />

    <!-- DEPARTMENTS -> MUNICIPALITIES -->
    <path d="M 530 680 L 450 680 L 450 680 L 370 680" stroke="#f87171" marker-start="url(#dot-red)" marker-end="url(#arrow-red)" />

    <!-- DEPARTMENTS -> DEPARTMENT_SHAPES -->
    <path d="M 690 770 L 690 840" stroke="#f87171" marker-start="url(#dot-red)" marker-end="url(#arrow-red)" />

    <!-- DEPARTMENTS -> DEPARTMENT_SERVICES -->
    <path d="M 850 640 L 910 640 L 910 600 L 970 600" stroke="#f87171" marker-start="url(#dot-red)" marker-end="url(#arrow-red)" />

    <!-- SERVICES -> DEPARTMENT_SERVICES -->
    <path d="M 1260 600 L 1210 600" stroke="#a855f7" marker-start="url(#dot-blue)" marker-end="url(#arrow-blue)" />

    <!-- SIT_LOCATIONS -> SIT_VEHICLES -->
    <path d="M 1220 280 L 1290 280" stroke="#f59e0b" marker-start="url(#dot-blue)" marker-end="url(#arrow-blue)" />
  </g>

  <!-- ================= TABELLEN ================= -->

  <!-- 1. REGIONS -->
  <g transform="translate(50, 130)" filter="url(#shadow)">
    <rect width="320" height="150" rx="10" fill="#1e293b" stroke="#3b82f6" stroke-width="1.5"/>
    <rect width="320" height="38" rx="10" fill="url(#grad-blue)"/>
    <rect y="30" width="320" height="8" fill="#1d4ed8"/>
    <text x="16" y="24" fill="#ffffff" font-size="14" font-weight="700">regions</text>
    <text x="304" y="24" fill="#bfdbfe" font-size="11" text-anchor="end">Hierarchy</text>
    <g transform="translate(16, 55)" font-size="12" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="155">INTEGER</tspan></text>
      <text y="42"><tspan fill="#f1f5f9">    name</tspan><tspan fill="#94a3b8" dx=\"140\">VARCHAR(100)</tspan></text>
      <text y="68"><tspan fill="#f1f5f9">    province</tspan><tspan fill="#94a3b8" dx=\"120\">VARCHAR(50)</tspan></text>
    </g>
  </g>

  <!-- 2. CLUSTERS -->
  <g transform="translate(50, 370)" filter="url(#shadow)">
    <rect width="320" height="175" rx="10" fill="#1e293b" stroke="#3b82f6" stroke-width="1.5"/>
    <rect width="320" height="38" rx="10" fill="url(#grad-blue)"/>
    <rect y="30" width="320" height="8" fill="#1d4ed8"/>
    <text x="16" y="24" fill="#ffffff" font-size="14" font-weight="700">clusters</text>
    <text x="304" y="24" fill="#bfdbfe" font-size="11" text-anchor="end">Werkingsgebieden</text>
    <g transform="translate(16, 55)" font-size="12" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="155">INTEGER</tspan></text>
      <text y="42"><tspan fill="#f1f5f9">    name</tspan><tspan fill="#94a3b8" dx="140">VARCHAR(100)</tspan></text>
      <text y="68"><tspan fill="#f1f5f9">    province</tspan><tspan fill="#94a3b8" dx="120">VARCHAR(50)</tspan></text>
      <text y="94"><tspan fill="#38bdf8" font-weight="700">FK  region_id</tspan><tspan fill="#94a3b8" dx="105">INTEGER &rarr; regions.id</tspan></text>
    </g>
  </g>

  <!-- 3. MUNICIPALITIES -->
  <g transform="translate(50, 610)" filter="url(#shadow)">
    <rect width="320" height="150" rx="10" fill="#1e293b" stroke="#3b82f6" stroke-width="1.5"/>
    <rect width="320" height="38" rx="10" fill="url(#grad-blue)"/>
    <rect y="30" width="320" height="8" fill="#1d4ed8"/>
    <text x="16" y="24" fill="#ffffff" font-size="14" font-weight="700">municipalities</text>
    <text x="304" y="24" fill="#bfdbfe" font-size="11" text-anchor="end">Members (1:N)</text>
    <g transform="translate(16, 55)" font-size="12" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="155">INTEGER</tspan></text>
      <text y="42"><tspan fill="#f1f5f9">    name</tspan><tspan fill="#94a3b8" dx="140">VARCHAR(100)</tspan></text>
      <text y="68"><tspan fill="#38bdf8" font-weight="700">FK  department_id</tspan><tspan fill="#94a3b8" dx="66">INTEGER &rarr; depts.id</tspan></text>
    </g>
  </g>

  <!-- 4. DEPARTMENTS (CENTRAAL / ROOD ACCENT) -->
  <g transform="translate(530, 130)" filter="url(#shadow)">
    <rect width="320" height="640" rx="10" fill="#1e293b" stroke="#ef4444" stroke-width="2.5"/>
    <rect width="320" height="42" rx="10" fill="url(#grad-red)"/>
    <rect y="32" width="320" height="10" fill="#b91c1c"/>
    <text x="16" y="26" fill="#ffffff" font-size="15" font-weight="800">departments</text>
    <text x="304" y="26" fill="#fee2e2" font-size="11" text-anchor="end">CORE ENTITY</text>
    
    <g transform="translate(16, 60)" font-size="12" fill="#e2e8f0">
      <text y="14"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="155">INTEGER</tspan></text>
      <text y="38"><tspan fill="#f43f5e" font-weight="700">UK  name</tspan><tspan fill="#94a3b8" dx="135">VARCHAR(100)</tspan></text>
      <text y="62"><tspan fill="#cbd5e1">    group</tspan><tspan fill="#94a3b8" dx="140">VARCHAR(50)</tspan></text>
      <text y="86"><tspan fill="#cbd5e1">    province</tspan><tspan fill="#94a3b8" dx="123">VARCHAR(50)</tspan></text>
      <text y="110"><tspan fill="#cbd5e1">    type</tspan><tspan fill="#94a3b8" dx="150">VARCHAR(50)</tspan></text>
      <text y="134"><tspan fill="#cbd5e1">    email</tspan><tspan fill="#94a3b8" dx="143">VARCHAR(100)</tspan></text>
      <text y="158"><tspan fill="#cbd5e1">    telephone</tspan><tspan fill="#94a3b8" dx="119">VARCHAR(50)</tspan></text>
      <text y="182"><tspan fill="#cbd5e1">    address</tspan><tspan fill="#94a3b8" dx="130">VARCHAR(255)</tspan></text>
      <text y="206"><tspan fill="#cbd5e1">    postal_address</tspan><tspan fill="#94a3b8" dx="91">VARCHAR(255)</tspan></text>
      <text y="230"><tspan fill="#cbd5e1">    website_override</tspan><tspan fill="#94a3b8" dx="73">VARCHAR(255)</tspan></text>
      <text y="254"><tspan fill="#cbd5e1">    comments</tspan><tspan fill="#94a3b8" dx="116">VARCHAR(1000)</tspan></text>
      <text y="278"><tspan fill="#cbd5e1">    entiteitnummer</tspan><tspan fill="#94a3b8" dx="90">VARCHAR(20)</tspan></text>
      <text y="302"><tspan fill="#cbd5e1">    color</tspan><tspan fill="#94a3b8" dx="145">VARCHAR(20)</tspan></text>
      <text y="326"><tspan fill="#cbd5e1">    transparent</tspan><tspan fill="#94a3b8" dx="107">BOOLEAN</tspan></text>
      <text y="350"><tspan fill="#cbd5e1">    lat</tspan><tspan fill="#94a3b8" dx="160">FLOAT</tspan></text>
      <text y="374"><tspan fill="#cbd5e1">    lon</tspan><tspan fill="#94a3b8" dx="158">FLOAT</tspan></text>
      <text y="398"><tspan fill="#38bdf8" font-weight="700">FK  region_id</tspan><tspan fill="#94a3b8" dx="105">INTEGER &rarr; regions.id</tspan></text>
      <text y="422"><tspan fill="#38bdf8" font-weight="700">FK  cluster_id</tspan><tspan fill="#94a3b8" dx="100">INTEGER &rarr; clusters.id</tspan></text>
      
      <line x1="-8" y1="445" x2="295" y2="445" stroke="#334155" stroke-width="1.2" />
      <text y="470" fill="#94a3b8" font-size="11">&#9679; Relaties: vehicles, shapes,</text>
      <text y="490" fill="#94a3b8" font-size="11">&#9679; members, services (N:M)</text>
      <text y="510" fill="#94a3b8" font-size="11">&#9679; Cascade: delete-orphan</text>
    </g>
  </g>

  <!-- 5. DEPARTMENT_SHAPES (PostGIS Vector) -->
  <g transform="translate(530, 840)" filter="url(#shadow)">
    <rect width="320" height="250" rx="10" fill="#1e293b" stroke="#14b8a6" stroke-width="2"/>
    <rect width="320" height="40" rx="10" fill="url(#grad-teal)"/>
    <rect y="30" width="320" height="10" fill="#0f766e"/>
    <text x="16" y="25" fill="#ffffff" font-size="14" font-weight="700">department_shapes</text>
    <text x="304" y="25" fill="#ccfbf1" font-size="11" text-anchor="end">PostGIS Layer</text>
    <g transform="translate(16, 58)" font-size="12" fill="#e2e8f0">
      <text y="14"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="155">INTEGER</tspan></text>
      <text y="36"><tspan fill="#cbd5e1">    shape_id</tspan><tspan fill="#94a3b8" dx="120">VARCHAR</tspan></text>
      <text y="58"><tspan fill="#cbd5e1">    name (deelgem)</tspan><tspan fill="#94a3b8" dx="80">VARCHAR</tspan></text>
      <text y="80"><tspan fill="#cbd5e1">    postcode</tspan><tspan fill="#94a3b8" dx="120">VARCHAR</tspan></text>
      <text y="102"><tspan fill="#cbd5e1">    hoofdgem</tspan><tspan fill="#94a3b8" dx="115">VARCHAR</tspan></text>
      <text y="124"><tspan fill="#38bdf8" font-weight="700">FK  department_id</tspan><tspan fill="#94a3b8" dx="65">INTEGER &rarr; depts.id</tspan></text>
      <text y="146"><tspan fill="#fbbf24">    match_method</tspan><tspan fill="#94a3b8" dx="90">MatchMethodEnum</tspan></text>
      <text y="168"><tspan fill="#2dd4bf" font-weight="700">    geom</tspan><tspan fill="#2dd4bf" dx="140">MULTIPOLYGON (4326)</tspan></text>
    </g>
  </g>

  <!-- 6. VEHICLES -->
  <g transform="translate(970, 130)" filter="url(#shadow)">
    <rect width="300" height="195" rx="10" fill="#1e293b" stroke="#3b82f6" stroke-width="1.5"/>
    <rect width="300" height="38" rx="10" fill="url(#grad-blue)"/>
    <rect y="30" width="300" height="8" fill="#1d4ed8"/>
    <text x="16" y="24" fill="#ffffff" font-size="14" font-weight="700">vehicles</text>
    <text x="284" y="24" fill="#bfdbfe" font-size="11" text-anchor="end">Wagenpark (1:N)</text>
    <g transform="translate(16, 55)" font-size="12" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="140">INTEGER</tspan></text>
      <text y="40"><tspan fill="#f1f5f9">    name</tspan><tspan fill="#94a3b8" dx="125">VARCHAR(100)</tspan></text>
      <text y="64"><tspan fill="#cbd5e1">    fleet_nr</tspan><tspan fill="#94a3b8" dx="110">VARCHAR(50)</tspan></text>
      <text y="88"><tspan fill="#cbd5e1">    address</tspan><tspan fill="#94a3b8" dx="115">VARCHAR(255)</tspan></text>
      <text y="112"><tspan fill="#cbd5e1">    lat / lon</tspan><tspan fill="#94a3b8" dx="105">FLOAT</tspan></text>
      <text y="136"><tspan fill="#38bdf8" font-weight="700">FK  department_id</tspan><tspan fill="#94a3b8" dx="52">INTEGER &rarr; depts.id</tspan></text>
    </g>
  </g>

  <!-- 7. SIT_LOCATIONS & SIT_VEHICLES -->
  <g transform="translate(970, 360)" filter="url(#shadow)">
    <rect width="250" height="150" rx="10" fill="#1e293b" stroke="#f59e0b" stroke-width="1.5"/>
    <rect width="250" height="36" rx="10" fill="url(#grad-amber)"/>
    <rect y="28" width="250" height="8" fill="#b45309"/>
    <text x="16" y="23" fill="#ffffff" font-size="13" font-weight="700">sit_locations</text>
    <g transform="translate(16, 52)" font-size="11" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="115">INTEGER</tspan></text>
      <text y="38"><tspan fill="#f1f5f9">    name / type</tspan><tspan fill="#94a3b8" dx="65">VARCHAR</tspan></text>
      <text y="60"><tspan fill="#cbd5e1">    province</tspan><tspan fill="#94a3b8" dx="80">VARCHAR</tspan></text>
      <text y="82"><tspan fill="#cbd5e1">    address / coords</tspan><tspan fill="#94a3b8" dx="45">VARCHAR/FLT</tspan></text>
    </g>
  </g>

  <g transform="translate(1300, 360)" filter="url(#shadow)">
    <rect width="260" height="150" rx="10" fill="#1e293b" stroke="#f59e0b" stroke-width="1.5"/>
    <rect width="260" height="36" rx="10" fill="url(#grad-amber)"/>
    <rect y="28" width="260" height="8" fill="#b45309"/>
    <text x="16" y="23" fill="#ffffff" font-size="13" font-weight="700">sit_vehicles</text>
    <g transform="translate(16, 52)" font-size="11" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="120">INTEGER</tspan></text>
      <text y="38"><tspan fill="#f1f5f9">    name</tspan><tspan fill="#94a3b8" dx="105">VARCHAR(100)</tspan></text>
      <text y="60"><tspan fill="#cbd5e1">    fleet_nr</tspan><tspan fill="#94a3b8" dx="90">VARCHAR(50)</tspan></text>
      <text y="82"><tspan fill="#38bdf8" font-weight="700">FK  sit_location_id</tspan><tspan fill="#94a3b8" dx="35">INT &rarr; sit_loc.id</tspan></text>
    </g>
  </g>

  <!-- 8. DEPARTMENT_SERVICES & SERVICES -->
  <g transform="translate(970, 540)" filter="url(#shadow)">
    <rect width="240" height="120" rx="10" fill="#1e293b" stroke="#64748b" stroke-width="1.5"/>
    <rect width="240" height="36" rx="10" fill="url(#grad-slate)"/>
    <rect y="28" width="240" height="8" fill="#334155"/>
    <text x="16" y="23" fill="#ffffff" font-size="13" font-weight="700">department_services</text>
    <g transform="translate(16, 52)" font-size="11" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK,FK  dept_id</tspan><tspan fill="#94a3b8" dx="70">INT &rarr; depts.id</tspan></text>
      <text y="38"><tspan fill="#fbbf24" font-weight="700">PK,FK  service_id</tspan><tspan fill="#94a3b8" dx="52">INT &rarr; srv.id</tspan></text>
      <text y="58" fill="#94a3b8">&#9679; N:M Junction Table</text>
    </g>
  </g>

  <g transform="translate(1260, 540)" filter="url(#shadow)">
    <rect width="300" height="120" rx="10" fill="#1e293b" stroke="#a855f7" stroke-width="1.5"/>
    <rect width="300" height="36" rx="10" fill="url(#grad-purple)"/>
    <rect y="28" width="300" height="8" fill="#7e22ce"/>
    <text x="16" y="23" fill="#ffffff" font-size="13" font-weight="700">services</text>
    <text x="284" y="23" fill="#f3e8ff" font-size="11" text-anchor="end">Catalogus</text>
    <g transform="translate(16, 52)" font-size="11" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="145">INTEGER</tspan></text>
      <text y="38"><tspan fill="#f43f5e" font-weight="700">UK  name</tspan><tspan fill="#94a3b8" dx="128">VARCHAR(50)</tspan></text>
      <text y="56" fill="#94a3b8">Jeugd, Zorgbib, Brugfiguren...</text>
    </g>
  </g>

  <!-- 9. VOLUNTEER_CORPS & COORDINATE_CACHE -->
  <g transform="translate(970, 690)" filter="url(#shadow)">
    <rect width="270" height="145" rx="10" fill="#1e293b" stroke="#14b8a6" stroke-width="1.5"/>
    <rect width="270" height="36" rx="10" fill="url(#grad-teal)"/>
    <rect y="28" width="270" height="8" fill="#0f766e"/>
    <text x="16" y="23" fill="#ffffff" font-size="13" font-weight="700">volunteer_corps</text>
    <g transform="translate(16, 52)" font-size="11" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="125">INTEGER</tspan></text>
      <text y="36"><tspan fill="#f43f5e" font-weight="700">UK  municipality</tspan><tspan fill="#94a3b8" dx="65">VARCHAR</tspan></text>
      <text y="56"><tspan fill="#cbd5e1">    province</tspan><tspan fill="#94a3b8" dx="85">VARCHAR</tspan></text>
      <text y="76"><tspan fill="#cbd5e1">    phase_1 .. phase_8</tspan><tspan fill="#94a3b8" dx="30">BOOLEAN (8 fasen)</tspan></text>
    </g>
  </g>

  <g transform="translate(1270, 690)" filter="url(#shadow)">
    <rect width="290" height="145" rx="10" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>
    <rect width="290" height="36" rx="10" fill="url(#grad-slate)"/>
    <rect y="28" width="290" height="8" fill="#1e293b"/>
    <text x="16" y="23" fill="#ffffff" font-size="13" font-weight="700">coordinate_cache</text>
    <g transform="translate(16, 52)" font-size="11" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="145">INTEGER</tspan></text>
      <text y="36"><tspan fill="#f43f5e" font-weight="700">UK  address</tspan><tspan fill="#94a3b8" dx="115">VARCHAR</tspan></text>
      <text y="56"><tspan fill="#cbd5e1">    lat, lon</tspan><tspan fill="#94a3b8" dx="115">FLOAT</tspan></text>
      <text y="76"><tspan fill="#cbd5e1">    last_checked</tspan><tspan fill="#94a3b8" dx="78">DATETIME (UTC)</tspan></text>
    </g>
  </g>

  <!-- 10. USERS & AUDIT_LOGS -->
  <g transform="translate(970, 860)" filter="url(#shadow)">
    <rect width="270" height="165" rx="10" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>
    <rect width="270" height="36" rx="10" fill="url(#grad-slate)"/>
    <rect y="28" width="270" height="8" fill="#1e293b"/>
    <text x="16" y="23" fill="#ffffff" font-size="13" font-weight="700">users</text>
    <g transform="translate(16, 52)" font-size="11" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="125">INTEGER</tspan></text>
      <text y="36"><tspan fill="#f43f5e" font-weight="700">UK  username</tspan><tspan fill=\"#94a3b8\" dx=\"85\">VARCHAR</tspan></text>
      <text y="56"><tspan fill="#cbd5e1">    password_hash</tspan><tspan fill="#94a3b8" dx=\"55\">VARCHAR (Bcrypt)</tspan></text>
      <text y="76"><tspan fill="#cbd5e1">    role, province_acc</tspan><tspan fill=\"#94a3b8\" dx=\"35\">VARCHAR</tspan></text>
      <text y="96"><tspan fill="#cbd5e1">    force_pwd_change</tspan><tspan fill=\"#94a3b8\" dx=\"40\">BOOLEAN</tspan></text>
    </g>
  </g>

  <g transform="translate(1270, 860)" filter="url(#shadow)">
    <rect width="290" height="165" rx="10" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>
    <rect width="290" height="36" rx="10" fill="url(#grad-slate)"/>
    <rect y="28" width="290" height="8" fill="#1e293b"/>
    <text x="16" y="23" fill="#ffffff" font-size="13" font-weight="700">audit_logs</text>
    <g transform="translate(16, 52)" font-size="11" fill="#e2e8f0">
      <text y="16"><tspan fill="#fbbf24" font-weight="700">PK  id</tspan><tspan fill="#94a3b8" dx="145">INTEGER</tspan></text>
      <text y="36"><tspan fill="#cbd5e1">    timestamp, user</tspan><tspan fill="#94a3b8" dx=\"65\">VARCHAR</tspan></text>
      <text y="56"><tspan fill="#cbd5e1">    action, table_name</tspan><tspan fill=\"#94a3b8\" dx=\"45\">VARCHAR</tspan></text>
      <text y="76"><tspan fill="#cbd5e1">    row_name</tspan><tspan fill="#94a3b8" dx=\"95\">VARCHAR</tspan></text>
      <text y="96"><tspan fill="#cbd5e1">    details</tspan><tspan fill="#94a3b8" dx=\"110\">TEXT</tspan></text>
    </g>
  </g>

  <!-- LEGENDE ONDERAAN -->
  <g transform="translate(50, 810)" filter="url(#shadow)">
    <rect width="320" height="180" rx="10" fill="#1e293b" stroke="#334155" stroke-width="1.2"/>
    <text x="16" y="26" fill="#f8fafc" font-size="13" font-weight="700">LEGENDE &amp; NOTATIE</text>
    <g transform="translate(16, 45)" font-size="11" fill="#cbd5e1">
      <text y="14"><tspan fill="#fbbf24" font-weight="700">PK</tspan> : Primaire Sleutel (Primary Key)</text>
      <text y="34"><tspan fill="#38bdf8" font-weight="700">FK</tspan> : Vreemde Sleutel (Foreign Key)</text>
      <text y="54"><tspan fill="#f43f5e" font-weight="700">UK</tspan> : Unieke Waarde (Unique Constraint)</text>
      <text y="74"><tspan fill="#2dd4bf" font-weight="700">PostGIS</tspan> : Ruimtelijke MultiPolygon Tabel</text>
      <text y="94"><tspan fill="#a855f7" font-weight="700">N:M</tspan> : Veel-op-veel relatie via koppeltabel</text>
      <text y="114"><tspan fill="#94a3b8">&#9679; Blauwe/Rode lijnen</tspan> : 1:N Vreemde Sleutel relaties</text>
    </g>
  </g>
</svg>"""

with open("erd_diagram.svg", "w", encoding="utf-8") as f:
    f.write(svg_content)
print("erd_diagram.svg successfully created!")

# Convert SVG to PNG using headless Chrome / Edge
browser_paths = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
]

browser = None
for b in browser_paths:
    if os.path.exists(b):
        browser = b
        break

if browser:
    # Wrap SVG in a temporary clean HTML for crisp screenshot
    html_wrapper = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ margin: 0; padding: 0; background-color: #0b1120; }}
  svg {{ display: block; }}
</style>
</head>
<body>
{svg_content}
</body>
</html>"""
    with open("temp_erd.html", "w", encoding="utf-8") as f:
        f.write(html_wrapper)
    
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--screenshot=erd_diagram.png",
        "--window-size=1640,1160",
        "--hide-scrollbars",
        os.path.abspath("temp_erd.html")
    ]
    print(f"Running browser screenshot via: {browser}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists("erd_diagram.png"):
        print("erd_diagram.png successfully rendered! Size:", os.path.getsize("erd_diagram.png"))
        if os.path.exists("temp_erd.html"):
            os.remove("temp_erd.html")
    else:
        print("Screenshot command finished, but erd_diagram.png not found. Output:", res.stdout, res.stderr)
else:
    print("No headless browser found to convert SVG to PNG.")
