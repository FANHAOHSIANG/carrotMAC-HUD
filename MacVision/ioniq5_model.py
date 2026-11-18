"""Low-poly first-generation IONIQ 5. Coordinates are fractions of the HUD ego box."""
import math

SILVER = (188, 197, 204)
SHADE = (126, 139, 151)
GLASS = (45, 60, 76)
TRIM = (39, 43, 50)
TIRE = (28, 30, 34)
ALLOY = (159, 172, 184)


def geometry():
    faces = []

    def face(color, *points):
        faces.append((color, points))

    # Horizontal octagons give the hatch and bumpers their chamfered corners.
    def ring(width, rear, nose, z):
        cut = .045
        return ((-width+cut,rear,z),(width-cut,rear,z),(width,rear+cut,z),
                (width,nose-cut,z),(width-cut,nose,z),(-width+cut,nose,z),
                (-width,nose-cut,z),(-width,rear+cut,z))

    def shell(lower, upper, sides, top):
        for i, color in enumerate(sides):
            j = (i+1) % len(lower)
            face(color, lower[i], lower[j], upper[j], upper[i])
        face(top, *upper)

    shell(ring(.45,-.475,.48,.18), ring(.49,-.50,.50,.36),
          [SHADE]*8, SHADE)
    shell(ring(.49,-.50,.50,.36), ring(.48,-.485,.475,.58),
          [SILVER,SHADE,SILVER,SHADE,SILVER,SHADE,SHADE,SHADE], SILVER)
    shell(ring(.445,-.45,.32,.585), ring(.365,-.33,.14,.935),
          [GLASS,(57,70,83),GLASS,GLASS,(68,88,104),GLASS,GLASS,GLASS], SILVER)
    shell(ring(.372,-.36,.15,.927), ring(.365,-.36,.15,.958),
          [TRIM]*8, SILVER)

    # Tailgate light bar, unlit pixels and the front twin pixel clusters.
    face(TRIM, (-.445,-.501,.455),(.445,-.501,.455),(.445,-.501,.607),(-.445,-.501,.607))
    face(TRIM,(-.115,-.5,.29),(.115,-.5,.29),(.115,-.5,.365),(-.115,-.5,.365))
    for side in (-1, 1):
        # B-pillar slopes inward with the side glass.
        face(TRIM,(side*.447,-.03,.59),(side*.447,.000,.59),
             (side*.367,-.014,.93),(side*.367,-.044,.93))
        for i in range(4):
            x = side*(.255+i*.055)
            face((106,36,44),(x-.021,-.503,.465),(x+.021,-.503,.465),
                 (x+.021,-.503,.535),(x-.021,-.503,.535))
        for i in range(2):
            x = side*(.28+i*.078)
            face((197,225,230),(x-.031,.498,.44),(x+.031,.498,.44),
                 (x+.031,.492,.51),(x-.031,.492,.51))
        x = side*.487
        face(SHADE,(x,-.25,.535),(x,.24,.39),(x,.25,.405),(x,-.25,.55))
        for axle in (-.31,.31):
            for color, radius, outer in ((TIRE,1,.502),(ALLOY,.58,.505)):
                rim = [(side*outer,axle+.083*radius*math.cos(a*math.tau/16),
                        .235+.223*radius*math.sin(a*math.tau/16)) for a in range(16)]
                if color == TIRE:
                    for i, point in enumerate(rim):
                        nxt = rim[(i+1)%len(rim)]
                        face(TIRE,point,nxt,(side*.42,*nxt[1:]),(side*.42,*point[1:]))
                face(color,*rim)
            for spoke in range(5):
                a = spoke*math.tau/5
                def hub_point(angle, radius):
                    return (side*.506, axle+.083*radius*math.cos(angle),
                            .235+.223*radius*math.sin(angle))
                face(TRIM,hub_point(a,.17),hub_point(a+.15,.53),hub_point(a+.75,.53))
    return tuple(faces)


FACES = geometry()


def draw(vehicle):
    import pyray as rl
    rl.rl_push_matrix()
    try:
        rl.rl_translatef(vehicle.center.x, vehicle.center.y, vehicle.center.z - vehicle.height_m*.5)
        rl.rl_rotatef(math.degrees(math.atan2(-vehicle.forward_x, vehicle.forward_y)), 0, 0, 1)
        rl.rl_scalef(vehicle.width_m, vehicle.length_m, vehicle.height_m)
        rl.rl_disable_backface_culling()
        try:
            rl.rl_begin(0x0004)  # rlgl RL_TRIANGLES
            try:
                for rgb, points in FACES:
                    rl.rl_color4ub(*rgb,255)
                    for i in range(1,len(points)-1):
                        for vertex in (points[0], points[i], points[i+1]):
                            rl.rl_vertex3f(*vertex)
            finally:
                rl.rl_end()
        finally:
            rl.rl_enable_backface_culling()
    finally:
        rl.rl_pop_matrix()
