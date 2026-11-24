namespace App;

/// Port of libs/geo (Rust): haversine distance times a 1.25 road detour factor.
public static class Geo
{
    const double EarthRadiusKm = 6371.0;

    static double DistanceKm(double lat1, double lon1, double lat2, double lon2)
    {
        double p1 = lat1 * Math.PI / 180.0, p2 = lat2 * Math.PI / 180.0;
        double dp = (lat2 - lat1) * Math.PI / 180.0;
        double dl = (lon2 - lon1) * Math.PI / 180.0;
        double a = Math.Pow(Math.Sin(dp / 2.0), 2) + Math.Cos(p1) * Math.Cos(p2) * Math.Pow(Math.Sin(dl / 2.0), 2);
        return 2.0 * EarthRadiusKm * Math.Asin(Math.Sqrt(a));
    }

    public static double RoadKm(double lat1, double lon1, double lat2, double lon2) =>
        DistanceKm(lat1, lon1, lat2, lon2) * 1.25;
}
