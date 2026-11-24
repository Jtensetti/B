//! Great-circle distances. Maintained by the routing team.

const EARTH_RADIUS_KM: f64 = 6371.0;

/// Distance in kilometres between two points given in decimal degrees.
pub fn distance_km(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let (p1, p2) = (lat1.to_radians(), lat2.to_radians());
    let dp = (lat2 - lat1).to_radians();
    let dl = (lon2 - lon1).to_radians();
    let a = (dp / 2.0).sin().powi(2) + p1.cos() * p2.cos() * (dl / 2.0).sin().powi(2);
    2.0 * EARTH_RADIUS_KM * a.sqrt().asin()
}

/// Road distance estimate: the great-circle distance times a detour factor of 1.25.
pub fn road_km(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    distance_km(lat1, lon1, lat2, lon2) * 1.25
}
