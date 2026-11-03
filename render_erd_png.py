import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def draw_erd():
    fig = plt.figure(figsize=(24, 15), facecolor='#0b1120')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0b1120')
    ax.set_xlim(0, 1600)
    ax.set_ylim(0, 1000)
    ax.axis('off')

    # Draw Subtle Background Grid
    for x in range(0, 1600, 50):
        ax.axvline(x, color='#1e293b', lw=0.5, alpha=0.3)
    for y in range(0, 1000, 50):
        ax.axhline(y, color='#1e293b', lw=0.5, alpha=0.3)

    # Header Banner
    header = patches.FancyBboxPatch((40, 915), 1520, 60, boxstyle="round,pad=0,rounding_size=10",
                                   facecolor='#1e293b', edgecolor='#334155', lw=1.5)
    ax.add_patch(header)
    ax.text(65, 952, "Rode Kruis-Vlaanderen Map Generator — Database ERD", 
            fontsize=18, fontweight='bold', color='#ffffff', va='center')
    ax.text(65, 932, "PostgreSQL + PostGIS Ruimtelijk Datamodel | SQLAlchemy ORM & GeoAlchemy2", 
            fontsize=11, color='#94a3b8', va='center')
    
    tag = patches.FancyBboxPatch((1380, 930), 160, 30, boxstyle="round,pad=0,rounding_size=6",
                                facecolor='#dc2626', edgecolor='none')
    ax.add_patch(tag)
    ax.text(1460, 945, "DATABASE v2.0", fontsize=11, fontweight='bold', color='#ffffff', ha='center', va='center')

    # Table Drawer Helper
    def draw_table(x, y, w, h, title, subtitle, header_color, fields):
        # Body
        body = patches.FancyBboxPatch((x, y - h), w, h, boxstyle="round,pad=0,rounding_size=8",
                                     facecolor='#1e293b', edgecolor=header_color if header_color == '#dc2626' else '#334155', 
                                     lw=2 if header_color == '#dc2626' else 1.2)
        ax.add_patch(body)
        
        # Header Box
        header_h = 32
        hdr = patches.FancyBboxPatch((x, y - header_h), w, header_h, boxstyle="round,pad=0,rounding_size=8",
                                    facecolor=header_color, edgecolor='none')
        ax.add_patch(hdr)
        # Flatten bottom corners of header
        flat = patches.Rectangle((x, y - header_h), w, 8, facecolor=header_color, edgecolor='none')
        ax.add_patch(flat)
        
        ax.text(x + 12, y - header_h / 2, title, fontsize=12, fontweight='bold', color='#ffffff', va='center')
        if subtitle:
            ax.text(x + w - 12, y - header_h / 2, subtitle, fontsize=9, color='#e2e8f0', alpha=0.8, ha='right', va='center')

        # Fields
        cur_y = y - header_h - 18
        for f in fields:
            f_type_prefix = f[0] # PK, FK, UK, ''
            f_name = f[1]
            f_dtype = f[2]
            
            # Badge
            if f_type_prefix == 'PK':
                ax.text(x + 12, cur_y, 'PK', fontsize=9, fontweight='bold', color='#fbbf24', va='center')
            elif f_type_prefix == 'FK':
                ax.text(x + 12, cur_y, 'FK', fontsize=9, fontweight='bold', color='#38bdf8', va='center')
            elif f_type_prefix == 'UK':
                ax.text(x + 12, cur_y, 'UK', fontsize=9, fontweight='bold', color='#f43f5e', va='center')
            elif f_type_prefix == 'PK,FK':
                ax.text(x + 12, cur_y, 'PK,FK', fontsize=8, fontweight='bold', color='#fbbf24', va='center')
            
            name_x = x + 48 if f_type_prefix else x + 18
            ax.text(name_x, cur_y, f_name, fontsize=10, color='#f1f5f9', va='center')
            ax.text(x + w - 12, cur_y, f_dtype, fontsize=9, color='#94a3b8', ha='right', va='center')
            cur_y -= 18

    # 1. REGIONS
    draw_table(50, 890, 270, 105, 'regions', 'Hierarchy', '#2563eb', [
        ('PK', 'id', 'INTEGER'),
        ('', 'name', 'VARCHAR(100)'),
        ('', 'province', 'VARCHAR(50)')
    ])

    # 2. CLUSTERS
    draw_table(50, 740, 270, 125, 'clusters', 'Werkingsgebieden', '#2563eb', [
        ('PK', 'id', 'INTEGER'),
        ('', 'name', 'VARCHAR(100)'),
        ('', 'province', 'VARCHAR(50)'),
        ('FK', 'region_id', 'INTEGER → regions.id')
    ])

    # 3. MUNICIPALITIES
    draw_table(50, 570, 270, 105, 'municipalities', 'Members (1:N)', '#2563eb', [
        ('PK', 'id', 'INTEGER'),
        ('', 'name', 'VARCHAR(100)'),
        ('FK', 'department_id', 'INTEGER → depts.id')
    ])

    # 4. DEPARTMENTS (CENTRAAL)
    dept_fields = [
        ('PK', 'id', 'INTEGER'),
        ('UK', 'name', 'VARCHAR(100)'),
        ('', 'group', 'VARCHAR(50)'),
        ('', 'province', 'VARCHAR(50)'),
        ('', 'type', 'VARCHAR(50)'),
        ('', 'email', 'VARCHAR(100)'),
        ('', 'telephone', 'VARCHAR(50)'),
        ('', 'address', 'VARCHAR(255)'),
        ('', 'postal_address', 'VARCHAR(255)'),
        ('', 'website_override', 'VARCHAR(255)'),
        ('', 'comments', 'VARCHAR(1000)'),
        ('', 'entiteitnummer', 'VARCHAR(20)'),
        ('', 'color', 'VARCHAR(20)'),
        ('', 'transparent', 'BOOLEAN'),
        ('', 'lat', 'FLOAT'),
        ('', 'lon', 'FLOAT'),
        ('FK', 'region_id', 'INTEGER → regions.id'),
        ('FK', 'cluster_id', 'INTEGER → clusters.id')
    ]
    draw_table(440, 890, 310, 410, 'departments', 'CORE ENTITY', '#dc2626', dept_fields)

    # 5. DEPARTMENT_SHAPES (PostGIS)
    shape_fields = [
        ('PK', 'id', 'INTEGER'),
        ('', 'shape_id', 'VARCHAR'),
        ('', 'name (deelgem)', 'VARCHAR'),
        ('', 'postcode', 'VARCHAR'),
        ('', 'hoofdgem', 'VARCHAR'),
        ('FK', 'department_id', 'INTEGER → depts.id'),
        ('', 'match_method', 'MatchMethodEnum'),
        ('', 'geom', 'MULTIPOLYGON (4326)')
    ]
    draw_table(440, 420, 310, 200, 'department_shapes', 'PostGIS Geometry', '#0d9488', shape_fields)

    # 6. VEHICLES
    draw_table(870, 890, 280, 160, 'vehicles', 'Wagenpark (1:N)', '#2563eb', [
        ('PK', 'id', 'INTEGER'),
        ('', 'name', 'VARCHAR(100)'),
        ('', 'fleet_nr', 'VARCHAR(50)'),
        ('', 'address', 'VARCHAR(255)'),
        ('', 'lat / lon', 'FLOAT'),
        ('FK', 'department_id', 'INTEGER → depts.id')
    ])

    # 7. SIT_LOCATIONS & SIT_VEHICLES
    draw_table(870, 680, 280, 140, 'sit_locations', 'SIT Depots', '#d97706', [
        ('PK', 'id', 'INTEGER'),
        ('', 'name', 'VARCHAR(100)'),
        ('', 'type', 'VARCHAR(50)'),
        ('', 'province', 'VARCHAR(50)'),
        ('', 'address / coords', 'VARCHAR / FLOAT')
    ])

    draw_table(1250, 680, 280, 120, 'sit_vehicles', 'SIT Fleet', '#d97706', [
        ('PK', 'id', 'INTEGER'),
        ('', 'name', 'VARCHAR(100)'),
        ('', 'fleet_nr', 'VARCHAR(50)'),
        ('FK', 'sit_location_id', 'INTEGER → sit_loc.id')
    ])

    # 8. DEPARTMENT_SERVICES & SERVICES
    draw_table(870, 490, 280, 105, 'department_services', 'N:M Junction', '#475569', [
        ('PK,FK', 'department_id', 'INTEGER → depts.id'),
        ('PK,FK', 'service_id', 'INTEGER → services.id')
    ])

    draw_table(1250, 490, 280, 105, 'services', 'Disciplines Catalogus', '#7c3aed', [
        ('PK', 'id', 'INTEGER'),
        ('UK', 'name', 'VARCHAR(50)')
    ])

    # 9. VOLUNTEER_CORPS & COORDINATE_CACHE
    draw_table(870, 340, 280, 125, 'volunteer_corps', 'Civiele Bescherming', '#0d9488', [
        ('PK', 'id', 'INTEGER'),
        ('UK', 'municipality', 'VARCHAR'),
        ('', 'province', 'VARCHAR'),
        ('', 'phase_1 .. phase_8', 'BOOLEAN (8 fasen)')
    ])

    draw_table(1250, 340, 280, 125, 'coordinate_cache', 'Geocoding Cache', '#475569', [
        ('PK', 'id', 'INTEGER'),
        ('UK', 'address', 'VARCHAR'),
        ('', 'lat / lon', 'FLOAT'),
        ('', 'last_checked', 'DATETIME (UTC)')
    ])

    # 10. USERS & AUDIT_LOGS
    draw_table(870, 170, 280, 140, 'users', 'Auth & Security', '#475569', [
        ('PK', 'id', 'INTEGER'),
        ('UK', 'username', 'VARCHAR'),
        ('', 'password_hash', 'VARCHAR (Bcrypt)'),
        ('', 'role, province_acc', 'VARCHAR'),
        ('', 'force_pwd_change', 'BOOLEAN')
    ])

    draw_table(1250, 170, 280, 140, 'audit_logs', 'System Audit Trail', '#475569', [
        ('PK', 'id', 'INTEGER'),
        ('', 'timestamp, user', 'VARCHAR'),
        ('', 'action, table_name', 'VARCHAR'),
        ('', 'row_name', 'VARCHAR(100)'),
        ('', 'details', 'TEXT')
    ])

    # 11. LEGENDE
    legend_box = patches.FancyBboxPatch((50, 200), 270, 180, boxstyle="round,pad=0,rounding_size=8",
                                       facecolor='#1e293b', edgecolor='#334155', lw=1.2)
    ax.add_patch(legend_box)
    ax.text(65, 360, "LEGENDE & NOTATIE", fontsize=11, fontweight='bold', color='#ffffff')
    ax.text(65, 335, "PK", fontsize=10, fontweight='bold', color='#fbbf24')
    ax.text(95, 335, ": Primaire Sleutel (Primary Key)", fontsize=9, color='#cbd5e1')
    ax.text(65, 312, "FK", fontsize=10, fontweight='bold', color='#38bdf8')
    ax.text(95, 312, ": Vreemde Sleutel (Foreign Key)", fontsize=9, color='#cbd5e1')
    ax.text(65, 289, "UK", fontsize=10, fontweight='bold', color='#f43f5e')
    ax.text(95, 289, ": Unieke Waarde (Unique)", fontsize=9, color='#cbd5e1')
    ax.text(65, 266, "PostGIS", fontsize=10, fontweight='bold', color='#2dd4bf')
    ax.text(125, 266, ": Ruimtelijke Vector Tabel", fontsize=9, color='#cbd5e1')
    ax.text(65, 243, "N:M", fontsize=10, fontweight='bold', color='#a855f7')
    ax.text(100, 243, ": Veel-op-Veel Koppeling", fontsize=9, color='#cbd5e1')
    ax.text(65, 220, "Lijnen", fontsize=10, fontweight='bold', color='#60a5fa')
    ax.text(105, 220, ": 1:N Vreemde Sleutel Relaties", fontsize=9, color='#cbd5e1')

    # RELATIE LIJNEN (Met rechte hoeken en pijlen)
    def draw_direct_arrow(p1, p2, color='#38bdf8'):
        ax.annotate('', xy=p2, xytext=p1,
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=2.0,
                                   mutation_scale=14, shrinkA=3, shrinkB=3))

    # Regions -> Clusters (verticaal)
    draw_direct_arrow((185, 785), (185, 740), '#38bdf8')
    # Regions -> Departments (horizontaal)
    draw_direct_arrow((320, 835), (440, 835), '#38bdf8')
    # Clusters -> Departments (horizontaal)
    draw_direct_arrow((320, 675), (440, 675), '#38bdf8')
    # Departments -> Vehicles (horizontaal)
    draw_direct_arrow((750, 810), (870, 810), '#f87171')
    # Departments -> Municipalities (horizontaal)
    draw_direct_arrow((440, 520), (320, 520), '#f87171')
    # Departments -> Department Shapes (verticaal)
    draw_direct_arrow((595, 480), (595, 420), '#f87171')
    
    # Departments -> Department Services (hoekverbinding)
    ax.annotate('', xy=(870, 440), xytext=(750, 495),
                arrowprops=dict(arrowstyle="-|>", color='#f87171', lw=2.0,
                               mutation_scale=14, shrinkA=3, shrinkB=3,
                               connectionstyle="angle,angleA=0,angleB=90,rad=8"))
    
    # Services -> Department Services (horizontaal)
    draw_direct_arrow((1250, 440), (1150, 440), '#c084fc')
    
    # Sit Locations -> Sit Vehicles (horizontaal)
    draw_direct_arrow((1150, 615), (1250, 615), '#fbbf24')

    plt.tight_layout()
    plt.savefig('erd_diagram.png', dpi=300, facecolor='#0b1120', edgecolor='none')
    print("erd_diagram.png successfully refreshed with clean layout!")

if __name__ == '__main__':
    draw_erd()
