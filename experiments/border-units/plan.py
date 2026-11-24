from b_examples import aviation, weather

KMH_PER_KNOT = 1.852
LB_PER_KG = 2.20462262185
M_PER_FT = 0.3048
L_PER_GAL = 3.785411784

runway_m: float = 900.0
roll_m: float = aviation.takeoff_distance(220.0 / KMH_PER_KNOT, 1100.0 * LB_PER_KG) * M_PER_FT
altitude_m: float = weather.density_altitude(350.0 / M_PER_FT, 28.0) * M_PER_FT
fuel_l: float = aviation.fuel_burn(95.0 / 60.0) * L_PER_GAL + 12.0

print(runway_m - roll_m)
print(altitude_m)
print(fuel_l)
